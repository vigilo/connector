# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

from pkg_resources import resource_filename

from twisted.internet import protocol
from twisted.python import log, failure

from txamqp.protocol import AMQClient
from txamqp.client import TwistedDelegate
from txamqp import spec

from vigilo.common.gettext import translate
_ = translate(__name__)

from vigilo.common.logging import get_error_message


NON_PERSISTENT = 1
PERSISTENT = 2


def getErrorMessage(error):
    """
    Retourne le message renvoyé par le serveur dans une exception
    C{txamqp.client.Closed}
    """
    if isinstance(error, failure.Failure):
        error = error.value
    try:
        try:
            return unicode(error.args[0].fields[1])
        except (UnicodeEncodeError, UnicodeDecodeError):
            return str(error.args[0].fields[1].decode('utf-8'))
    except (KeyError, AttributeError, IndexError,
            UnicodeEncodeError, UnicodeDecodeError):
        return get_error_message(error)


class AmqpProtocol(AMQClient):
    """
    The protocol is created and destroyed each time a connection is created and
    lost.
    """

    def connectionMade(self):
        AMQClient.connectionMade(self)
        # Flag that this protocol is not connected yet.
        self.connected = False
        # Authenticate.
        deferred = self.start({"LOGIN": self.factory.user,
                               "PASSWORD": self.factory.password})
        deferred.addCallbacks(self._authenticated, self._authentication_failed)


    def _authenticated(self, ignore):
        """Called when the connection has been authenticated."""
        # Get a channel.
        d = self.channel(1)
        d.addCallback(self._got_channel)
        d.addErrback(self._got_channel_failed)


    def _got_channel(self, channel):
        d = channel.channel_open()
        d.addCallback(self._channel_open, channel)
        d.addErrback(self._channel_open_failed)


    def _channel_open(self, _ignore, channel):
        """Called when the channel is open."""
        self.factory.connectionInitialized(channel)


    def _channel_open_failed(self, error):
        log.msg("Channel open failed: %s" % error)


    def _got_channel_failed(self, error):
        log.msg("Error getting channel: %s" % error)


    def _authentication_failed(self, error):
        log.msg("AMQP authentication failed: %s" % getErrorMessage(error))



class AmqpFactory(protocol.ReconnectingClientFactory):

    protocol = AmqpProtocol

    def __init__(self, parent, user, password, vhost=None, logTraffic=False):
        self.parent = parent
        self.user = user
        self.password = password
        self.vhost = vhost or '/'
        self.logTraffic = logTraffic
        spec_file = resource_filename('vigilo.connector', 'amqp0-9-1.xml')
        self.spec = spec.load(spec_file)
        self.delegate = TwistedDelegate()
        self.handlers = []

        self.p = None # The protocol instance.
        self.channel = None # The main channel


    def buildProtocol(self, addr):
        p = self.protocol(self.delegate, self.vhost, self.spec)
        p.factory = self # Tell the protocol about this factory.
        p.logTraffic = self.logTraffic

        self.p = p # Store the protocol.

        # Reset the reconnection delay since we're connected now.
        self.resetDelay()

        return p


    def clientConnectionLost(self, connector, reason):
        #log.msg("Client connection lost.")
        self.p = None
        self.channel = None
        self.parent.channel = None
        protocol.ReconnectingClientFactory.clientConnectionLost(
                self, connector, reason)
        self.parent.connectionLost(reason)


    def connectionInitialized(self, channel):
        """
        Send out cached stanzas and call each handler's
        C{connectionInitialized} method.
        """
        self.channel = channel
        self.parent.channel = channel
        self.parent.connectionInitialized()


    def stop(self):
        self.stopTrying()
        if self.p is None:
            return
        if self.channel is None:
            return
        d = self.channel.channel_close()
        d.addCallback(lambda _r: self.p.channel(0))
        d.addCallback(lambda ch: ch.connection_close())
        d.addCallback(lambda _r: self.p.close("quit"))
        return d
