# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import os, sys
from twisted.internet import reactor, defer, error, tcp
from twisted.application import service
from twisted.python import log, failure

from vigilo.connector.amqp import AmqpFactory

from vigilo.common.gettext import translate, l_
_ = translate(__name__)

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

from vigilo.common.lock import grab_lock


def split_host_port(hostdef):
    """
    Découpe une définition hostname:port en couple (hostname, port)
    @todo: Support IPv6
    """
    hostdef = hostdef.strip()
    if ":" in hostdef:
        host, port = hostdef.split(":")
        port = int(port)
    else:
        host = hostdef
        port = 5672
    return host, port



class VigiloClient(service.Service):
    """Client du bus Vigilo"""


    def __init__(self, host, user, password, use_ssl=False, max_delay=60,
                 log_traffic=False):
        """
        Initialise le client.
        @param host: le serveur AMQP
        @type  host: C{str}
        @param user: Identifiant du client.
        @type  user: C{str}
        @param password: Mot de passe associé au compte.
        @type  password: C{str}
        @param use_ssl: Indique si la connexion doit être chiffrée ou non.
        @type  use_ssl: C{bool}
        @param max_delay: le délai maximum entre chaque tentative de
            reconnexion.
        @type  max_delay: C{int}
        """
        self.host = host
        self.user = user
        self.password = password
        self.use_ssl = use_ssl

        self.factory = AmqpFactory(user=self.user, password=self.password,
                                   logTraffic=log_traffic)
        self.factory.maxDelay = max_delay


    def startService(self):
        service.Service.startService(self)
        self._connection = self._getConnection()


    def stopService(self):
        service.Service.stopService(self)
        self.factory.stopTrying()
        self._connection.disconnect()


    def initializationFailed(self, reason):
        self.stopService()
        reason.raiseException()


    def _getConnection(self):
        if isinstance(self.host, list):
            hosts = [ split_host_port(h) for h in self.host ]
            c = MultipleServerConnector(hosts, self.factory,
                                        reactor=reactor)
            c.connect()
            return c
        else:
            host, port = split_host_port(self.host)
            return reactor.connectTCP(host, port, self.factory)



def client_factory(settings):
    from vigilo.pubsub.checknode import VerificationNode

    try:
        require_tls = settings['bus'].as_bool('use_ssl')
    except KeyError:
        require_tls = False

    # Temps max entre 2 tentatives de connexion (par défaut 1 min)
    max_delay = int(settings["bus"].get("max_reconnect_delay", 60))

    host = settings['bus'].get('host')
    if host is not None:
        host = host.strip()
        if " " in host:
            host = [ h.strip() for h in host.split(" ") ]

    vigilo_client = VigiloClient(
            host,
            JID(settings['bus']['jid']),
            settings['bus']['password'],
            use_ssl=use_ssl,
            max_delay=max_delay)
    vigilo_client.setName('vigilo_client')

    try:
        vigilo_client.logTraffic = settings['bus'].as_bool('log_traffic')
    except KeyError:
        vigilo_client.logTraffic = False

    return vigilo_client



class MultipleServerConnector(tcp.Connector):
    def __init__(self, hosts, factory, timeout=30, attempts=3,
                 reactor=None):
        """
        @param host: le serveur XMPP
        @type host: C{str}
        @param port: le port du serveur
        @type port C{int}
        @param factory: Une factory pour le connecteur Twisted.
        @type factory: L{twisted.internet.interfaces.IProtocolFactory}
        @param timeout: Le timeout de connexion.
        @type timeout: C{int}
        @param attempts: Le nombre de tentative de connexion.
        @type: C{int}
        @param reactor: Une instance d'un réacteur de Twisted.
        @type reactor: L{twisted.internet.reactor}
        """
        tcp.Connector.__init__(self, None, None, factory, timeout, None,
                               reactor=reactor)
        self.hosts = hosts
        self.attempts = attempts
        self._attemptsLeft = attempts
        self._usableHosts = None

    def pickServer(self):
        if not self._usableHosts:
            self._usableHosts = self.hosts[:]
        self.host, self.port = self._usableHosts[0]
        log.msg("Connecting to %s:%s" % (self.host, self.port))

    def connectionFailed(self, reason):
        assert self._attemptsLeft is not None
        self._attemptsLeft -= 1
        if self._attemptsLeft == 0:
            LOGGER.warning(_("Server %(oldserver)s did not answer after "
                    "%(attempts)d attempts"),
                    {"oldserver": self.host, "attempts": self.attempts})
            self._usableHosts.remove((self.host, self.port))
            self.resetAttempts()
            if hasattr(self.factory, "resetDelay"):
                self.factory.resetDelay()
        return tcp.Connector.connectionFailed(self, reason)

    def resetAttempts(self):
        self._attemptsLeft = self.attempts

    def _makeTransport(self):
        self.pickServer()
        return tcp.Connector._makeTransport(self)



class LockingError(Exception):
    """Exception remontée quand un fichier de lock est trouvé"""
    pass



class OneShotClient(object):
    """Gestionnaire de client en vue d'un usage unique"""

    client_class = VigiloClient

    def __init__(self, host, user, password, use_ssl=False,
                 lock_file=None, timeout=30):
        """
        @param host: le hostname du serveur AMQP (si besoin, spécifier le port
            après des deux-points)
        @type  host: C{str}
        @param user: Identifiant AMQP du client.
        @type  user: C{str}
        @param password: Mot de passe associé au compte AMQP.
        @type  password: C{str}
        @param use_ssl: Indique si la connexion doit être chiffrée ou non.
        @type  use_ssl: C{bool}
        @param timeout: Durée maximale d'exécution du connecteur,
            afin d'éviter des connecteurs "fous".
        @type  timeout: C{int}
        """
        self.client = self.client_class(host, user, password, use_ssl)
        self.lock_file = lock_file
        self.timeout = timeout
        self._result = 0
        self._func = None
        self._args = ()
        self._kwargs = {}
        self._logger = LOGGER


    def create_lockfile(self):
        if self.lock_file is None:
            return
        self._logger.debug(_("Creating lock file in %s"), self.lock_file)
        result = grab_lock(self.lock_file)
        if result:
            self._logger.debug(_("Lock file successfully created in %s"),
                               self.lock_file)
        else:
            self._stop(failure.Failure(LockingError()), 4)


    def _stop(self, result, code):
        """
        Arrête proprement le connecteur, en affichant un message d'erreur en
        cas de timeout.
        """
        if isinstance(result, failure.Failure):
            if result.check(defer.TimeoutError):
                self._logger.error(_("Timeout"))
            else:
                # Message générique pour signaler l'erreur
                self._logger.error(
                    _("Error: %(message)s (%(type)r)"), {
                        'message': result.getErrorMessage(),
                        'type': str(result),
                    }
                )
        else:
            self._logger.debug(_("Exiting with no error"))
        self._result = code
        self.client.stopService()
        reactor.stop()
        return result


    def setHandler(self, func, *args, **kwargs):
        """
        @param func: Configure la fonction à exécuter pour déclencher
            les traitements de ce connecteur.
        @type func: C{callable}
        @note: Les paramètres supplémentaires (nommés ou non) passés
            à cette méthode seront transmis à L{func} lors de son appel.
        """
        self._func = func
        self._args = args
        self._kwargs = kwargs


    def run(self, log_traffic=False, app_name='Vigilo client'):
        """
        Fait fonctionner le connecteur (connexion, traitement, déconnexion).

        @param log_traffic: Indique si le trafic échangé avec le serveur
            doit être journalisé ou non.
        @type log_traffic: C{bool}
        @param app_name: Nom à donner au client (peut aider au débogage).
        @type app_name: C{str}
        @return: Code de retour de l'exécution du connecteur.
            La valeur 0 est renvoyée lorsque le connecteur a fini son
            exécution normalement. Toute autre valeur signale une erreur.
        @rtype: C{int}
        """
        service.Application(app_name)
        self.create_lockfile()
        # Création du client
        self.client.factory.logTraffic = log_traffic
        self.client.startService()
        d = self.client.factory.deferred

        # Ajout de la fonction de traitement.
        if self._func:
            d.addCallback(
                self._func,
                *self._args,
                **self._kwargs
            )
        else:
            self._logger.warning(_("No handler registered for this "
                                    "one-shot client"))

        d.addErrback(lambda fail: self._stop(fail, code=1))

        # Déconnecte le client du bus.
        d.addCallback(lambda _dummy: self.client.factory.stop())
        d.addCallback(self._stop, code=0)
        #d.addErrback(lambda _dummy: None)
        d.addErrback(log.err)

        # Garde-fou : on limite la durée de vie du connecteur.
        reactor.callLater(
            self.timeout,
            self._stop,
            result=failure.Failure(defer.TimeoutError()),
            code=3
        )
        reactor.run()
        return self._result



def oneshotclient_factory(settings):
    try:
        use_ssl = settings['bus'].as_bool('use_ssl')
    except KeyError:
        use_ssl = False

    vigilo_client = OneShotClient(
            host=settings['bus'].get('host', 'localhost'),
            user=settings['bus'].get('user', 'guest'),
            password=settings['bus'].get('password', 'guest'),
            use_ssl=use_ssl,
            timeout=int(settings['connector'].get('timeout', 30)),
            lock_file=settings['connector'].get('lock_file'),
            )

    return vigilo_client
