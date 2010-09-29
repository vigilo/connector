# vim: set fileencoding=utf-8 sw=4 ts=4 et :

"""
Extends pubsub clients to compute Socket message
"""

from __future__ import absolute_import

from twisted.internet import reactor, protocol
from twisted.protocols.basic import LineReceiver
from twisted.words.xish import domish
from wokkel.pubsub import PubSubClient, Item
from wokkel.generic import parseXml
from wokkel import xmppim

from vigilo.connector import converttoxml
from vigilo.connector.store import DbRetry
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
    def __init__(self, socket_filename, dbfilename, dbtable,
                 nodetopublish, service):
        """
        Instancie un connecteur socket vers BUS XMPP.

        @param socket_filename: le nom du fichier pipe qui accueillra les
                                messages XMPP
        @type  socket_filename: C{str}
        @param dbfilename: le nom du fichier permettant la sauvegarde des
                           messages en cas de problème d'éciture sur le BUS
        @type  dbfilename: C{str}
        @param dbtable: Le nom de la table SQL pour la sauvegarde des messages.
        @type  dbtable: C{str}
        @param nodetopublish: dictionnaire pour la correspondance type de message
                              noeud PubSub de destination.
        @type  nodetopublish: C{dict}
        @param service: The publish subscribe service that keeps the node.
        @type  service: C{twisted.words.protocols.jabber.jid.JID}
        """
        PubSubClient.__init__(self)
        self.retry = DbRetry(dbfilename, dbtable)
        self._backuptoempty = os.path.exists(dbfilename)

        self.factory = protocol.ServerFactory()

        self.factory.protocol = Forwarder
        self.factory.publishXml = self.publishXml
        self.factory.sendOneToOneXml = self.sendOneToOneXml
        if os.path.exists(socket_filename):
            os.remove(socket_filename)
        self.__connector = reactor.listenUNIX(socket_filename, self.factory)
        self._service = service
        self._nodetopublish = nodetopublish
        self.name = self.__class__.__name__


    def sendQueuedMessages(self):
        """
        Called to send Message previously stored
        """
        if self._backuptoempty:
            self._backuptoempty = False
            # XXX Ce code peut potentiellement boucler indéfiniment...
            while True:
                msg = self.retry.unstore()
                if msg is None:
                    break
                else:
                    LOGGER.debug(_('Received message: %r') % msg)
                    xml = parseXml(msg)
                    if xml.name == MESSAGEONETOONE:
                        if self.sendOneToOneXml(xml) is not True:
                            # we loose the ability to send message again
                            self._backuptoempty = True
                            break
                    else:
                        if self.publishXml(xml) is not True:
                            # we loose the ability to send message again
                            self._backuptoempty = True
                            break

            self.retry.vacuum()


    def connectionInitialized(self):
        """ redefinition of the function for flushing backup message """
        PubSubClient.connectionInitialized(self)
        # There's probably a way to configure it (on_sub vs on_sub_and_presence)
        # but the spec defaults to not sending subscriptions without presence.
        self.send(xmppim.AvailablePresence())
        LOGGER.info(_('Connected to the XMPP bus'))
        self.sendQueuedMessages()


    def sendOneToOneXml(self, xml):
        """
        function to send a XML msg to a particular jabber user
        @param xml: le message a envoyé sous forme XML
        @type xml: twisted.words.xish.domish.Element
        """
        # we need to send it to a particular receiver
        # il faut l'envoyer vers un destinataire en particulier
        msg = domish.Element((None, "message"))
        msg["to"] = xml['to']
        msg["from"] = self.parent.jid.userhostJID().full()
        msg["type"] = 'chat'
        body = xml.firstChildElement()
        msg.addElement("body", content=body)
        # if not connected store the message
        if self.xmlstream is None:
            xml_src = xml.toXml().encode('utf8')
            LOGGER.error(_('Message from Socket impossible to forward'
                           ' (no connection to XMPP server), the message '
                           'is stored for later reemission (%s)') % xml_src)
            self.retry.store(xml_src)
            self._backuptoempty = True
        else:
            self.send(msg)
            return True



    def publishXml(self, xml):
        """
        function to publish a XML msg to node
        @param xml: le message a envoyé sous forme XML
        @type xml: twisted.words.xish.domish.Element
        """
        def eb(e, xml):
            """errback"""
            xml_src = xml.toXml().encode('utf8')
            LOGGER.error(_('Unable to forward the message (%(error)r), it '
                        'has been stored for later retransmission '
                        '(%(xml_src)s)') % {
                            'xml_src': xml_src,
                            'error': e,
                        })
            self.retry.store(xml_src)
            self._backuptoempty = True

        item = Item(payload=xml)

        if xml.name not in self._nodetopublish:
            LOGGER.error(_("No destination node configured for messages "
                           "of type '%s'. Skipping.") % xml.name)
            del item
            return
        node = self._nodetopublish[xml.name]
        try:
            result = self.publish(self._service, node, [item])
            result.addErrback(eb, xml)
            del result
            return True
        except AttributeError:
            xml_src = xml.toXml().encode('utf8')
            LOGGER.error(_('Message from Socket impossible to forward'
                           ' (no connection to XMPP server), the message '
                           'is stored for later reemission (%s)') % xml_src)
            self.retry.store(xml_src)
            self._backuptoempty = True
        finally:
            del item
            del eb
