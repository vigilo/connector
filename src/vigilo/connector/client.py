# vim: set fileencoding=utf-8 sw=4 ts=4 et :

from twisted.internet import reactor
from twisted.python import log
from twisted.words.protocols.jabber import xmlstream
from twisted.words.protocols.jabber.sasl import SASLNoAcceptableMechanism, \
                                                SASLAuthError
from twisted.words.protocols.jabber.jid import JID
from wokkel import client

from vigilo.common.gettext import translate
_ = translate(__name__)

class XMPPClient(client.XMPPClient):
    """Client XMPP Vigilo"""

    def __init__(self, jid, password, host=None, port=5222, require_tls=False):
        self.require_tls = require_tls
        client.XMPPClient.__init__(self, jid, password, host, port)

    def _connected(self, xs):
        """
        On modifie dynamiquement l'attribut "required" du plugin
        d'authentification TLSInitiatingInitializer créé automatiquement
        par wokkel, pour imposer TLS si l'administrateur le souhaite.
        """
        for initializer in xs.initializers:
            if isinstance(initializer, xmlstream.TLSInitiatingInitializer):
                initializer.required = self.require_tls
        client.XMPPClient._connected(self, xs)

    def _disconnected(self, xs):
        """
        Ajout de l'arrêt à la déconnexion
        @TODO: vérifier que ça ne bloque pas la reconnexion automatique.
        """
        client.XMPPClient._disconnected(self, xs)

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
            LOGGER.error(_("Authentication failure."))
            log.err(failure, _("Authentication failed:"))
            reactor.stop()
            return
        if failure.check(xmlstream.FeatureNotAdvertized):
            LOGGER.error(_("Server does not support TLS encryption."))
            log.err(failure, _("Server does not support TLS encryption."))
            reactor.stop()
            return
        client.XMPPClient.initializationFailed(self, failure)


def client_factory(settings):
    from vigilo.pubsub.checknode import VerificationNode

    try:
        require_tls = settings['bus'].as_bool('require_tls')
    except KeyError:
        require_tls = False

    xmpp_client = XMPPClient(
            JID(settings['bus']['jid']),
            settings['bus']['password'],
            settings['bus']['host'],
            require_tls = require_tls)
    xmpp_client.setName('xmpp_client')
    # Temps max entre 2 tentatives de connexion (par défaut 1 min)
    xmpp_client.factory.maxDelay = int(settings["bus"].get(
                                       "max_reconnect_delay", 60))

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
                'The "watched_topics" option has now been renamed '
                'into "subscriptions"'
            )))
        except KeyError:
            subscriptions = []

    node_verifier = VerificationNode(subscriptions, doThings=True)
    node_verifier.setHandlerParent(xmpp_client)
    return xmpp_client
