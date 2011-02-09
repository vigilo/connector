# vim: set fileencoding=utf-8 sw=4 ts=4 et :

from twisted.internet import reactor, defer
from twisted.python import log
from twisted.words.protocols.jabber import xmlstream
from twisted.words.protocols.jabber.sasl import SASLNoAcceptableMechanism, \
                                                SASLAuthError
from twisted.words.protocols.jabber.jid import JID
from wokkel.client import XMPPClient

from vigilo.connector.compression import CompressInitiatingInitializer

from vigilo.common.gettext import translate
_ = translate(__name__)

class VigiloXMPPClient(XMPPClient):
    """Client XMPP Vigilo"""

    def __init__(self, jid, password, host=None, port=5222,
                 require_tls=False, max_delay=60):
        XMPPClient.__init__(self, jid, password, host, port)
        self.require_tls = require_tls
        self.factory.maxDelay = max_delay

    def _connected(self, xs):
        """
        On modifie dynamiquement l'attribut "required" du plugin
        d'authentification TLSInitiatingInitializer créé automatiquement
        par wokkel, pour imposer TLS si l'administrateur le souhaite, et
        insérer la compression zlib.
        """
        for index, initializer in enumerate(xs.initializers[:]):
            if isinstance(initializer, xmlstream.TLSInitiatingInitializer):
                if self.require_tls:
                    xs.initializers[index].required = True
                else:
                    # on ajoute la compression zlib et on désactive TLS
                    # (ils sont incompatibles, voir XEP-0138)
                    xs.initializers[index].wanted = False
                    xs.initializers.insert(index+1,
                            CompressInitiatingInitializer(xs))
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

        from vigilo.common.gettext import translate, translate_narrow
        _ = translate(__name__)
        N_ = translate(__name__)

        if failure.check(SASLNoAcceptableMechanism, SASLAuthError):
            LOGGER.error(_("Authentication failure: %s"),
                         failure.getErrorMessage())
            reactor.stop()
            return
        if failure.check(xmlstream.FeatureNotAdvertized):
            LOGGER.error(_("Server does not support TLS encryption."))
            log.err(failure, N_("Server does not support TLS encryption."))
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

def client_factory(settings):
    from vigilo.pubsub.checknode import VerificationNode

    try:
        require_tls = settings['bus'].as_bool('require_tls')
    except KeyError:
        require_tls = False

    # Temps max entre 2 tentatives de connexion (par défaut 1 min)
    max_delay = int(settings["bus"].get("max_reconnect_delay", 60))

    xmpp_client = VigiloXMPPClient(
            JID(settings['bus']['jid']),
            settings['bus']['password'],
            settings['bus']['host'],
            require_tls=require_tls,
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


