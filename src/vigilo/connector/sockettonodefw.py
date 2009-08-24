# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

"""
Extends pubsub clients to compute Socket message
"""

import twisted.internet.protocol
from twisted.internet import reactor
from twisted.protocols.basic import LineReceiver
from wokkel import pubsub

from vigilo.common.logging import get_logger
from vigilo.pubsub import  NodeSubscriber
import logging 
from vigilo.connector import converttoxml 

LOGGER = get_logger(__name__)

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
        line_protocol = LineReceiver()
        line_protocol.delimiter = '\n'
        line_protocol.lineReceived = self.lineReceived
        return line_protocol

    def lineReceived(self, line):
        
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
        self.publish(self.__subscription.service, self.__subscription.node,[item])


    def connectionInitialized(self):
        super(SocketToNodeForwarder, self).connectionInitialized()
        if self.__port is not None:
            return
        self.__port = reactor.listenUNIX(self.__socket_filename, self.__factory)

    def connectionLost(self, reason):
        return
        print "connection LOST"
        if self.__port :
            self.__port.stopListening()
        super(SocketToNodeForwarder, self).connectionLost(reason)

