# -*- coding: utf-8 -*-

from twisted.internet import reactor, defer
from wokkel.test.helpers import XmlStreamStub

# http://stackoverflow.com/questions/776631/using-twisteds-twisted-web-classes-how-do-i-flush-my-outgoing-buffers
def wait(seconds, result=None):
    """Returns a deferred that will be fired later"""
    d = defer.Deferred()
    reactor.callLater(seconds, d.callback, result)
    return d
