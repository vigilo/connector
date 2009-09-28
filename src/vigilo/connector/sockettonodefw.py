# vim: set fileencoding=utf-8 sw=4 ts=4 et :

"""
Extends pubsub clients to compute Socket message
"""

from __future__ import absolute_import

from twisted.internet import reactor, protocol
from twisted.protocols.basic import LineReceiver
from twisted.words.protocols.jabber.jid import JID
from twisted.words.xish import domish
from wokkel.pubsub import PubSubClient, Item
from wokkel.generic import parseXml

from vigilo.connector import converttoxml 
from vigilo.connector.store import unstoremessage, storemessage, \
                initializeDB, sqlitevacuumDB
from vigilo.common.gettext import translate
_ = translate(__name__)
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

import os

MESSAGEONETOONE = 'oneToOne'


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
            xml = converttoxml.text2xml(line)
        else:
            xml = parseXml(line)

        if xml is None:
            # Couldn't parse this line
            return
        if xml.name == MESSAGEONETOONE:
            self.factory.sendOneToOneXml(xml)
        else:
            self.factory.publishXml(xml)



class SocketToNodeForwarder(PubSubClient):
    """
    Receives messages on the socket and passes them to the xmpp bus,
    Forward socket to Node.
    """

    def __init__(self, socket_filename, dbfilename, table, 
                 nodetopublish, service):
        PubSubClient.__init__(self)
        self.__dbfilename = dbfilename
        self.__table = table

        initializeDB(self.__dbfilename, [self.__table])
        self.__backuptoempty = os.path.exists(self.__dbfilename)
        self.__factory = protocol.ServerFactory()

        self.__connector = reactor.listenUNIX(socket_filename, self.__factory)
        self.__factory.protocol = Forwarder
        self.__factory.publishXml = self.publishXml
        self.__factory.sendOneToOneXml = self.sendOneToOneXml
        self.__service = service
        self.__nodetopublish = nodetopublish


    def connectionInitialized(self):
        """ redefinition of the function for flushing backup message """
        PubSubClient.connectionInitialized(self)
        LOGGER.info(_('ConnectionInitialized'))
        if self.__backuptoempty :
            while True:
                msg = unstoremessage(self.__dbfilename, self.__table)
                if msg == True:
                    break
                elif msg == False:
                    continue
                else:
                    xml = parseXml(msg)
                    if xml.name == MESSAGEONETOONE:
                        self.sendOneToOneXml(xml)
                    else:
                        self.publishXml(xml)
                
            self.__backuptoempty = False
            sqlitevacuumDB(self.__dbfilename)



    def sendOneToOneXml(self, xml):
        """ function to send a XML msg to a particular jabber user"""
        # we need to send it to a particular receiver 
        # il faut l'envoyer vers un destinataire en particulier
        msg = domish.Element((None, "message"))
        msg["to"] = xml['to']
        msg["from"] = self.parent.jid.userhostJID().full()
        msg["type"] = 'chat'
        body = xml.firstChildElement()
        msg.addElement("body", content=body)
        self.send(msg)


    def publishXml(self, xml):
        """ function to publish a XML msg to node """
        def eb(e, xml):
            """errback"""
            LOGGER.error(_("errback publishStrXml %s") % e.__str__())
            msg = xml.toXml()
            storemessage(self.__dbfilename, msg, self.__table)
            self.__backuptoempty = True                                      

        item = Item(payload=xml)
        node = self.__nodetopublish[xml.name]
        
        try :
            result = self.publish(self.__service, node, [item])
            result.addErrback(eb, xml)
        except AttributeError :
            LOGGER.error(_('Message from Socket impossible to forward' + \
                           ' (XMPP BUS not connected), the message is' + \
                           ' stored for later reemission'))
            msg = xml.toXml()
            storemessage(self.__dbfilename, msg, self.__table)
            self.__backuptoempty = True
