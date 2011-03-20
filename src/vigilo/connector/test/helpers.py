# -*- coding: utf-8 -*-

from collections import deque

from twisted.internet import reactor, defer
from twisted.words.protocols.jabber.jid import JID
from wokkel.test.helpers import XmlStreamStub as WXSS
from nose.plugins.skip import SkipTest


# http://stackoverflow.com/questions/776631/using-twisteds-twisted-web-classes-how-do-i-flush-my-outgoing-buffers
def wait(seconds, result=None):
    """Returns a deferred that will be fired later"""
    d = defer.Deferred()
    reactor.callLater(seconds, d.callback, result)
    return d


from twisted.words.xish import domish
class XmlStreamStub(WXSS):

    def send_replies(self):
        for sent in self.output:
            reply = self._build_reply(sent)
            self.send(reply)

    def _build_reply(self, message):
        reply = domish.Element((None, "iq"))
        reply["type"] = "result"
        reply["from"] = message["to"]
        reply["id"] = message["id"]
        reply_pubsub = domish.Element(
                ("http://jabber.org/protocol/pubsub", "pubsub"))
        reply.addChild(reply_pubsub)
        reply_publish = domish.Element((None, "publish"))
        reply_pubsub.addChild(reply_publish)
        reply_publish["node"] = message.pubsub.publish["node"]
        reply_item = domish.Element((None, "item"))
        reply_publish.addChild(reply_item)
        reply_item["id"] = "ABCDEF0123456789" # TODO
        return reply


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


class HandlerStub(object):
    jid = JID("jid@example.com")
    def __init__(self, xmlstream):
        self.xmlstream = xmlstream
    def addHandler(self, dummy):
        pass
    def removeHandler(self, dummy):
        pass
    def send(self, obj):
        self.xmlstream.send(obj)

