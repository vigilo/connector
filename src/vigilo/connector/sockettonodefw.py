# vim: set fileencoding=utf-8 sw=4 ts=4 et :

"""
Extends pubsub clients to compute Socket message
"""

from __future__ import absolute_import

import twisted.internet.protocol
from twisted.internet import reactor
from twisted.protocols.basic import LineReceiver
from wokkel import pubsub

from vigilo.connector import converttoxml 


class SocketToNodeForwarder(pubsub.PubSubClient, LineReceiver):
    """
    Publishes pubsub items from a socket.

    Consumes serialized L{Pubsub.Item}s from a socket
    and publishes to a pubsub topic node.
    Forward Socket to Node
    """

    def __init__(self, socket_filename, subscription):
        self.__subscription = subscription
        self.__socket_filename = socket_filename
        self.__factory = twisted.internet.protocol.Factory()
        self.__factory.buildProtocol = self.buildProtocol
        self.__port = None

    def buildProtocol(self, addr):
        """ redefinition of the LineReceiver protocol """
        line_protocol = LineReceiver()
        line_protocol.delimiter = '\n'
        line_protocol.lineReceived = self.lineReceived
        return line_protocol

    def lineReceived(self, line):
        """ definition of the lineReceived function"""
        
        if len(line) == 0:
            # empty line -> can't parse it
            return

        # already XML or not ?
        if line[0] != '<':
            payload = converttoxml.text2xml(line)
        else:
            payload = line

        if payload is None:
            # Couldn't parse this line
            return
        item = pubsub.Item(payload=payload)
        self.publish(self.__subscription.service, 
                     self.__subscription.node, [item])


    def connectionInitialized(self):
        """ redefinition of the connectionInitialized function """
        #super(SocketToNodeForwarder, self).connectionInitialized()
        pubsub.PubSubClient.connectionInitialized(self)
        if self.__port is not None:
            return
        self.__port = reactor.listenUNIX(self.__socket_filename, self.__factory)

