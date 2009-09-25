# vim: set fileencoding=utf-8 sw=4 ts=4 et :

"""
Extends pubsub clients to compute Node message.
"""
from __future__ import absolute_import

import twisted.internet.protocol
from twisted.internet import reactor

from vigilo.common.logging import get_logger
from vigilo.pubsub import  NodeSubscriber
from vigilo.connector.store import unstoremessage, storemessage, \
        initializeDB, sqlitevacuumDB
import os
from wokkel.pubsub import PubSubClient
from wokkel import xmppim

LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate
_ = translate(__name__)


#class NodeToSocketForwarder(NodeSubscriber, twisted.internet.protocol.Protocol):
class NodeToSocketForwarder(PubSubClient, twisted.internet.protocol.Protocol):
    """
    Receives messages on the xmpp bus, and passes them to the socket.
    Forward Node to socket.
    """
    def connectionInitialized(self):
        # Called when we are connected and authenticated
        #super(NodeSubscriber, self).connectionInitialized()
        PubSubClient.connectionInitialized(self)
        
        # There's probably a way to configure it (on_sub vs on_sub_and_presence)
        # but the spec defaults to not sending subscriptions without presence.
        self.send(xmppim.AvailablePresence())
        LOGGER.info(_('ConnectionInitialized'))



    def __init__(self, socket_filename, dbfilename, table):
        self.__dbfilename = dbfilename
        self.__table = table

        initializeDB(self.__dbfilename, [self.__table])
        self.__backuptoempty = os.path.exists(self.__dbfilename) 
        # using ReconnectingClientFactory using a backoff retry 
        # (it try again and again with a delay incrising between attempt)
        self.__factory = twisted.internet.protocol.ReconnectingClientFactory()

        self.__factory.buildProtocol = self.buildProtocol
        #creation socket
        connector = reactor.connectUNIX(socket_filename, self.__factory,
                                        timeout=3, checkPID=0)
        self.__connector = connector

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
        if self.__backuptoempty and self.__connector.state == 'connected':
            while not unstoremessage(self.__dbfilename, self.messageForward,
                                     self.__table):
                pass
            self.__backuptoempty = False
            sqlitevacuumDB(self.__dbfilename)
    
    def buildProtocol(self, addr):
        """ Create an instance of a subclass of Protocol. """
        return self

    def messageForward(self, msg):
        """
        function to forward the message to the socket
        @param msg: message to forward
        @type msg: C{str}
        """
        self.__connector.transport.write(msg + '\n')

    def itemsReceived(self, event):
        """ 
        function to treat a received item 
        
        @param event: event to treat
        @type  event: xml object

        """
        #event.headers
        for item in event.items:
            # Item is a domish.IElement and a domish.Element
            # Serialize as XML before queueing,
            # or we get harmless stderr pollution  × 5 lines:
            # Exception RuntimeError: 'maximum recursion depth exceeded in 
            # __subclasscheck__' in <type 'exceptions.AttributeError'> ignored
            # Stderr pollution caused by http://bugs.python.org/issue5508
            # and some touchiness on domish attribute access.
            if item.name != 'item':
                # The alternative is 'retract', which we silently ignore
                # We receive retractations in FIFO order,
                # ejabberd keeps 10 items before retracting old items.
                continue
            it = [ it for it in item.elements() if item.name == "item" ]
            if self.__connector.state == 'connected':
                for i in it:
                    LOGGER.debug(_('Message from BUS to forward: %s') % 
                                 i.toXml().encode('utf8'))
                    self.messageForward(i.toXml().encode('utf8'))
            else:
                for i in it:
                    LOGGER.error(_('Message from BUS impossible to forward' + \
                            ' (socket not connected), the message is ' + \
                            'stored for later reemission'))
                    storemessage(self.__dbfilename, 
                                 i.toXml().encode('utf8'), self.__table)
                    self.__backuptoempty = True

