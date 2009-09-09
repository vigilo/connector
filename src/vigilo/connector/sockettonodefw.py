# vim: set fileencoding=utf-8 sw=4 ts=4 et :

"""
Extends pubsub clients to compute Socket message
"""

from __future__ import absolute_import

from twisted.internet import reactor, protocol
from twisted.protocols.basic import LineReceiver
from wokkel.pubsub import PubSubClient, Item

from vigilo.connector import converttoxml 
from vigilo.connector.stock import unstockmessage, stockmessage, \
                initializeDB, sqlitevacuumDB
from vigilo.common.gettext import translate
_ = translate(__name__)
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

import os


class Forwarder(LineReceiver):
    """ Protocol used for each line received from the socket """
    
    delimiter = '\n'

    def lineReceived(self, line):
        """ redefinition of the lineReceived function"""
        
        if len(line) == 0:
            # empty line -> can't parse it
            return

        # already XML or not ?
        if line[0] != '<':
            strXml = converttoxml.text2xml(line)
        else:
            strXml = line

        if strXml is None:
            # Couldn't parse this line
            return
        self.factory.publishStrXml(strXml)


class SocketToNodeForwarder(PubSubClient):
    """
    Receives messages on the socket and passes them to the xmpp bus,
    Forward socket to Node.
    """

    def __init__(self, socket_filename, subscription, dbfilename, table):
        self.__dbfilename = dbfilename
        self.__table = table

        initializeDB(self.__dbfilename, [self.__table])
        self.__subscription = subscription
        self.__backuptoempty = os.path.exists(self.__dbfilename)
        self.__factory = protocol.ServerFactory()

        self.__connector = reactor.listenUNIX(socket_filename, self.__factory)
        self.__factory.protocol = Forwarder
        self.__factory.publishStrXml = self.publishStrXml


    def connectionInitialized(self):
        """ redefinition of the function for flushing backup message """
        PubSubClient.connectionInitialized(self)
        if self.__backuptoempty :
            while not unstockmessage(self.__dbfilename, self.publishStrXml,
                                     self.__table):
                pass
            self.__backuptoempty = False
            sqlitevacuumDB(self.__dbfilename)
        
    def publishStrXml(self, strXml):
        """ function to publish a C{str} XML text to the node """
        item = Item(payload=strXml)
        try :
            self.publish(self.__subscription.service, 
                         self.__subscription.node, [item])
        except AttributeError :
            LOGGER.error(_('Message from Socket impossible to forward' + \
                           ' (XMPP BUS not connected), the message is' + \
                           ' stocked for later reemission'))
            stockmessage(self.__dbfilename, strXml, self.__table)
            self.__backuptoempty = True
    
