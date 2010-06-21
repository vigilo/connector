# vim: set fileencoding=utf-8 sw=4 ts=4 et :

from twisted.internet import reactor
from twisted.python import log
from twisted.words.protocols.jabber import xmlstream
from twisted.words.protocols.jabber.sasl import SASLNoAcceptableMechanism, \
                                                SASLAuthError

from wokkel import client

class XMPPClient(client.XMPPClient):
    """Client XMPP Vigilo"""

    def __init__(self, jid, password, host=None, port=5222, require_tls=False):
        self.require_tls = require_tls
        client.XMPPClient.__init__(self, jid, password, host, port)

    def _connected(self, xs):
        # On modifie dynamiquement l'attribut "required" du plugin
        # d'authentification TLSInitiatingInitializer créé automatiquement
        # par wokkel, pour imposer TLS si l'administrateur le souhaite.
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
        if failure.check(SASLNoAcceptableMechanism, SASLAuthError):
            log.err(failure, "Authentication failed:")
            reactor.stop()
            return
        client.XMPPClient.initializationFailed(self, failure)

