# vim: set fileencoding=utf-8 sw=4 ts=4 et :

"""
Extends pubsub clients to compute Socket message
"""

from __future__ import absolute_import

from twisted.internet import reactor, protocol, defer
from twisted.protocols.basic import LineReceiver
from twisted.words.xish import domish
from wokkel.pubsub import PubSubClient, Item
from wokkel.generic import parseXml
from wokkel import xmppim

from vigilo.connector import converttoxml
from vigilo.connector.converttoxml import MESSAGEONETOONE
from vigilo.connector.store import DbRetry
from vigilo.common.gettext import translate
_ = translate(__name__)
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

import os


class NotConnectedError(Exception):
    pass

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
            return self.factory.sendOneToOneXml(xml)
        else:
            return self.factory.publishXml(xml)



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

    @defer.inlineCallbacks
    def sendQueuedMessages(self):
        """
        Called to send Message previously stored
        @note: http://stackoverflow.com/questions/776631/using-twisteds-twisted-web-classes-how-do-i-flush-my-outgoing-buffers
        """
        if not self._backuptoempty:
            return
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
                    yield self.sendOneToOneXml(xml)
                else:
                    yield self.publishXml(xml)

        self.retry.vacuum()


    def connectionInitialized(self):
        """ redefinition of the function for flushing backup message """
        PubSubClient.connectionInitialized(self)
        # There's probably a way to configure it (on_sub vs on_sub_and_presence)
        # but the spec defaults to not sending subscriptions without presence.
        self.send(xmppim.AvailablePresence())
        LOGGER.info(_('Connected to the XMPP bus'))
        self.sendQueuedMessages()


    def _send_failed(self, e, xml, errmsg=None):
        """errback: remet le message en base"""
        xml_src = xml.toXml().encode('utf8')
        if errmsg is None:
            if e.type == NotConnectedError:
                errmsg = _('Message from Socket impossible to forward'
                           ' (no connection to XMPP server), the message '
                           'is stored for later reemission (%(xml_src)s)')
            else:
                errmsg = _('Unable to forward the message (%r), it '
                           'has been stored for later retransmission '
                           '(%%(xml_src)s)') % e
        LOGGER.error(errmsg % {"xml_src": xml_src})
        self.retry.store(xml_src)
        self._backuptoempty = True


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
            result = defer.fail(NotConnectedError())
        else:
            result = self.send(msg)
        result.addErrback(self._send_failed, msg)
        return result



    def publishXml(self, xml):
        """
        function to publish a XML msg to node
        @param xml: le message a envoyé sous forme XML
        @type xml: twisted.words.xish.domish.Element
        """
        item = Item(payload=xml)
        if xml.name not in self._nodetopublish:
            LOGGER.error(_("No destination node configured for messages "
                           "of type '%s'. Skipping.") % xml.name)
            del item
            return defer.succeed(True)
        node = self._nodetopublish[xml.name]
        try:
            result = self.publish(self._service, node, [item])
        except AttributeError:
            result = defer.fail(NotConnectedError())
        finally:
            del item
        result.addErrback(self._send_failed, xml)
        return result
