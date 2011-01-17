# vim: set fileencoding=utf-8 sw=4 ts=4 et :

"""
Envoi d'états concernant le connecteur pour l'auto-supervision
"""

from __future__ import absolute_import

import time
import socket

from twisted.internet import reactor, task
from wokkel.pubsub import PubSubClient, Item
from wokkel.generic import parseXml

from vigilo.pubsub.xml import NS_PERF, NS_COMMAND
from vigilo.connector.forwarder import PubSubSender
#from vigilo.common.conf import settings
#settings.load_module(__name__)
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)


class StatusPublisher(PubSubSender):

    def __init__(self, forwarder, hostname, servicename, frequency=300):
        """
        Instancie un connecteur vers le bus XMPP.

        @param dbfilename: le nom du fichier permettant la sauvegarde des
                           messages en cas de problème d'éciture sur le BUS
        @type  dbfilename: C{str}
        @param dbtable: Le nom de la table SQL pour la sauvegarde des messages.
        @type  dbtable: C{str}
        """
        super(StatusPublisher, self).__init__()
        self.forwarder = forwarder
        self.hostname = hostname
        self.servicename = servicename
        self.frequency = frequency
        if self.hostname is None:
            self.hostname = socket.gethostname()
            if "." in self.hostname: # on ne veut pas le FQDN
                self.hostname = self.hostname[:self.hostname.index(".")]
        self.task = task.LoopingCall(self.sendStatus)
        # Pas d'envoi simultané
        self.max_send_simult = 1
        self.batch_send_perf = 1

    def connectionInitialized(self):
        """
        Lancée à la connexion (ou re-connexion).
        """
        super(StatusPublisher, self).connectionInitialized()
        if not self.task.running:
            # Normalement on a pas besoin d'être abonné au bus pour envoyer les
            # messages, mais on laisse un peu de temps quand même pour les
            # autres tâches potentielles d'initialisation
            reactor.callLater(10, self.task.start, self.frequency)

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
        forward_method = self.forwardMessage
        if isinstance(self.forwarder, PubSubSender):
            # comme ça on profite de la base de backup
            forward_method = self.forwarder.forwardMessage
        for statname, statvalue in stats.iteritems():
            forward_method(msg_perf % {"datasource": statname,
                                       "value": statvalue})
            LOGGER.debug("Stats for %s: %s = %s" %
                         (self.servicename, statname, statvalue))
