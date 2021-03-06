# -*- coding: utf-8 -*-
# Copyright (C) 2006-2020 CS GROUP - France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

from collections import deque

from twisted.internet import reactor, defer
from nose.plugins.skip import SkipTest
from txamqp.queue import TimeoutDeferredQueue
from vigilo.connector.client import VigiloClient


# http://stackoverflow.com/questions/776631/using-twisteds-twisted-web-classes-how-do-i-flush-my-outgoing-buffers
def wait(seconds, result=None):
    """Returns a deferred that will be fired later"""
    d = defer.Deferred()
    reactor.callLater(seconds, d.callback, result)
    return d


class ReplyStub(object):
    def __init__(self, consumer_tag):
        self.consumer_tag = consumer_tag


class ChannelStub(object):


    def __init__(self):
        self.sent = []
        self.queues = {}


    def receive(self, message):
        pass


    def basic_publish(self, exchange, routing_key, content, immediate=False):
        # pylint: disable-msg=W0613
        # W0613: Unused argument 'immediate'
        self.sent.append( {
            "method": "basic_publish",
            "exchange": exchange,
            "routing_key": routing_key,
            "content": content,
            })
        return defer.succeed(None)


    def queue_declare(self, queue, durable, exclusive, auto_delete, arguments):
        self.sent.append( {
            "method": "queue_declare",
            "queue": queue,
            "durable": durable,
            "exclusive": exclusive,
            "auto_delete": auto_delete,
            "arguments": arguments,
            })
        self.queues[queue] = TimeoutDeferredQueue()
        return defer.succeed(None)


    def basic_consume(self, queue, consumer_tag):
        self.sent.append( {
            "method": "basic_consume",
            "queue": queue,
            "consumer_tag": consumer_tag,
            })
        reply = ReplyStub(consumer_tag)
        return defer.succeed(reply)


    def basic_ack(self, delivery_tag, multiple):
        self.sent.append( {
            "method": "basic_ack",
            "delivery_tag": delivery_tag,
            "multiple": multiple,
            })
        return defer.succeed(None)


    def basic_qos(self, prefetch_count=0, prefetch_size=0):
        self.sent.append( {
            "method": "basic_qos",
            "prefetch_count": prefetch_count,
            "prefetch_size": prefetch_size,
            })
        return defer.succeed(None)



class ClientStub(VigiloClient):


    def stub_connect(self):
        self.channel = ChannelStub()
        return self.connectionInitialized()


    def stub_receive(self, message, queue=None):
        assert (queue is not None or len(self.channel.queues) == 1)
        if queue is None and len(self.channel.queues) == 1:
            queue = self.channel.queues.keys()[0]
        self.channel.queues[queue].put(message)
        return defer.succeed(None)


    def getQueue(self, *args, **kwargs):
        return self.channel.queues[args[0]]



class ConsumerStub(object):

    def __init__(self):
        self.written = []
        self.connected = True

    def write(self, data):
        self.written.append(data)

    def isConnected(self):
        return self.connected



from twisted.enterprise.adbapi import Transaction
class LoggingTransaction(Transaction):

    def __init__(self, pool, connection, parent):
        Transaction.__init__(self, pool, connection)
        self.parent = parent

    def execute(self, *args, **kw):
        self.parent.requests.append( (args, kw) )
        return self._cursor.execute(*args, **kw)

    def executemany(self, *args, **kw):
        self.parent.requests.append( (args, kw) )
        return self._cursor.executemany(*args, **kw)


class ConnectionPoolStub(object):
    """Wrapper pour ConnectionPool"""

    def __init__(self, parent):
        self.requests = deque()
        self.parent = parent
        if not hasattr(self.parent, "transactionFactory"):
            raise SkipTest # twisted < 8.2
        self.parent.transactionFactory = self.transactionFactory

    def transactionFactory(self, pool, connection):
        return LoggingTransaction(pool, connection, self)

    def __getattr__(self, name):
        return getattr(self.parent, name)
