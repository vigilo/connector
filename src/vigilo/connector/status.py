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

from zope.interface import implements
from twisted.internet import reactor, task, defer

from vigilo.connector.handlers import BusPublisher
from vigilo.connector.interfaces import IBusHandler
from vigilo.common.gettext import translate
_ = translate(__name__)
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)



class StatusPublisher(BusPublisher):
    """
    Supervision et métrologie d'un connecteur.
    """

    implements(IBusHandler)


    def __init__(self, hostname, servicename, frequency=60, exchange=None):
        """
        @param hostname: le nom d'hôte à utiliser pour le message Nagios
        @type  hostname: C{str}
        @param servicename: le nom de service Nagios à utiliser
        @type  servicename: C{str}
        @param frequency: la fréquence à laquelle envoyer les messages d'état,
            en secondes
        @type  frequency: C{int}
        @param exchange: l'exchange à utiliser, si on ne veut pas utiliser les
            exchanges par défaut du connecteur
        @type  exchange: C{str}
        """
        super(StatusPublisher, self).__init__()
        self.hostname = hostname
        self.servicename = servicename
        self.frequency = frequency
        self.providers = []

        if exchange is not None:
            self._publications["nagios"] = exchange
            self._publications["perf"] = exchange

        self.task = task.LoopingCall(self.sendStatus)
        self.status = (0, _("OK: running"))
        # Pas d'envoi simultané
        self.max_send_simult = 1
        self.batch_send_perf = 1


    def registerProvider(self, provider):
        assert hasattr(provider, "getStats"), \
               "%r does not have a getStats method" % provider
        self.providers.append(provider)

    def unregisterProvider(self, provider):
        self.providers.remove(provider)


    def connectionInitialized(self):
        super(StatusPublisher, self).connectionInitialized()
        def start_task():
            if not self.task.running:
                self.task.start(self.frequency)
        # Normalement on a pas besoin d'être abonné au bus pour envoyer les
        # messages, mais on laisse un peu de temps quand même pour les autres
        # tâches potentielles d'initialisation
        reactor.callLater(10, start_task)


    def connectionLost(self, reason):
        super(StatusPublisher, self).connectionLost(reason)
        # On doit continuer à générer des stats pour que la métrologie soit
        # continue, donc on ne fait pas self.task.stop()


    def sendStatus(self):
        timestamp = int(time.time())

        # État Nagios
        msg_state = {
                "type": "nagios",
                "timestamp": timestamp,
                "cmdname": "PROCESS_SERVICE_CHECK_RESULT",
                "routing_key": "Vigilo",
                }
        msg_state["value"] = ("%(host)s;%(service)s;%(code)d;%(msg)s"
                              % { "host": self.hostname,
                                  "service": self.servicename,
                                  "code": self.status[0],
                                  "msg": self.status[1].encode("utf-8"),
                                })

        # Métrologie
        msg_perf = {
                "type": "perf",
                "timestamp": timestamp,
                "host": self.hostname,
                "routing_key": "Vigilo",
                }
        d = self._collectStats()
        # on envoie même si on est pas connecté pour avoir des graphes continus
        d.addCallback(self._sendStats, msg_perf)

        if self.isConnected():
            d.addCallback(lambda _x: self.sendMessage(msg_state))

        return d


    def _collectStats(self):
        dl = []
        for provider in self.providers:
            dl.append(provider.getStats())
        dl = defer.gatherResults(dl)
        def merge(results):
            stats = {}
            for result in results:
                stats.update(result)
            return stats
        dl.addCallback(merge)
        return dl


    def _sendStats(self, stats, msg_perf):
        dl = []
        for statname, statvalue in stats.iteritems():
            msg = msg_perf.copy()
            msg["datasource"] = "%s-%s" % (self.servicename, statname)
            msg["value"] = statvalue
            dl.append(self.sendMessage(msg))
            LOGGER.info(_("Stats for %(service)s: %(name)s = %(value)s")
                        % {"service": self.servicename,
                           "name": statname,
                           "value": statvalue})
        return defer.DeferredList(dl)



def statuspublisher_factory(settings, servicename, client, providers=[]):
    hostname = settings["connector"].get("hostname", None)
    if hostname is None:
        hostname = socket.gethostname()
        if "." in hostname: # on ne veut pas le FQDN
            hostname = hostname[:hostname.index(".")]

    if servicename is None:
        servicename = os.path.basename(sys.argv[0])

    stats_publisher = StatusPublisher(hostname, servicename,
                exchange=settings["connector"].get("status_exchange", None))

    stats_publisher.setClient(client)
    for provider in providers:
        stats_publisher.registerProvider(provider)

    return stats_publisher
