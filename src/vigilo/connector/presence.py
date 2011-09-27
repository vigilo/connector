# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Gestion de la présence, avec éventuellement de la répartition de charge
"""

from __future__ import absolute_import

import random

from zope.interface import implements

from twisted.internet import reactor, task, interfaces
from twisted.internet.interfaces import IPushProducer
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
    changement de priorité régulier toutes les I{s} secondes, pour mettre en
    place de la répartition de charge.

    Les règles de gestion sont les suivantes :
     - Le I{pool} de priorités possibles est entre 1 et C{n+1}, I{n} étant le
       nombre de connecteurs du même compte sur le bus.
     - Toutes les I{x} secondes, si j'ai la priorité la plus basse possible
       (C{1}), alors je prends la priorité la plus haute possible (C{n+1}).
     - Quand un connecteur du même type change de priorité, je baisse ma
       priorité de 1 si cette priorité est disponible.
     - Si un connecteur arrive sur le bus, quitte le bus ou se marque comme
       non-disponible sur le bus, on réinitialise les priorités à un ordre
       arbitraire : l'ordre donné par un tri du nom des ressources XMPP. On
       ré-initialise aussi le timer.
    """

    implements(IPushProducer)

    def __init__(self):
        super(PresenceManager, self).__init__()
        self.priority = None
        self.status_publisher = None
        self._priorities = {}
        self._recentReset = False
        self._changeTimer = None
        try:
            self.static_priority = int(settings["bus"]["priority"])
        except KeyError:
            self.static_priority = None
        except ValueError:
            LOGGER.warning(_("Invalid value for setting bus/priority: "
                             "it must be an integer"))
            self.static_priority = None


    def connectionInitialized(self):
        super(PresenceManager, self).connectionInitialized()
        LOGGER.info(_('Connected to the XMPP bus'))

    def connectionLost(self, reason):
        """
        Lancée à la perte de la connexion au bus. Permet d'arrêter d'envoyer
        les messages en attente.
        """
        super(PresenceManager, self).connectionLost(reason)

    def getFrequency(self):
        """Retourne la fréquence de changement de priorité, en secondes."""
        # TODO: on peut éventuellement la diminuer un peu avec l'augmentation
        # du nombre de connecteurs (au cas où il rempliraient leur file trop
        # vite), mais pas en-dessous de 5, pour laisser le temps du changement
        try:
            return int(settings["bus"]["priority_change_frequency"])
        except (KeyError, ValueError):
            return 10

    def getDefaultPriority(self):
        """
        Retourne la priorité après une réinitialisation: il s'agit d'une
        priorité arbitraire, décidée par l'ordre lexicographique des ressources
        XMPP.
        """
        resources = self._priorities.keys()
        resources.append(self.parent.jid.resource)
        resources.sort()
        return resources.index(self.parent.jid.resource) + 1

    def lowerPriority(self):
        """Baisse la priorité de un, si elle est disponible."""
        if self.priority <= 1:
            return
        next_prio = self.priority - 1
        if next_prio in self._priorities.values():
            return # non disponible
        #LOGGER.debug("Lowering priority to %d", next_prio)
        self.available(priority=next_prio)

    def getMaxPriority(self):
        """
        Calcule la priorité maximale. Nombre d'instances connectées + 1 (marge
        nécessaire pour pouvoir changer)
        """
        # +2: un pour ma propre prio (n'est pas stockée dans self._priorities)
        # et un slot de marge pour changer
        return len(self._priorities) + 2

    def tryToBecomeMaster(self):
        """
        Si on est à la priorité la plus basse, on prend la priorité la plus
        élevée (à condition qu'elle soit dispo). Viva la Revolucion.
        """
        if self.priority != 1:
            return
        if len(self._priorities) == 0:
            # Je suis tout seul
            return
        max_prio = self.getMaxPriority()
        if max_prio in self._priorities.values():
            LOGGER.warning(_("I wanted to become master, but the priority is "
                             "already taken. This should not happen."))
            # Essayons plus tard
            self._changeTimer = reactor.callLater(self.getFrequency(),
                                                  self.tryToBecomeMaster)
            return
        LOGGER.debug("Becoming master with priority %d", max_prio)
        reactor.callLater(self.getFrequency() * 2, self._dictatorshipPrevention)
        self.available(priority=max_prio)

    def _dictatorshipPrevention(self):
        """
        Evite que le master reste en place trop longtemps, ce qui peut arriver
        si un reset se combine mal avec le timer de prise de pouvoir
        """
        if self.priority != self.getMaxPriority():
            return # Nothing to do
        LOGGER.debug("I've been a master for way too long, stepping down.")
        # on baisse de 1 sans vérifier si la place est prise, pour éviter
        # que ça bloque au cas où ça serait le cas. Au pire ça déclenchera
        # un reset par conflit de priorités.
        self.available(priority=self.priority-1)

    def reset(self):
        """
        Réinitialisation des priorités
        """
        if self.priority < 0:
            return # Je suis unavailable
        self._recentReset = True
        LOGGER.debug("Resetting, choosing priority %d", self.getDefaultPriority())
        self.available(priority=self.getDefaultPriority())
        def afterReset():
            self._recentReset = False
        reactor.callLater(self.getFrequency() / 2, afterReset)

    def isMyAccount(self, entity):
        """seul mon propre compte m'intéresse (Narcisse-style)"""
        return self.parent.jid.user == entity.user and \
               self.parent.jid.host == entity.host

    def gotMyPresence(self, priority):
        """
        Réception de ma propre présence (ma ressource, pas seulement mon compte)
        """
        LOGGER.debug("I just took prio %s (%s)",
                     priority, self.parent.jid.resource)
        self.priority = priority
        if self.static_priority:
            self.available(priority=self.static_priority)
            return
        # On a changé de prio, il faut annuler les timers précédents au cas
        # où (cas du reset)
        if (interfaces.IDelayedCall.providedBy(self._changeTimer)
                and self._changeTimer.active()):
            self._changeTimer.cancel()
        if len(self._priorities) == 0:
            # Je suis tout seul
            if priority == 0:
                # Je passe en prio 1 pour que les futurs arrivants puissent se
                # connecter en prio 0
                self.available(priority=1)
        elif priority == 1:
            # Je ne suis pas seul et je viens de prendre la prio 1: préparation
            # du coup d'état
            self._changeTimer = reactor.callLater(self.getFrequency(),
                                                  self.tryToBecomeMaster)

    def availableReceived(self, entity, show=None, statuses=None, priority=0):
        """
        Réception de notre présence ou de celle d'un frère. On baisse sa présence si on peut.
        """
        if not self.isMyAccount(entity):
            return
        if self.parent.jid == entity:
            self.gotMyPresence(priority)
            return
        old_priorities = self._priorities.copy()

        if priority < 0:
            if entity.resource in old_priorities:
                # un frère passe en non-dispo
                LOGGER.debug("Goodbye brother %s", entity.resource)
                del self._priorities[entity.resource]
                self.reset()
            return

        self._priorities[entity.resource] = priority
        if entity.resource not in old_priorities:
            # un nouveau ! Plus on est de fous plus on rit.
            LOGGER.debug("We welcome our new brother %s", entity.resource)
            self.reset()
            return

        if self._recentReset:
            # réinit, tout le monde a changé de prio, c'est normal s'il y a
            # temporairement des conflits
            return

        if (priority >= 0 and self.static_priority is None and
                (priority in old_priorities.values()
                 or priority == self.priority)):
            # conflit de priorités sur le réseau: tout le monde reset
            in_conflict = [r for r in old_priorities
                           if old_priorities[r] == priority]
            in_conflict.insert(0, entity.resource)
            LOGGER.warning(_("Priority conflict, resetting priorities (%s)"),
                           ", ".join(in_conflict))
            self.reset()
            return

        # Tout a l'air bon, on essaye de baisser la priorité
        self.lowerPriority()


    def unavailableReceived(self, entity, statuses=None):
        """
        Réception d'une déconnexion d'un frère, on ré-initialise
        """
        LOGGER.debug("Our brother %s has left us (unavailable)", entity.resource)
        if not self.isMyAccount(entity):
            return
        if entity.resource in self._priorities:
            del self._priorities[entity.resource]
        self.reset()

    def registerStatusPublisher(self, sp):
        self.status_publisher = sp

    # IPushProducer
    def pauseProducing(self):
        if self.priority < 0:
            return
        self.priority = -1
        self.unavailable()
        if self.status_publisher is not None:
            self.status_publisher.queueFull()

    def resumeProducing(self):
        if self.priority >= 0:
            return
        LOGGER.info("Resuming data production")
        self.available(priority=0) # va déclencher un reset chez les autres
        self.reset()
        if self.status_publisher is not None:
            self.status_publisher.queueOk()

    def stopProducing(self):
        """Non utilisé (on pourrait éventuellement se déconnecter)"""
        pass
