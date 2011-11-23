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


    def _got_channel(self, chan):
        self.chan = chan
        d = self.chan.channel_open()
        d.addCallback(self._channel_open)
        d.addErrback(self._channel_open_failed)


    def _channel_open(self, arg):
        """Called when the channel is open."""
        # Flag that the connection is open.
        self.connected = True

        # Now that the channel is open add any readers the user has specified.
        for l in self.factory.read_list:
            self._subscribe(l[0], l[1], l[2])

        # Send any messages waiting to be sent.
        self.send()

        # Fire the factory's 'initial connect' deferred if it hasn't already
        if not self.factory.deferred.called:
            self.factory.deferred.callback(self)


    def subscribe(self, queue, exchange, routing_key, callback):
        """Add an exchange to the list of exchanges to read from."""
        if self.connected:
            # Connection is already up. Add the reader.
            self._subscribe(exchange, routing_key, callback)
        else:
            # Connection is not up. _channel_open will add the reader when the
            # connection is up.
            pass


    @defer.inlineCallbacks
    def send(self):
        """If connected, send all waiting messages."""
        if not self.connected:
            return

        while len(self.factory.queued_messages) > 0:
            m = self.factory.queued_messages.pop(0)
            yield self._send_message(m[0], m[1], m[2])


    @defer.inlineCallbacks
    def _subscribe(self, queue, exchange, routing_key, callback):
        """This function does the work to read from an exchange."""
        queue = exchange # For now use the exchange name as the queue name.
        consumer_tag = exchange # Use the exchange name for the consumer tag for now.

        # Declare the exchange in case it doesn't exist.
        #yield self.chan.exchange_declare(exchange=exchange, type="direct",
        #                                 durable=True, auto_delete=False)
        yield self.chan.exchange_declare(exchange=exchange, type="direct",
                                         durable=False, auto_delete=True)

        # Declare the queue and bind to it.
        yield self.chan.queue_declare(queue=queue, durable=True,
                                      exclusive=False, auto_delete=False)
        yield self.chan.queue_bind(queue=queue, exchange=exchange,
                                   routing_key=routing_key)

        # Consume.
        yield self.chan.basic_consume(queue=queue, no_ack=True,
                                      consumer_tag=consumer_tag)
        queue = yield self.queue(consumer_tag)

        # Now setup the readers.
        d = queue.get()
        d.addCallback(self._read_item, queue, callback)
        d.addErrback(self._read_item_err)


    def _channel_open_failed(self, error):
        log.msg("Channel open failed: %s" % error)


    def _got_channel_failed(self, error):
        log.msg("Error getting channel: %s" % error)


    def _authentication_failed(self, error):
        log.msg("AMQP authentication failed: %s" % error)


    def _send_message(self, exchange, routing_key, msg):
        """Send a single message."""
        # First declare the exchange just in case it doesn't exist.
        #yield self.chan.exchange_declare(exchange=exchange, type="direct",
        #                                 durable=True, auto_delete=False)
        d = self.chan.exchange_declare(exchange=exchange, type="direct",
                                       durable=False, auto_delete=True)

        def _send(_, exchange, routing_key, msg):
            msg = Content(msg)
            msg["delivery mode"] = 2 # 2 = persistent delivery.
            print exchange, routing_key, msg
            d_send = self.chan.basic_publish(exchange=exchange,
                            routing_key=routing_key, content=msg)
            d_send.addErrback(self._send_message_err)
            return d_send

        d.addCallback(_send, exchange, routing_key, msg)
        return d


    def _send_message_err(self, error):
        log.err("Sending message failed", error)


    def _read_item(self, item, queue, callback):
        """Callback function which is called when an item is read."""
        # Setup another read of this queue.
        d = queue.get()
        d.addCallback(self._read_item, queue, callback)
        d.addErrback(self._read_item_err)

        # Process the read item by running the callback.
        callback(item)


    def _read_item_err(self, error):
        log.err("Error reading item: ", error)



class AmqpFactory(protocol.ReconnectingClientFactory):
    protocol = AmqpProtocol


    def __init__(self, user, password, vhost=None, log_traffic=False):
        self.user = user
        self.password = password
        self.vhost = vhost or '/'
        self.log_traffic = log_traffic
        spec_file = resource_filename('vigilo.connector', 'amqp0-8.xml')
        self.spec = spec.load(spec_file)
        self.delegate = TwistedDelegate()
        self.deferred = defer.Deferred()

        self.p = None # The protocol instance.
        self.client = None # Alias for protocol instance

        self.queued_messages = [] # List of messages waiting to be sent.
        self.read_list = [] # List of queues to listen on.


    def buildProtocol(self, addr):
        p = self.protocol(self.delegate, self.vhost, self.spec)
        p.factory = self # Tell the protocol about this factory.
        p.logTraffic = self.log_traffic

        self.p = p # Store the protocol.
        self.client = p

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
        protocol.ReconnectingClientFactory.clientConnectionFailed(
                self, connector, reason)


    def stop(self):
        self.stopTrying()
        if self.p is None:
            return
        d = self.p.chan.channel_close()
        d.addCallback(lambda _r: self.p.channel(0))
        d.addCallback(lambda ch: ch.connection_close())
        d.addCallback(lambda _r: self.p.close("quit"))
        return d


    def send_message(self, exchange=None, routing_key=None, msg=None):
        # Add the new message to the queue.
        self.queued_messages.append((exchange, routing_key, msg))
        # This tells the protocol to send all queued messages.
        if self.p != None:
            return self.p.send()


    def read(self, exchange=None, routing_key=None, callback=None):
        """Configure an exchange to be read from."""
        assert(exchange != None and routing_key != None and callback != None)

        # Add this to the read list so that we have it to re-add if we lose the
        # connection.
        self.read_list.append((exchange, routing_key, callback))

        # Tell the protocol to read this if it is already connected.
        if self.p != None:
            self.p.read(exchange, routing_key, callback)



