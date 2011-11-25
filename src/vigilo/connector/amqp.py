# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import os, sys

from pkg_resources import resource_filename

from twisted.internet import reactor, defer, error, protocol
from twisted.application import service
from twisted.python import log, failure

from txamqp.protocol import AMQClient
from txamqp.client import TwistedDelegate
from txamqp.content import Content
from txamqp import spec

from vigilo.common.gettext import translate, l_
_ = translate(__name__)



NON_PERSISTENT = 1
PERSISTENT = 2



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
        deferred.addCallback(self._authenticated)
        deferred.addErrback(self._authentication_failed)


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
        log.msg("AMQP authentication failed: %s" % error)


    #def subscribe(self, queue, exchange, routing_key, callback):
    #    """Add an exchange to the list of exchanges to read from."""
    #    if self.connected:
    #        # Connection is already up. Add the reader.
    #        self._subscribe(exchange, routing_key, callback)
    #    else:
    #        # Connection is not up. _channel_open will add the reader when the
    #        # connection is up.
    #        pass


    #@defer.inlineCallbacks
    #def _subscribe(self, queue, exchange, routing_key, callback):
    #    """This function does the work to read from an exchange."""
    #    queue = exchange # For now use the exchange name as the queue name.
    #    consumer_tag = exchange # Use the exchange name for the consumer tag for now.

    #    # Declare the exchange in case it doesn't exist.
    #    #yield self.chan.exchange_declare(exchange=exchange, type="direct",
    #    #                                 durable=True, auto_delete=False)
    #    yield self.chan.exchange_declare(exchange=exchange, type="direct",
    #                                     durable=False, auto_delete=True)

    #    # Declare the queue and bind to it.
    #    yield self.chan.queue_declare(queue=queue, durable=True,
    #                                  exclusive=False, auto_delete=False)
    #    yield self.chan.queue_bind(queue=queue, exchange=exchange,
    #                               routing_key=routing_key)

    #    # Consume.
    #    yield self.chan.basic_consume(queue=queue, no_ack=True,
    #                                  consumer_tag=consumer_tag)
    #    queue = yield self.queue(consumer_tag)

    #    # Now setup the readers.
    #    d = queue.get()
    #    d.addCallback(self._read_item, queue, callback)
    #    d.addErrback(self._read_item_err)


    #def _read_item(self, item, queue, callback):
    #    """Callback function which is called when an item is read."""
    #    # Setup another read of this queue.
    #    d = queue.get()
    #    d.addCallback(self._read_item, queue, callback)
    #    d.addErrback(self._read_item_err)

    #    # Process the read item by running the callback.
    #    callback(item)


    #def _read_item_err(self, error):
    #    log.err("Error reading item: ", error)



class AmqpFactory(protocol.ReconnectingClientFactory):

    protocol = AmqpProtocol

    def __init__(self, user, password, vhost=None, logTraffic=False):
        self.user = user
        self.password = password
        self.vhost = vhost or '/'
        self.logTraffic = logTraffic
        spec_file = resource_filename('vigilo.connector', 'amqp0-8.xml')
        self.spec = spec.load(spec_file)
        self.delegate = TwistedDelegate()
        self.deferred = defer.Deferred()
        self.handlers = []

        self.p = None # The protocol instance.
        self.channel = None # The main channel

        self._packetQueue = [] # List of messages waiting to be sent.


    def addHandler(self, handler):
        self.handlers.append(handler)
        # get protocol handler up to speed when a connection has already
        # been established
        if self.channel:
            handler.connectionInitialized(self.channel)


    def removeHandler(self, handler):
        self.handlers.remove(handler)


    def buildProtocol(self, addr):
        p = self.protocol(self.delegate, self.vhost, self.spec)
        p.factory = self # Tell the protocol about this factory.
        p.logTraffic = self.logTraffic

        self.p = p # Store the protocol.

        # Reset the reconnection delay since we're connected now.
        self.resetDelay()

        return p


    def clientConnectionFailed(self, connector, reason):
        log.msg("Connection failed.")
        protocol.ReconnectingClientFactory.clientConnectionLost(
                self, connector, reason)


    def clientConnectionLost(self, connector, reason):
        log.msg("Client connection lost.")
        self.p = None
        self.channel = None
        protocol.ReconnectingClientFactory.clientConnectionFailed(
                self, connector, reason)
        # Notify all child services
        for e in self.handlers:
            if hasattr(e, "connectionLost"):
                e.connectionLost(reason)



    def connectionInitialized(self, channel):
        """
        Send out cached stanzas and call each handler's
        C{connectionInitialized} method.
        """
        self.channel = channel
        # Flush all pending packets
        d = self._sendPacketQueue()
        def doneSendingQueue(_ignore):
            # Trigger the deferred
            if not self.deferred.called:
                self.deferred.callback(self)
            # Notify all child services
            for e in self.handlers:
                if hasattr(e, "connectionInitialized"):
                    e.connectionInitialized(channel)
        d.addCallback(doneSendingQueue)


    @defer.inlineCallbacks
    def _sendPacketQueue(self, _ignore=None):
        while self._packetQueue:
            e, k, m = self._packetQueue.pop(0)
            yield self.send(e, k, m)


    def send(self, exchange, routing_key, message):
        if self.channel:
            msg = Content(message)
            msg["delivery mode"] = PERSISTENT
            d = self.channel.basic_publish(exchange=exchange,
                            routing_key=routing_key, content=msg)
            d.addErrback(self._sendFailed)
            return d
        else:
            self._packetQueue.append( (exchange, routing_key, message) )
            return defer.succeed(None)


    def _sendFailed(self, fail):
        log.err(fail)
        return fail


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


    def read(self, exchange=None, routing_key=None, callback=None):
        """Configure an exchange to be read from."""
        assert(exchange != None and routing_key != None and callback != None)

        # Add this to the read list so that we have it to re-add if we lose the
        # connection.
        self.read_list.append((exchange, routing_key, callback))

        # Tell the protocol to read this if it is already connected.
        if self.p != None:
            self.p.read(exchange, routing_key, callback)



