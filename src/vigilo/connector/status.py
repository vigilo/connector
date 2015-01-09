# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2015 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Envoi d'états concernant le connecteur pour l'auto-supervision
"""

from __future__ import absolute_import

import os
import sys
import time
import socket # pylint: disable-msg=W0403
# W0403: Relative import 'socket', corrigé par le __future__.absolute_import

from zope.interface import implements
from twisted.internet import reactor, task, defer

from vigilo.connector.handlers import BusPublisher
from vigilo.connector.interfaces import IBusHandler
from vigilo.connector.options import parsePublications
from vigilo.common.gettext import translate
_ = translate(__name__)
from vigilo.common.logging import get_logger, get_error_message
LOGGER = get_logger(__name__)



class StatusPublisher(BusPublisher):
    """
    Supervision et métrologie d'un connecteur.
    """

    implements(IBusHandler)


    def __init__(self, hostname, servicename, frequency=60, publications=None):
        """
        @param hostname: le nom d'hôte à utiliser pour le message Nagios
        @type  hostname: C{str}
        @param servicename: le nom de service Nagios à utiliser
        @type  servicename: C{str}
        @param frequency: la fréquence à laquelle envoyer les messages d'état,
            en secondes
        @type  frequency: C{int}
        @param publications: le dictionnaire contenant les différents types de
                             messages et la façon de les publier.
                             Exemple:
                             {
                               "perf": (exchange, ttl)
                             }
                             perf est le type de message.
                             exchange le nom de l'exchange destination.
                             ttl la durée de vie en secondes.
        @type  publications: C{dict} or C{None}
        """
        super(StatusPublisher, self).__init__(publications)
        self.hostname = hostname
        self.servicename = servicename
        self.frequency = frequency
        self.providers = []

        self.task = task.LoopingCall(self.sendStatus)
        self.status = (0, _("OK: running"))
        # Pas d'envoi simultané
        self.max_send_simult = 1
        self.batch_send_perf = 1


    def registerProvider(self, provider):
        """Enregistre un fournisseur de statistiques."""
        assert hasattr(provider, "getStats"), \
               "%r does not have a getStats method" % provider
        self.providers.append(provider)

    def unregisterProvider(self, provider):
        """Supprime un fournisseur de statistiques."""
        self.providers.remove(provider)


    def connectionInitialized(self):
        """
        À la connexion au bus, on commence à collecter et à envoyer les
        statistiques.
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
        super(StatusPublisher, self).connectionLost(reason)
        # On doit continuer à générer des stats pour que la métrologie soit
        # continue, donc on ne fait pas self.task.stop()


    def sendStatus(self):
        """Envoi de l'état et des statistiques sur le bus."""
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
        """
        Collecte les statistiques des fournisseurs dans un même dictionnaire
        @return: C{Deferred} contenant le dictionnaire des statistiques
        @rtype: C{Deferred}
        """
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



def statuspublisher_factory(settings, client, providers=None):
    """
    Construit une instance de L{StatusPublisher}

    @param settings: fichier de configuration
    @type  settings: C{vigilo.common.conf.settings}
    @param client: client du bus
    @type  client: L{vigilo.connector.client.VigiloClient}
    @param providers: liste de fournisseurs de statistiques
    @type  providers: C{list}
    """
    hostname = settings.get("connector", {}).get("hostname", None)
    if hostname is None:
        hostname = socket.gethostname()
        if "." in hostname: # on ne veut pas le FQDN
            hostname = hostname[:hostname.index(".")]

    idinstance = settings.get("instance", "")
    servicename = os.path.basename(sys.argv[0])
    if idinstance:
        servicename = servicename + "-" + str(idinstance)
    servicename = settings.get("connector", {}).get("status_service",
            servicename)
    smne = settings["connector"].get("self_monitoring_nagios_exchange", None)
    smpe = settings["connector"].get("self_monitoring_perf_exchange", None)
    publications = settings.get('publications', {}).copy()
    try:
        # Si besoin (paramètre de surcharge défini dans la configuration)
        # surcharger le paramètre de publication pour les messages qui viennent
        # de l'auto-supervision du connecteur.
        if smne is not None:
            publications["nagios"] = smne
        if smpe is not None:
            publications["perf"] = smpe
        publications = parsePublications(publications)
    except Exception, e:
        LOGGER.error(_('Invalid configuration option for publications: '
                       '(%(error)s).') % {"error": get_error_message(e)})
        sys.exit(1)

    stats_publisher = StatusPublisher(hostname, servicename,
                                      publications=publications)

    stats_publisher.setClient(client)
    if providers is None:
        providers = []
    for provider in providers:
        stats_publisher.registerProvider(provider)

    return stats_publisher
