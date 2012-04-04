# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2010-2012 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

from twisted.internet import reactor, defer, tcp, ssl
from twisted.application import service

from txamqp.content import Content
import txamqp

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate
_ = translate(__name__)

from vigilo.common.lock import grab_lock # après get_logger

from vigilo.connector import amqp
from vigilo.connector.interfaces import InterfaceNotProvided
from vigilo.connector.interfaces import IBusHandler


def split_host_port(hostdef, use_ssl=False):
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
        if use_ssl:
            port = 5671
        else:
            port = 5670
    return host, port



class MultipleServerMixin:
    # attribute defined outside __init__
    # pylint: disable-msg=W0201

    def setMultipleParams(self, hosts, parentClass):
        """
        @param hosts: les serveurs auxquels se connecter
        @type  hosts: C{str}
        """
        self.hosts = hosts
        self.parentClass = parentClass
        self.attempts = 3
        self._attemptsLeft = 3
        self._usableHosts = None

    def pickServer(self):
        """Choisit un serveur dans la liste des serveurs utilisables."""
        if not self._usableHosts:
            self._usableHosts = self.hosts[:]
        self.host, self.port = self._usableHosts[0]
        self.addr = (self.host, self.port)
        LOGGER.info("Connecting to %s:%s", self.host, self.port)

    def connectionFailed(self, reason):
        """Echec de la connexion, on marque le serveur comme inutilisable."""
        assert self._attemptsLeft is not None
        self._attemptsLeft -= 1
        if self._attemptsLeft == 0:
            if (self.host, self.port) not in self._usableHosts:
                msg = ("Something went wrong, %s:%s is not in "
                       "'usableHosts' (%r)",
                       self.host, self.port, self._usableHosts)
                LOGGER.warning(msg)
            else:
                LOGGER.warning(_("Server %(oldserver)s did not answer after "
                        "%(attempts)d attempts"),
                        {"oldserver": self.host, "attempts": self.attempts})
                self._usableHosts.remove((self.host, self.port))
            self.resetAttempts()
            if hasattr(self.factory, "resetDelay"):
                self.factory.resetDelay()
        return self.parentClass.connectionFailed(self, reason)

    def resetAttempts(self):
        self._attemptsLeft = self.attempts

    def _makeTransport(self):
        """Choisit un serveur avant de créer le transport"""
        # Access to a protected member of a client class
        # pylint: disable-msg=W0212
        self.pickServer()
        return self.parentClass._makeTransport(self)



class VigiloClient(service.Service):
    """Client du bus Vigilo"""


    def __init__(self, host, user, password, use_ssl=False,
                 max_delay=60, log_traffic=False):
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
        self.log_traffic = log_traffic

        self.handlers = []
        self.deferred = defer.Deferred()
        self._packetQueue = [] # List of messages waiting to be sent.
        self.channel = None

        self.factory = amqp.AmqpFactory(parent=self, user=self.user,
                password=self.password, logTraffic=log_traffic)
        self.factory.maxDelay = max_delay


    def startService(self):
        """
        Exécuté au démarrage du connecteur. On essaye de se connecter et on
        lance tous les I{handlers} enregistrés.
        """
        service.Service.startService(self)
        self._getConnection()
        # Notify all child services
        dl = []
        for h in self.handlers:
            if hasattr(h, "startService"):
                dl.append(defer.maybeDeferred(h.startService))
        return defer.gatherResults(dl)


    def stopService(self):
        """
        Exécuté à l'arrêt du connecteur. On transmet l'info à tous les
        I{handlers} enregistrés et on se déconnecte.
        """
        service.Service.stopService(self)
        # Notify all child services
        dl = []
        for h in self.handlers:
            if hasattr(h, "stopService"):
                dl.append(defer.maybeDeferred(h.stopService))
        # On se déconnecte nous-même
        dl = defer.gatherResults(dl)
        dl.addCallback(lambda _x: self.factory.stop())
        return dl


    def _getConnector(self, hosts):
        """
        Récupère l'instance du C{Connector} à utiliser en fonction de
        l'activation de SSL choisie.
        """
        if self.use_ssl:
            return self._getConnectorSSL(hosts)
        else:
            return self._getConnectorTCP(hosts)

    def _getConnectorTCP(self, hosts):
        """Retourne une instance du C{Connector} sans SSL"""
        class MultipleServerConnector(MultipleServerMixin, tcp.Connector):
            pass
        c = MultipleServerConnector(None, None, self.factory, 30, None,
                                    reactor=reactor)
        c.setMultipleParams(hosts, tcp.Connector)
        return c

    def _getConnectorSSL(self, hosts):
        """Retourne une instance du C{Connector} avec SSL"""
        class MultipleServerConnector(MultipleServerMixin, ssl.Connector):
            pass
        context = ssl.ClientContextFactory()
        c = MultipleServerConnector(None, None, self.factory, context, 30,
                                    None, reactor=reactor)
        c.setMultipleParams(hosts, ssl.Connector)
        return c


    def _getConnection(self):
        """Connexion au serveur."""
        if isinstance(self.host, list):
            hosts = [ split_host_port(h, self.use_ssl) for h in self.host ]
            c = self._getConnector(hosts)
            c.connect()
            return c
        else:
            host, port = split_host_port(self.host, self.use_ssl)
            if self.use_ssl:
                context = ssl.ClientContextFactory()
                return reactor.connectSSL(host, port, self.factory, context)
            else:
                return reactor.connectTCP(host, port, self.factory)


    def initializationFailed(self, reason):
        self.stopService()
        reason.raiseException()


    def isConnected(self):
        """
        @return: état de la connexion au serveur
        @rtype:  C{boolean}
        """
        return (self.channel is not None)


    def addHandler(self, handler):
        """
        Ajoute un I{handler}, qui sera notifié des changements d'état de la
        connexion.
        """
        if not IBusHandler.providedBy(handler):
            raise InterfaceNotProvided(IBusHandler, handler)
        self.handlers.append(handler)
        # get protocol handler up to speed when a connection has already
        # been established
        if self.isConnected():
            handler.connectionInitialized()

    def removeHandler(self, handler):
        """Supprime un I{handler}."""
        handler.client = None
        self.handlers.remove(handler)


    def connectionLost(self, reason):
        """Perte de la connexion, on transmet l'info aux I{handlers}."""
        self.deferred = defer.Deferred()
        # Notify all child services
        for h in self.handlers:
            if hasattr(h, "connectionLost"):
                h.connectionLost(reason)
        LOGGER.info(_('Lost connection to the bus (%s)'),
                    reason.getErrorMessage())


    def connectionInitialized(self):
        """
        Send out cached stanzas and call each handler's
        C{connectionInitialized} method.
        """
        # Flush all pending packets
        d = self._sendPacketQueue()
        def doneSendingQueue(_ignore):
            # Trigger the deferred
            if not self.deferred.called:
                self.deferred.callback(self)
            # Notify all child services
            for h in self.handlers:
                if hasattr(h, "connectionInitialized"):
                    h.connectionInitialized()
        d.addCallback(doneSendingQueue)


    @defer.inlineCallbacks
    def _sendPacketQueue(self):
        """Envoie les messages en attente."""
        while self._packetQueue:
            e, k, m, p, c = self._packetQueue.pop(0)
            yield self.send(e, k, m, p, c)


    def send(self, exchange, routing_key, message, persistent=True,
             content_type=None):
        """
        Envoie un message sur le bus. Si la connexion n'est pas encore établie,
        le message est sauvegardé et sera expédié à la prochaine connexion.

        @param exchange: nom de l'I{exchange} où publier
        @type  exchange: C{str}
        @param routing_key: clé de routage
        @type  routing_key: C{str}
        @param message: message à publier
        @type  message: C{str}
        @param persistent: le message doit-il être conservé en cas
            d'indisponibilité du destinatire (par défaut: oui)
        @type  persistent: C{boolean}
        @param content_type: type MIME du contenu du message
        @type  content_type: C{str}
        """

        if not self.isConnected():
            self._packetQueue.append( (exchange, routing_key, message,
                                       persistent, content_type) )
            return defer.succeed(None)

        msg = Content(message)
        if persistent:
            msg["delivery-mode"] = amqp.PERSISTENT
            immediate = False
        else:
            msg["delivery-mode"] = amqp.NON_PERSISTENT
            immediate = True
        if content_type is not None:
            msg["content-type"] = content_type
        if self.log_traffic:
            LOGGER.debug("PUBLISH to %s with key %s: %s"
                         % (exchange, routing_key, msg))
        d = self.channel.basic_publish(
                exchange=exchange, routing_key=routing_key,
                content=msg, immediate=immediate)
        d.addErrback(self._sendFailed)
        return d


    # Wrappers

    def getQueue(self, *args, **kwargs):
        """Récupère l'instance de la file d'attente"""
        if not self.isConnected():
            return None
        return self.factory.p.queue(*args, **kwargs)

    def _sendFailed(self, fail):
        errmsg = _('Sending failed: %(reason)s')
        LOGGER.warning(errmsg % {"reason": amqp.getErrorMessage(fail)})
        return fail

    def disconnect(self):
        """Déconnexion du bus"""
        self.factory.p.transport.loseConnection()


def client_factory(settings):
    """Instanciation d'un client du bus.

    @param settings: fichier de configuration
    @type  settings: C{vigilo.common.conf.settings}
    """
    # adresse du bus
    host = settings['bus'].get('host')
    if host is not None:
        host = host.strip()
        if " " in host:
            host = [ h.strip() for h in host.split(" ") ]

    # SSL
    try:
        use_ssl = settings['bus'].as_bool('use_ssl')
    except KeyError:
        use_ssl = False

    # Temps max entre 2 tentatives de connexion (par défaut 1 min)
    max_delay = int(settings["bus"].get("max_reconnect_delay", 60))

    try:
        log_traffic = settings['bus'].as_bool('log_traffic')
    except (KeyError, ValueError):
        log_traffic = False

    vigilo_client = VigiloClient(
            host,
            settings['bus']['user'],
            settings['bus']['password'],
            use_ssl=use_ssl,
            max_delay=max_delay,
            log_traffic=log_traffic)
    vigilo_client.setName('vigilo_client')

    #try:
    #    subscriptions = settings['bus'].as_list('subscriptions')
    #except KeyError:
    #    subscriptions = []
    #vigilo_client.setupSubscriptions(subscriptions)

    return vigilo_client



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
        """
        Gère un verrou fichier pour que le connecteur ne soit exécuté qu'une
        fois.
        """
        if self.lock_file is None:
            return
        self._logger.debug(_("Creating lock file in %s"), self.lock_file)
        result = grab_lock(self.lock_file)
        if result:
            self._logger.debug(_("Lock file successfully created in %s"),
                               self.lock_file)
        else:
            self._result = 4
            self._logger.error(
                _("Error: lockfile found, another instance may be running.")
            )
            reactor.stop()


    def _handle_errors(self, result):
        """Affichant un message d'erreur"""
        self._result = 1
        if result.check(txamqp.client.Closed):
            srv_msg = result.value.args[0]
            errcode = srv_msg.fields[0]
            message = srv_msg.fields[1]
            self._logger.error(
                    _("Error %(code)s: %(message)s"), {
                        "code": errcode,
                        "message": message,
                    }
                )
        else:
            # Message générique pour signaler l'erreur
            self._logger.error(_("Error: %s"), result.getErrorMessage())
            self._logger.error(result.getTraceback())


    def _handle_timeout(self):
        self._result = 3
        self._logger.error(_("Timeout"))
        return self._stop()


    def _stop(self, _ignored=None):
        """Arrête proprement le connecteur"""
        from vigilo.connector.handlers import BusHandler
        class ReactorStopper(BusHandler):
            """Arrête le reactor quand le bus est vraiment déconnecté"""
            def connectionLost(self, reason):
                reactor.stop()
        stopper = ReactorStopper()
        stopper.setClient(self.client)
        return self.client.stopService()


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
        self.client.factory.noisy = log_traffic
        self.client.startService()
        d = self.client.deferred

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

        d.addErrback(self._handle_errors)
        d.addBoth(self._stop)

        # Garde-fou : on limite la durée de vie du connecteur.
        reactor.callLater(
            self.timeout,
            self._handle_timeout,
        )
        reactor.run()
        return self._result



def oneshotclient_factory(settings):
    """Instanciation d'un client du bus à usage unique.

    @param settings: fichier de configuration
    @type  settings: C{vigilo.common.conf.settings}
    """
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
