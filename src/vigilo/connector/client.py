# vim: set fileencoding=utf-8 sw=4 ts=4 et :

from twisted.internet import reactor
from twisted.python import log
from twisted.words.protocols.jabber import xmlstream
from twisted.words.protocols.jabber.sasl import SASLNoAcceptableMechanism,SASLAuthError

from wokkel import client

class XMPPClient(client.XMPPClient):
    """Client XMPP Vigilo"""

    def __init__(self, *args, **kw):
        client.XMPPClient.__init__(self, *args, **kw)

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
        if failure.check(SASLNoAcceptableMechanism,SASLAuthError):
            log.err(failure, "Authentication failed:")
            reactor.stop()
            return
        client.XMPPClient.initializationFailed(self, failure)

