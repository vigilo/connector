# vim: set fileencoding=utf-8 sw=4 ts=4 et :

"""
Extends pubsub clients to compute Node message.
"""
from __future__ import absolute_import

from twisted.internet import protocol
from twisted.internet import reactor
from twisted.python.failure import Failure

from vigilo.common.logging import get_logger
from vigilo.connector.forwarder import PubSubListener, NotConnectedError

LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate
_ = translate(__name__)


class SocketNotConnectedError(NotConnectedError):
    def __str__(self):
        return _('socket not connected')

class NodeToSocketForwarder(PubSubListener, protocol.Protocol):
    """
    Receives messages on the xmpp bus, and passes them to the socket.
    Forward Node to socket.
    """

    def __init__(self, socket_filename, dbfilename, dbtable):
        """
        Instancie un connecteur BUS XMPP vers socket.

        @param socket_filename: le nom du fichier socket qui accueillra les
        messages du BUS XMPP
        @type socket_filename: C{str}
        @param dbfilename: le nom du fichier permettant la sauvegarde des
        messages en cas de problème d'éciture sur le pipe
        @type dbfilename: C{str}
        @param dbtable: Le nom de la table SQL dans ce fichier.
        @type dbtable: C{str}
        """
        super(NodeToSocketForwarder, self).__init__(dbfilename, dbtable)
        # using ReconnectingClientFactory with a backoff retry
        # (it tries again and again with a delay increasing between attempts)
        self.__factory = protocol.ReconnectingClientFactory()
        self.__factory.buildProtocol = self.buildProtocol
        # creation socket
        self._socket = reactor.connectUNIX(socket_filename, self.__factory,
                                           timeout=3, checkPID=0)

    def connectionMade(self):
        """Called when a connection is made.

        This may be considered the initializer of the protocol, because
        it is called when the connection is completed.  For clients,
        this is called once the connection to the server has been
        established; for servers, this is called after an accept() call
        stops blocking and a socket has been received.  If you need to
        send any greeting or initial message, do it here.
        """
        # reset the reconnecting delay after a succesfull connection
        self.__factory.resetDelay()

    def buildProtocol(self, addr):
        """ Create an instance of a subclass of Protocol. """
        return self

    def isConnected(self):
        return self._socket.state == 'connected'

    def processMessage(self, msg):
        if self.isConnected():
            self._socket.transport.write(msg + '\n')
        else:
            self._send_failed(Failure(SocketNotConnectedError()), msg)

