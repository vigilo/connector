# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import os, sys
from twisted.internet import reactor, defer, error
from twisted.application import service
from twisted.python import log, failure

from vigilo.connector.amqp import AmqpFactory

from vigilo.common.gettext import translate, l_
_ = translate(__name__)



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


    def __init__(self, jid, password, host=None,
                 require_tls=False, require_compression=False, max_delay=60):
        """
        Initialise le client.
        @param jid: Identifiant Jabber du client.
        @type jid: C{JID}
        @param password: Mot de passe associé au compte Jabber.
        @type password: C{str}
        @param host: le serveur XMPP
        @type host: C{str}
        @param require_tls: Indique si la connexion doit être chiffrée ou non.
        @type require_tls: C{bool}
        @param require_compression: Indique si la connexion doit être
            compressée ou non. Cette option est incompatible avec l'option
            C{require_tls}. Si les deux options sont activées, la connexion
            NE SERA PAS compressée (mais elle sera chiffrée).
        @type require_compression: C{bool}
        @param max_delay: le délai maximum entre chaque tentative de
            reconnexion.
        @type max_delay: C{int}
        """
        # On court-circuite client.XMPPClient qui utilise une factory
        # qui n'a pas le comportement attendu.
        self.jid = jid
        self.domain = jid.host
        self.host = host

        # On utilise notre factory personnalisée, que l'on configure.
        if isinstance(self.host, list):
            factory = VigiloClientFactory(jid, password)
        else:
            factory = client.HybridClientFactory(jid, password)
        factory.maxDelay = max_delay
        StreamManager.__init__(self, factory)

        self.require_tls = require_tls
        self.require_compression = require_compression

    def _connected(self, xs):
        """
        On modifie dynamiquement l'attribut "required" du plugin
        d'authentification TLSInitiatingInitializer créé automatiquement
        par wokkel, pour imposer TLS si l'administrateur le souhaite, et
        insérer la compression zlib.
        """
        from vigilo.common.logging import get_logger
        LOGGER = get_logger(__name__)

        for index, initializer in enumerate(xs.initializers[:]):
            if not isinstance(initializer, xmlstream.TLSInitiatingInitializer):
                continue

            if self.require_tls:
                # Activation du chiffrement par TLS.
                if self.require_compression:
                    # zlib et TLS sont incompatibles, voir XEP-0138.
                    LOGGER.warning(
                        _("'require_compression' cannot be True when "
                        "'require_tls' is also True.")
                        )
                xs.initializers[index].required = True

            elif self.require_compression:
                # On ajoute la compression zlib et on désactive TLS.
                xs.initializers[index].wanted = False
                xs.initializers[index].required = False
                compressor = CompressInitiatingInitializer(xs)
                compressor.required = True
                xs.initializers.insert(index + 1, compressor)

            else:
                # On utilise le chiffrement TLS si disponible,
                # mais on ne force pas son utilisation.
                xs.initializers[index].wanted = True
                xs.initializers[index].required = False

            # Inutile de regarder plus loin.
            break

        client.XMPPClient._connected(self, xs)

    def _disconnected(self, xs):
        """
        Ajout de l'arrêt à la déconnexion
        @TODO: vérifier que ça ne bloque pas la reconnexion automatique.
        """
        client.XMPPClient._disconnected(self, xs)

    def initializationFailed(self, fail):
        """
        Appelé si l'initialisation échoue. Ici, on ajoute la gestion de
        l'erreur d'authentification.
        """
        from vigilo.common.logging import get_logger
        LOGGER = get_logger(__name__)

        tls_errors = {
            xmlstream.TLSFailed:
                l_("Some error occurred while negotiating TLS encryption"),
            xmlstream.TLSRequired:
                l_("The server requires TLS encryption. Use the "
                    "'require_tls' option to enable TLS encryption."),
            xmlstream.TLSNotSupported:
                l_("TLS encryption was required, but pyOpenSSL is "
                    "not installed"),
        }

        if fail.check(SASLNoAcceptableMechanism, SASLAuthError):
            LOGGER.error(_("Authentication failure: %s"),
                         fail.getErrorMessage())
            try:
                reactor.stop()
            except error.ReactorNotRunning:
                pass
            return

        if fail.check(xmlstream.FeatureNotAdvertized):
            # Le nom de la fonctionnalité non-supportée n'est pas transmis
            # avec l'erreur. On calcule le différentiel entre ce qu'on a
            # demandé et ce qu'on a obtenu pour trouver son nom.
            for initializer in self.xmlstream.initializers:
                if not isinstance(initializer, \
                    xmlstream.BaseFeatureInitiatingInitializer):
                    continue

                if initializer.required and \
                    initializer.feature not in self.xmlstream.features:
                    LOGGER.error(_("The server does not support "
                                    "the '%s' feature"),
                                    initializer.feature[1])
            # Ça peut être une erreur temporaire du serveur (ejabberd fait ça
            # des fois sous forte charge), donc on ré-essaye.
            self._connection.disconnect()
            #try:
            #    reactor.stop()
            #except error.ReactorNotRunning:
            #    pass
            return

        # S'il s'agit d'une erreur liée à TLS autre le manque de support
        # par le serveur, on affiche un message traduit pour aider à la
        # résolution du problème.
        tls_error = fail.check(*tls_errors.keys())
        if tls_error:
            LOGGER.error(_(tls_errors[tls_error]))

        client.XMPPClient.initializationFailed(self, fail)

    def stopService(self):
        client.XMPPClient.stopService(self)
        stops = []
        for e in self:
            if not hasattr(e, "stop"):
                continue
            d = e.stop()
            if d is not None:
                stops.append(d)
        return defer.DeferredList(stops)

    def _getConnection(self):
        if self.host:
            if isinstance(self.host, list):
                hosts = [ split_host_port(h) for h in self.host ]
                c = MultipleServerConnector(hosts, self.factory,
                                            reactor=reactor)
                c.connect()
                return c
            else:
                host, port = split_host_port(self.host)
                return reactor.connectTCP(host, port, self.factory)
        else:
            c = client.XMPPClientConnector(reactor, self.domain, self.factory)
            c.connect()
            return c


def client_factory(settings):
    from vigilo.pubsub.checknode import VerificationNode

    try:
        require_tls = settings['bus'].as_bool('require_tls')
    except KeyError:
        require_tls = False
    try:
        require_compression = settings['bus'].as_bool('require_compression')
    except KeyError:
        require_compression = False

    # Temps max entre 2 tentatives de connexion (par défaut 1 min)
    max_delay = int(settings["bus"].get("max_reconnect_delay", 60))

    host = settings['bus'].get('host')
    if host is not None:
        host = host.strip()
        if " " in host:
            host = [ h.strip() for h in host.split(" ") ]

    xmpp_client = VigiloXMPPClient(
            JID(settings['bus']['jid']),
            settings['bus']['password'],
            host,
            require_tls=require_tls,
            require_compression=require_compression,
            max_delay=max_delay)
    xmpp_client.setName('xmpp_client')

    try:
        xmpp_client.logTraffic = settings['bus'].as_bool('log_traffic')
    except KeyError:
        xmpp_client.logTraffic = False

    try:
        subscriptions = settings['bus'].as_list('subscriptions')
    except KeyError:
        try:
            # Pour la rétro-compatibilité.
            subscriptions = settings['bus'].as_list('watched_topics')
            import warnings
            warnings.warn(DeprecationWarning(_(
                'The "watched_topics" option has now been renamed into '
                '"subscriptions". Please update your configuration file.'
            )))
        except KeyError:
            subscriptions = []

    node_verifier = VerificationNode(subscriptions, doThings=True)
    node_verifier.setHandlerParent(xmpp_client)
    return xmpp_client


from twisted.internet import tcp
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
        from vigilo.common.logging import get_logger
        LOGGER = get_logger(__name__)

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


class MultipleServersXmlStreamFactory(xmlstream.XmlStreamFactory):
    """
    Sous-classée pour ré-initialiser les tentatives de connexions du connector
    lorsqu'une tentative réussit.
    """

    def buildProtocol(self, addr): # pylint: disable-msg=E0202
        """
        Ré-initialise les tentatives de connexions d'un
        L{MultipleServerConnector} lorsque l'une d'entre elles réussit.
        @param addr: an object implementing
            C{twisted.internet.interfaces.IAddress}
        """
        if (self.connector is not None
                and hasattr(self.connector, "resetAttempts")):
            self.connector.resetAttempts()
        return xmlstream.XmlStreamFactory.buildProtocol(self, addr)


from wokkel.client import HybridAuthenticator
def VigiloClientFactory(jid, password):
    """Factory pour utiliser L{MultipleServersXmlStreamFactory}"""
    a = HybridAuthenticator(jid, password)
    return MultipleServersXmlStreamFactory(a)


class DeferredMaybeTLSClientFactory(client.DeferredClientFactory):
    """
    Factory asynchrone de clients XMPP de type "one-shot",
    capable de chiffrer la connexion avec le serveur.
    """

    def __init__(self, jid, password, require_tls):
        """
        Initialiseur de la classe.

        @param jid: Identifiant Jabber du connecteur.
        @type jid: C{str}
        @param password: Mot de passe du compteur Jabber du connecteur.
        @type password: C{str}
        @param require_tls: Indique si la connexion doit être chiffrée
            (en utilisant le protocole TLS) ou non.
        @type require_tls: C{bool}
        """
        super(DeferredMaybeTLSClientFactory, self).__init__(jid, password)
        self.addBootstrap(xmlstream.STREAM_CONNECTED_EVENT, self._connected)
        self.require_tls = require_tls

    def _connected(self, xs):
        """
        On modifie dynamiquement l'attribut "required" du plugin
        d'authentification TLSInitiatingInitializer créé automatiquement
        par wokkel, pour imposer TLS si l'administrateur le souhaite.
        """
        for initializer in xs.initializers:
            if isinstance(initializer, xmlstream.TLSInitiatingInitializer):
                initializer.required = self.require_tls



class OneShotClient(object):
    """Client à usage unique"""

    def __init__(self, host, user, password, lock_file=None,
                 timeout=None, use_ssl=False):
        """
        @param user: Identifiant AMQP du client.
        @type  user: C{str}
        @param password: Mot de passe associé au compte AMQP.
        @type  password: C{str}
        @param host: le hostname du serveur AMQP (si besoin, spécifier le port
            après des deux-points)
        @type  host: C{str}
        @param lock_file: Emplacement du fichier de verrou à créer pour
            empêcher l'exécution simultanée de plusieurs instances du
            connecteur.
        @type  lock_file: C{str}
        @param timeout: Durée maximale d'exécution du connecteur,
            afin d'éviter des connecteurs "fous".
        @type  timeout: C{int}
        @param use_ssl: Indique si la connexion doit être chiffrée ou non.
        @type  use_ssl: C{bool}
        """
        from vigilo.common.logging import get_logger
        self._logger = get_logger(__name__)
        self._user = user
        self._password = password
        self._host = host
        self._lock_file = lock_file
        self._timeout = timeout
        self._use_ssl = use_ssl
        self._result = 0
        self._func = None
        self._args = ()
        self._kwargs = {}

    def _create_lockfile(self):
        """
        Cette fonction vérifie si une autre instance du connecteur est déjà
        en cours d'exécution, et arrête le connecteur si c'est le cas.
        Dans le cas contraire, elle crée un nouveau fichier de lock.

        @return: Code de retour (0 en cas de succès, une autre valeur en cas
            d'erreur).
        @rtype: C{int}
        """
        if self.lock_file is None:
            return 0
        from vigilo.common.lock import grab_lock
        self._logger.debug(_("Creating lock file in %s"), self._lock_file)
        result = grab_lock(self._lock_file)
        if result:
            self._logger.debug(
                _("Lock file successfully created in %s"),
                self._lock_file
            )
        return int(not result) # on convertit en code de retour POSIX

    def _stop(self, result, code):
        """
        Arrête proprement le connecteur, en supprimant le fichier de
        lock et en affichant un message d'erreur en cas de timeout.
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
        self._result = self._create_lockfile()
        # Si la création du fichier de verrou renvoie une erreur,
        # on propage celle-ci.
        if self._result:
            return self._result

        # Création de la factory pour le client.
        service.Application(app_name)
        factory = AmqpFactory(user=self.user, password=self.password,
                              log_traffic=log_traffic)
        # Création du client XMPP et ajout de la fonction de traitement.
        if self._host:
            host, port = split_host_port(self._host)
            reactor.connectTCP(host, port, factory)
            d = factory.deferred
        else:
            d = client.clientCreator(factory)

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
        d.addCallback(lambda _dummy: factory.stop())
        d.addCallback(self._stop, code=0)
        d.addErrback(lambda _dummy: None)

        # Garde-fou : on limite la durée de vie du connecteur.
        reactor.callLater(
            self._timeout,
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
        require_tls = False

    vigilo_client = OneShotClient(
            host=settings['bus'].get('host', 'localhost'),
            user=settings['bus'].get('user', 'guest'),
            password=settings['bus'].get('password', 'guest'),
            lock_file=settings['connector'].get('lock_file'),
            timeout=int(settings['connector'].get('timeout', 30)),
            use_ssl=use_ssl,
            )
    return vigilo_client
