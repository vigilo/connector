# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2013 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

from pkg_resources import resource_filename

from twisted.internet import protocol
from twisted.python import failure

from txamqp.protocol import AMQClient
from txamqp.client import TwistedDelegate
from txamqp import spec

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

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
    if isinstance(error, Exception):
        error = error.args[0]
    try:
        try:
            return unicode(error.fields[1])
        except (UnicodeEncodeError, UnicodeDecodeError):
            return error.fields[1].decode('utf-8')
    except (KeyError, AttributeError, IndexError,
            UnicodeEncodeError, UnicodeDecodeError):
        return get_error_message(error)


class AmqpProtocol(AMQClient):
    """
    The protocol is created and destroyed each time a connection is created and
    lost.
    """

    def __init__(self, *args, **kwargs):
        AMQClient.__init__(self, *args, **kwargs)
        self.factory = None
        self.logTraffic = False

    def connectionMade(self):
        AMQClient.connectionMade(self)
        # Authenticate.
        assert self.factory is not None
        deferred = self.start({"LOGIN": self.factory.user,
                               "PASSWORD": self.factory.password})
        deferred.addCallbacks(self._authenticated, self._authentication_failed)


    def _authenticated(self, _ignore, channum=1):
        """Called when the connection has been authenticated."""
        # Get a channel.
        d = self.channel(channum)
        d.addCallback(self._got_channel)
        d.addErrback(self._got_channel_failed)
        return d


    def _got_channel(self, channel):
        d = channel.channel_open()
        d.addCallback(self._channel_open, channel)
        d.addErrback(self._channel_open_failed)
        return d


    def _channel_open(self, _ignore, channel):
        """Called when the channel is open."""
        self.factory.connectionInitialized(channel)


    def _channel_open_failed(self, error):
        LOGGER.warning(_("Channel open failed: %s"), getErrorMessage(error))


    def _got_channel_failed(self, error):
        LOGGER.warning(_("Error getting channel: %s"), getErrorMessage(error))


    def _authentication_failed(self, error):
        LOGGER.warning(_("AMQP authentication failed: %s"),
                       getErrorMessage(error))

    def channelFailed(self, channel, reason):
        LOGGER.warning(_("Channel %(id)d was unexpectedly closed, disconnecting. "
                         "Reason: %(reason)s"),
                       {"id": channel.id, "reason": getErrorMessage(reason)})
        self.transport.loseConnection()



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
        """
        Redéfini pour gérer la variable logTraffic et pour stocker le protocole
        créé.

        @param addr: un objet qui implémente
            C{twisted.internet.interfaces.IAddress}
        """
        p = self.protocol(self.delegate, self.vhost, self.spec)
        p.factory = self # Tell the protocol about this factory.
        p.logTraffic = self.logTraffic
        self.p = p # Store the protocol.
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
        # Reset the reconnection delay since we're connected now.
        self.resetDelay()

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
        # Sous RabbitMQ 3.0.x, le fait d'appeler connection_close()
        # sur le canal ne suffit plus à fermer la connexion
        # (comportement constaté avec 3.0.0 et 3.0.1 sous Debian Squeeze).
        d.addCallback(lambda _r: self.p.transport.loseConnection())
        return d
