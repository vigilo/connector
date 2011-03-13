# -*- coding: utf-8 -*-

from collections import deque

from twisted.internet import reactor, defer
from wokkel.test.helpers import XmlStreamStub

# http://stackoverflow.com/questions/776631/using-twisteds-twisted-web-classes-how-do-i-flush-my-outgoing-buffers
def wait(seconds, result=None):
    """Returns a deferred that will be fired later"""
    d = defer.Deferred()
    reactor.callLater(seconds, d.callback, result)
    return d


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
        self.parent.transactionFactory = self.transactionFactory

    def transactionFactory(self, pool, connection):
        return LoggingTransaction(pool, connection, self)

    def __getattr__(self, name):
        return getattr(self.parent, name)
