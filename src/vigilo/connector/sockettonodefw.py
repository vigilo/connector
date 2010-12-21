# vim: set fileencoding=utf-8 sw=4 ts=4 et :

"""
Extends pubsub clients to compute Socket message
"""

from __future__ import absolute_import

import os
import Queue

from twisted.python.failure import Failure
from twisted.internet import reactor, protocol, defer, threads
from twisted.protocols.basic import LineReceiver
from wokkel.generic import parseXml

from vigilo.connector import converttoxml
from vigilo.connector.converttoxml import MESSAGEONETOONE
from vigilo.connector.forwarder import PubSubForwarder, NotConnectedError
from vigilo.common.gettext import translate
_ = translate(__name__)
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)


class SocketReceiver(LineReceiver):
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

        self.factory.parent.sendMessage(xml, source="socket")


class SocketToNodeForwarder(PubSubForwarder):
    """
    Receives messages on the socket and passes them to the xmpp bus,
    Forward socket to Node.

    @ivar _pending_replies: file des réponses à attendre de la part du serveur.
        Pour traiter ce problème, le plus logique serait d'utiliser une
        L{defer.DeferredList}, mais ça prend beaucoup plus de mémoire (~ 2.5x).
        Quand un message est envoyé, son Deferred est ajouté dans cette file.
        Quand elle est pleine (voir le paramètre de configuration
        C{max_send_simult}), on doit attendre les réponses du serveurs, qui
        vident la file en arrivant.
    @type _pending_replies: C{Queue.Queue}
    """

    def __init__(self, socket_filename, dbfilename, dbtable):
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
        """
        PubSubForwarder.__init__(self, dbfilename, dbtable)

        self.factory = protocol.ServerFactory()
        self.factory.protocol = SocketReceiver
        self.factory.parent = self
        if os.path.exists(socket_filename):
            os.remove(socket_filename)
        self._socket = reactor.listenUNIX(socket_filename, self.factory)


    def forwardMessage(self, xml, source="socket"):
        """
        Envoi du message sur le bus, en respectant le nombre max d'envois
        simultanés.

        @return: un Deferred qui s'active quand le message I{a été envoyé}
            (et non pas quand la réponse du serveur a été reçue).
        @rtype: C{Deferred}
        """
        xml_src = xml.toXml().encode('utf8')
        if self.xmlstream is None:
            # Backup : doit s'arrêter de dépiler. Socket : doit mettre en base
            self._send_failed(Failure(NotConnectedError()), xml_src)
            return
        if source != "backup" and \
                (self._sendingbackup or self._waitingforreplies):
            self.storeMessage(xml_src)
            return

        if xml.name == MESSAGEONETOONE:
            result = self.sendOneToOneXml(xml)
        else:
            result = self.publishXml(xml)
        # Pour attendre les réponses, le plus logique serait de faire un
        # defer.DeferredList, mais ça utilise trop de RAM, voir ci-dessus la
        # doc de la variable d'instance _pending_replies.
        try:
            self._pending_replies.put_nowait(result)
        except Queue.Full:
            threads.deferToThread(self._pending_replies.put, result)
            return self.waitForReplies()
        else:
            return defer.succeed(None)

