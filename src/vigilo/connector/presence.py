# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Gestion de la présence, avec éventuellement de la répartition de charge
"""

from __future__ import absolute_import

import random

from twisted.internet import reactor, task
from wokkel import xmppim

from vigilo.common.conf import settings
from vigilo.common.gettext import translate
_ = translate(__name__)
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)


class PresenceManager(xmppim.PresenceClientProtocol):
    """
    Gère la présence du connecteur. Par défaut la priorité est fixée à 1, mais
    si une autre ressource du même compte se connecte, on cherche une autre
    priorité.

    S'il y a plus d'une instance du compte connectée, alors on provoque un
    changement de priorité régulier toutes les I{n} secondes, pour mettre en
    place de la répartition de charge.
    """

    def __init__(self, forwarder=None):
        super(PresenceManager, self).__init__()
        self.priority = None
        self._priorities = {}
        self._task = task.LoopingCall(self.sendPresence)
        self.forwarder = forwarder
        try:
            self.static_priority = int(settings["bus"]["priority"])
        except (KeyError, ValueError):
            self.static_priority = None


    def connectionInitialized(self):
        super(PresenceManager, self).connectionInitialized()
        def start_sending():
            if not self._task.running:
                self._task.start(self.getFrequency())
        # Ne pas lancer trop tôt pour récupérer les présences des autres
        reactor.callLater(random.randrange(2, 15), start_sending)

    def connectionLost(self, reason):
        """
        Lancée à la perte de la connexion au bus. Permet d'arrêter d'envoyer
        les messages en attente.
        """
        super(PresenceManager, self).connectionLost(reason)
        if self._task.running:
            self._task.stop()

    def getFrequency(self):
        """
        Retourne la fréquence de changement de priorité. Fonction du nombre de
        connecteurs visibles.
        Commence à 10s quand on est tout seul, avec une asymptote réelle des
        changements du groupe à 5s quand le nombre de connecteurs visibles
        augmente.
        Attention, cela détermine aussi la fréquence à laquelle on va vérifier
        que la file d'attente n'est pas trop chargée (qui augmente donc
        géométriquement avec un facteur 5 pour chaque connecteur).
        """
        return 10 + len(self._priorities) * 5

    def choosePriority(self):
        if self.static_priority is not None:
            return self.static_priority
        if not self._priorities:
            return 1 # tout seul, pas besoin de changer
        # Range + 3: un slot pour ma propre priortié, un slot pour pouvoir
        # changer, et un parce que la seconde borne de range() est exclue
        available_priorities = range(1, len(self._priorities) + 3)
        # On enlève les priorité déjà prises par les autres
        for other_p in self._priorities.values():
            if other_p in available_priorities:
                available_priorities.remove(other_p)
        # On enlève notre propre priorité (ben ouais faut bien changer)
        if self.priority in available_priorities:
            available_priorities.remove(self.priority)
        assert len(available_priorities) > 0, \
                    "No available priority ! This should not happen"
        return available_priorities[0] # On prend la première dispo

    def sendPresence(self, priority=None):
        if self.isOverloaded():
            if self.priority >= 0:
                LOGGER.info(_("Queue size too high (%d) ! Switching presence to "
                              "unavailable."), len(self.forwarder.queue))
                self.unavailable()
                self.priority = -1
            return
        if priority is None:
            priority = self.choosePriority()
        if priority == self.priority:
            return
        LOGGER.debug("Sending presence with priority %d", priority)
        if self.xmlstream is not None:
            self.available(priority=priority)
        # On met à jour l'intervalle au cas où le nombre de frères aurait
        # changé
        self._task.interval = self.getFrequency()

    def isOverloaded(self):
        if not self.forwarder:
            return False
        max_queue_size = settings["connector"].get("max_queue_size", 0)
        try:
            max_queue_size = int(max_queue_size)
        except ValueError:
            return False
        if max_queue_size and len(self.forwarder.queue) >= max_queue_size:
            return True
        return False

    def isMyAccount(self, entity):
        """seul mon propre compte m'intéresse (Narcisse-style)"""
        return self.parent.jid.user == entity.user and \
               self.parent.jid.host == entity.host

    def availableReceived(self, entity, show=None, statuses=None, priority=0):
        if not self.isMyAccount(entity):
            return
        if self.parent.jid == entity: # C'est ma propre présence
            self.priority = priority
            return
        self._priorities[entity.resource] = priority
        if priority == self.priority and self.static_priority is None:
            LOGGER.warning(_("Another instance of %(user)s@%(host)s has "
                             "priority %(priority)d ! (me: %(me)s, other: "
                             "%(other)s)"),
                           {"user": self.parent.jid.user,
                            "host": self.parent.jid.host,
                            "priority": priority,
                            "me": self.parent.jid.resource,
                            "other": entity.resource})
            self.sendPresence()
            # On décale le changement de présence pour éviter les collisions
            self._task.stop()
            reactor.callLater(random.randrange(3, 7), self._task.start,
                              self.getFrequency(), now=False)

    def unavailableReceived(self, entity, statuses=None):
        if not self.isMyAccount(entity):
            return
        if entity.resource in self._priorities:
            del self._priorities[entity.resource]

