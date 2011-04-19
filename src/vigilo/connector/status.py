# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Envoi d'états concernant le connecteur pour l'auto-supervision
"""

from __future__ import absolute_import

import os
import sys
import time
import socket

from twisted.internet import reactor, task

from vigilo.pubsub.xml import NS_PERF, NS_COMMAND
from vigilo.connector.forwarder import PubSubSender
from vigilo.common.gettext import translate
_ = translate(__name__)
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)


class StatusPublisher(PubSubSender):
    """
    Supervision et métrologie d'un connecteur.
    """

    def __init__(self, forwarder, hostname, servicename=None, frequency=60,
                 node=None):
        """
        @param forwarder: le conecteur à superviser
        @type  forwarder: instance de L{PubSubForwarder
            <vigilo.connector.forwarder.PubSubForwarder>} (ou une de ses
            sous-classes)
        @param hostname: le nom d'hôte à utiliser pour le message Nagios
        @type  hostname: C{str}
        @param servicename: le nom de service Nagios à utiliser
        @type  servicename: C{str}
        @param frequency: la fréquence à laquelle envoyer les messages d'état,
            en secondes
        @type  frequency: C{int}
        @param node: le noeud de publication à utiliser, si on ne veut pas
            utiliser les noeuds par défaut du connecteur
        @type  node: C{str}
        """
        super(StatusPublisher, self).__init__()
        self.forwarder = forwarder
        self.hostname = hostname
        if servicename is not None:
            self.servicename = servicename
        else:
            self.servicename = os.path.basename(sys.argv[0])
        self.frequency = frequency
        if self.hostname is None:
            self.hostname = socket.gethostname()
            if "." in self.hostname: # on ne veut pas le FQDN
                self.hostname = self.hostname[:self.hostname.index(".")]
        if node is not None:
            for msgtype in self._nodetopublish:
                self._nodetopublish[msgtype] = node
        self.task = task.LoopingCall(self.sendStatus)
        # Pas d'envoi simultané
        self.max_send_simult = 1
        self.batch_send_perf = 1

    def connectionInitialized(self):
        """
        Lancée à la connexion (ou re-connexion).
        """
        super(StatusPublisher, self).connectionInitialized()
        def start_task():
            if not self.task.running:
                self.task.start(self.frequency)
        # Normalement on a pas besoin d'être abonné au bus pour envoyer les
        # messages, mais on laisse un peu de temps quand même pour les autres
        # tâches potentielles d'initialisation
        reactor.callLater(10, start_task)

    def connectionLost(self, reason):
        """
        Lancée à la perte de la connexion au bus.
        """
        super(StatusPublisher, self).connectionLost(reason)
        #self.task.stop() # on doit continuer à générer des stats

    def sendStatus(self):
        timestamp = int(time.time())
        # État Nagios
        msg_state = (
            '<command xmlns="%(namespace)s">'
                '<timestamp>%(timestamp)d</timestamp>'
                '<cmdname>PROCESS_SERVICE_CHECK_RESULT</cmdname>'
                '<value>%(host)s;%(service)s;0;OK: running</value>'
            '</command>' % {
                "namespace": NS_COMMAND,
                "timestamp": timestamp,
                "host": self.hostname,
                "service": self.servicename,
                }
             )
        if self.isConnected():
            self.forwardMessage(msg_state)
        # Métrologie
        msg_perf = ('<perf xmlns="%(namespace)s">'
                        '<timestamp>%(timestamp)d</timestamp>'
                        '<host>%(host)s</host>'
                        '<datasource>%(service)s-%%(datasource)s</datasource>'
                        '<value>%%(value)s</value>'
                    '</perf>' % {
                        "namespace": NS_PERF,
                        "timestamp": timestamp,
                        "host": self.hostname,
                        "service": self.servicename,
                        }
                     )
        stats = self.forwarder.getStats()
        stats.addCallback(self._send_stats, msg_perf)

    def _send_stats(self, stats, msg_perf):
        for statname, statvalue in stats.iteritems():
            self.forwardMessage(msg_perf % {"datasource": statname,
                                            "value": statvalue})
            LOGGER.info(_("Stats for %(service)s: %(name)s = %(value)s")
                        % {"service": self.servicename,
                           "name": statname,
                           "value": statvalue})
