# vim: set fileencoding=utf-8 sw=4 ts=4 et :

from twisted.internet import reactor, defer
from twisted.python import log
from twisted.words.protocols.jabber import xmlstream
from twisted.words.protocols.jabber.sasl import SASLNoAcceptableMechanism, \
                                                SASLAuthError
from twisted.words.protocols.jabber.jid import JID
from wokkel.client import XMPPClient, XMPPClientConnector

from vigilo.connector.compression import CompressInitiatingInitializer

from vigilo.common.gettext import translate
_ = translate(__name__)


class VigiloXMPPClient(XMPPClient):
    """Client XMPP Vigilo"""

    def __init__(self, jid, password, host=None, port=5222,
                 require_tls=False, require_compression=False, max_delay=60):
        XMPPClient.__init__(self, jid, password, host, port)
        self.require_tls = require_tls
        self.require_compression = require_compression
        self.factory.maxDelay = max_delay
        if isinstance(self.host, list):
            factory = VigiloClientFactory(jid, password)

    def _connected(self, xs):
        """
        On modifie dynamiquement l'attribut "required" du plugin
        d'authentification TLSInitiatingInitializer créé automatiquement
        par wokkel, pour imposer TLS si l'administrateur le souhaite, et
        insérer la compression zlib.
        """
        for index, initializer in enumerate(xs.initializers[:]):
            if isinstance(initializer, xmlstream.TLSInitiatingInitializer):
                if self.require_tls and not self.require_compression:
                    xs.initializers[index].required = True
                if self.require_compression and not self.require_tls:
                    # on ajoute la compression zlib et on désactive TLS
                    # (ils sont incompatibles, voir XEP-0138)
                    xs.initializers[index].wanted = False
                    xs.initializers.insert(index+1,
                            CompressInitiatingInitializer(xs))
                if self.require_compression and self.require_tls:
                    from vigilo.common.logging import get_logger
                    LOGGER = get_logger(__name__)
                    from vigilo.common.gettext import translate
                    _ = translate(__name__)
                    LOGGER.warning(
                        _("'require_tls' do compression. 'require_compression'"
                        " option is ignored when both options are True.")
                        )
                    xs.initializers[index].required = True

        XMPPClient._connected(self, xs)

    def _disconnected(self, xs):
        """
        Ajout de l'arrêt à la déconnexion
        @TODO: vérifier que ça ne bloque pas la reconnexion automatique.
        """
        XMPPClient._disconnected(self, xs)

    def initializationFailed(self, failure):
        """
        Appelé si l'initialisation échoue. Ici, on ajoute la gestion de
        l'erreur d'authentification.
        """
        from vigilo.common.logging import get_logger
        LOGGER = get_logger(__name__)

        from vigilo.common.gettext import translate
        _ = translate(__name__)

        if failure.check(SASLNoAcceptableMechanism, SASLAuthError):
            LOGGER.error(_("Authentication failure: %s"),
                         failure.getErrorMessage())
            reactor.stop()
            return
        if failure.check(xmlstream.FeatureNotAdvertized):
            LOGGER.error(_("Server does not support TLS encryption."))
            reactor.stop()
            return
        XMPPClient.initializationFailed(self, failure)

    def stopService(self):
        XMPPClient.stopService(self)
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
                c = MultipleServerConnector(self.host, self.port, self.factory,
                                            reactor=reactor)
                c.connect()
                return c
            else:
                return reactor.connectTCP(self.host, self.port, self.factory)
        else:
            c = XMPPClientConnector(reactor, self.domain, self.factory)
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
        require_compression= False

    # Temps max entre 2 tentatives de connexion (par défaut 1 min)
    max_delay = int(settings["bus"].get("max_reconnect_delay", 60))

    host = settings['bus']['host'].strip()
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
    def __init__(self, hosts, port, factory, timeout=30, attempts=3,
                 reactor=None):
        tcp.Connector.__init__(self, None, port, factory, timeout, None,
                               reactor=reactor)
        self.hosts = hosts
        self.attempts = attempts
        self._attemptsLeft = attempts
        self._usableHosts = None

    def pickServer(self):
        if not self._usableHosts:
            self._usableHosts = self.hosts[:]
        self.host = self._usableHosts[0]
        log.msg("Connecting to %s" % self.host)

    def connectionFailed(self, reason):
        assert self._attemptsLeft is not None
        self._attemptsLeft -= 1
        if self._attemptsLeft == 0:
            self._usableHosts.remove(self.host)
            self.resetAttempts()
            if hasattr(self.factory, "resetDelay"):
                self.factory.resetDelay()
        return tcp.Connector.connectionFailed(self, reason)

    def resetAttempts(self):
        self._attemptsLeft = self.attempts

    def _makeTransport(self):
        self.pickServer()
        return tcp.Connector._makeTransport(self)

#from twisted.internet import protocol
#class MultipleServersClientFactory(protocol.ReconnectingClientFactory):
#    def resetDelay(self):
#        if self.connector is not None:
#            self.connector.resetAttempts()
#        return protocol.ReconnectingClientFactory.resetDelay(self)
#
#from twisted.words.xish.xmlstream import XmlStream, XmlStreamFactoryMixin
#class MultipleServersXmlStreamFactory(XmlStreamFactoryMixin,
#                                      MultipleServersClientFactory):
#    protocol = XmlStream
#
#    def buildProtocol(self, addr):
#        self.resetDelay()
#        return XmlStreamFactoryMixin.buildProtocol(self, addr)

from twisted.words.xish.xmlstream import XmlStreamFactory
class MultipleServersXmlStreamFactory(XmlStreamFactory):
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
        return XmlStreamFactory.buildProtocol(self, addr)

from wokkel.client import HybridAuthenticator
def VigiloClientFactory(jid, password):
    """Factory pour utiliser L{MultipleServersXmlStreamFactory}"""
    a = HybridAuthenticator(jid, password)
    return MultipleServersXmlStreamFactory(a)

