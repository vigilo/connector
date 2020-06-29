# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2010-2020 CS GROUP – France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import re
import sys

from twisted.internet import reactor, defer, tcp, ssl
from twisted.protocols import tls
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
    Découpe une définition ``hostname:port`` en couple (hostname, port).
    L'hôte peut être désigné par son nom de machine (éventuellement qualifié),
    une adresse IPv4 ou une adresse IPv6. Dans le cas d'une adresse IPv6,
    celle-ci doit être encadrée par les caractères "[" et "]".

    Exemple d'utilisation d'un port non-standard avec une adresse IPv6 :
    "[::1]:1337"

    @param hostdef: le serveur auxquel se connecter.
    @type  hostdef: C{str}
    """
    match = re.match(r"""
            ^                   # Toute la chaîne doit matcher.
            (?P<host>           # Groupe nommé "host" pour matcher l'hôte.
                                #
                \[              # Les IPv6 sont représentées entre crochets.
                    [^]]+       # On autorise n'importe quel caractère
                \]              # jusqu'au crochant fermant (le but n'est
                                # pas de valider l'adresse).
                                #
                |               # ou alors...
                                #
                [^:[]+          # IPv4 ou hôte (qualifié). On accepte n'importe
                                # quel caractère sauf les deux points qui
                                # servent à séparer le port de l'hôte et le
                                # crochet ouvrant (réservé pour les IPv6).
            )
            (?:                 # On utilise un positive look-ahead
                                # (groupe non capturant) pour tester
                                # la présence éventuelle d'un port.
                                #
                :               # Matche le port, qui doit être séparé
                (?P<port>       # de l'hôte par le symbole ":" et ne
                    [0-9]+      # contenir que des chiffres.
                )
            )?                  # Le port est optionnel.
            $                   # Toute la chaîne doit matcher.
        """,
        hostdef,
        re.VERBOSE)
    if not match:
        raise ValueError("Invalid hostname/port")
    groups = match.groupdict()
    host = groups['host']
    port = groups['port']

    # Cas des adresses IPv6.
    if host.startswith('['):
        host = host[1:-1]

    if port is None:
        # Utilisation des ports par défaut.
        if use_ssl:
            port = 5671
        else:
            port = 5672
    else:
        port = int(port)
    return host, port


class MultipleServerMixin:
    """
    Un mixin permettant la connexion en cascade à plusieurs serveurs
    à partir du même connecteur.
    """
    # attribute defined outside __init__
    # pylint: disable-msg=W0201

    def setMultipleParams(self, hosts, parentClass):
        """
        @param hosts: les serveurs auxquels se connecter.
        @type  hosts: C{list}
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
        """
        Echec de la connexion, on marque le serveur comme inutilisable.

        @param reason: La raison de la deconnexion.
        @type  reason: C{twisted.python.failure.Failure}
        """
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


class MultipleServerConnector(MultipleServerMixin, tcp.Connector):
    """
    Un connecteur Twisted capable de supporter des connexions à plusieurs
    serveurs en cascade.
    """
    pass


class VigiloClient(service.Service):
    """Client du bus Vigilo"""


    def __init__(self, hosts, user, password, use_ssl=False,
                 max_delay=60, log_traffic=False):
        """
        Initialise le client.
        @param hosts: liste des serveurs AMQP, ou un serveur (si besoin,
            spécifier le port après des deux-points).
        @type  hosts: C{list} or C{str}
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
        self.hosts = hosts
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
        @param hosts: liste des serveurs AMQP, ou un serveur.
        @type  hosts: C{list} or C{str}
        """
        if self.use_ssl:
            return self._getConnectorSSL(self.factory, hosts)
        else:
            return self._getConnectorTCP(self.factory, hosts)

    def _getConnectorTCP(self, factory, hosts):
        """
        Retourne une instance du C{Connector} sans SSL
        @param hosts: liste des serveurs AMQP, ou un serveur (si besoin,
            spécifier le port après des deux-points).
        @type  hosts: C{list} or C{str}
        """
        c = MultipleServerConnector('', None, factory, 30, None,
                                    reactor=reactor)
        c.setMultipleParams(hosts, tcp.Connector)
        return c

    def _getConnectorSSL(self, factory, hosts):
        """
        Retourne une instance du C{Connector} avec SSL
        @param hosts: liste des serveurs AMQP, ou un serveur (si besoin,
            spécifier le port après des deux-points).
        @type  hosts: C{list} or C{str}
        """
        context = ssl.ClientContextFactory()
        # Le principe est repris de connectSSL(), à ceci près qu'on
        # n'essaye pas de re-basculer vers le support des anciennes versions
        # de OpenSSL/pyOpenSSL lorsque TLSMemoryBIOFactory n'est pas
        # disponible (via ssl.Connector); ceci provoque de toute façon
        # des erreurs liées à la couche de transport (cf. #1112).
        tlsFactory = tls.TLSMemoryBIOFactory(context, True, factory)
        return self._getConnectorTCP(tlsFactory, hosts)


    def _getConnection(self):
        """Connexion au serveur."""
        if isinstance(self.hosts, list):
            hosts = [ split_host_port(h, self.use_ssl) for h in self.hosts ]
            c = self._getConnector(hosts)
            c.connect()
            return c
        else:
            host, port = split_host_port(self.hosts, self.use_ssl)
            if self.use_ssl:
                context = ssl.ClientContextFactory()
                return reactor.connectSSL(host, port, self.factory, context)
            else:
                return reactor.connectTCP(host, port, self.factory)


    def initializationFailed(self, reason):
        """
        @param reason: La raison de la deconnexion.
        @type  reason: C{twisted.python.failure.Failure}
        """
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
        """
        Perte de la connexion, on transmet l'info aux I{handlers}.
        @param reason: La raison de la deconnexion.
        @type  reason: C{twisted.python.failure.Failure}
        """
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
        return d


    @defer.inlineCallbacks
    def _sendPacketQueue(self):
        """Envoie les messages en attente."""
        while self._packetQueue:
            e, k, m, p, c, t = self._packetQueue.pop(0)
            yield self.send(e, k, m, p, c, t)


    def send(self, exchange, routing_key, message, persistent=True,
             content_type=None, ttl=None):
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
        @param ttl: Durée de vie du message (Time To Live) en secondes.
        @type  ttl: C{int}
        """

        if not self.isConnected():
            self._packetQueue.append((exchange, routing_key, message,
                                       persistent, content_type, ttl))
            return defer.succeed(None)

        properties = {}
        if ttl and ttl > 0:
            properties["expiration"] = str(ttl)
        msg = Content(message, properties=properties)

        kwargs = {}
        if persistent:
            msg["delivery-mode"] = amqp.PERSISTENT
            kwargs['immediate'] = False
        else:
            msg["delivery-mode"] = amqp.NON_PERSISTENT
        if content_type is not None:
            msg["content-type"] = content_type
        if self.log_traffic:
            LOGGER.debug("PUBLISH to %s with key %s: %s"
                         % (exchange, routing_key, msg))
        d = self.channel.basic_publish(
                exchange=exchange, routing_key=routing_key,
                content=msg, **kwargs)
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
    hosts = settings['bus'].get('hosts')
    if isinstance(hosts, list):
        hosts = [ h.strip() for h in hosts]
        for h in hosts:
            if not h:
                LOGGER.error(_('Invalid configuration value for option '
                               '"%(key)s".') % {"key": "hosts"})
                sys.exit(1)

    if not hosts:
        LOGGER.error(_('Missing configuration value for option "%(key)s".') %
                {"key": "hosts"})
        sys.exit(1)

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
            hosts,
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

    def __init__(self, hosts, user, password, use_ssl=False,
                 lock_file=None, timeout=30):
        """
        @param hosts: liste des serveurs AMQP, ou un serveur (si besoin,
            spécifier le port après des deux-points).
        @type  hosts: C{list} or C{str}
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
        self.client = self.client_class(hosts, user, password, use_ssl)
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

    # adresse du bus
    hosts = settings['bus'].get('hosts')
    if isinstance(hosts, list):
        hosts = [ h.strip() for h in hosts]
        for h in hosts:
            if not h:
                LOGGER.error(_('Invalid configuration value '
                               'for option "%(key)s".') %
                        {"key": "hosts"})
                sys.exit(1)
    if not hosts:
        LOGGER.error(_('Missing configuration value for option "%(key)s".') %
                {"key": "hosts"})
        sys.exit(1)

    vigilo_client = OneShotClient(
            hosts=hosts,
            user=settings['bus'].get('user', 'guest'),
            password=settings['bus'].get('password', 'guest'),
            use_ssl=use_ssl,
            timeout=int(settings['connector'].get('timeout', 30)),
            lock_file=settings['connector'].get('lock_file'),
            )

    return vigilo_client
