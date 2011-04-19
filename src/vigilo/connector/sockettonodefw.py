# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Extends pubsub clients to compute Socket message
"""

from __future__ import absolute_import

import os

from twisted.internet import reactor, protocol, defer
from twisted.protocols.basic import LineReceiver
from wokkel.generic import parseXml

from vigilo.connector import converttoxml
from vigilo.connector.forwarder import PubSubSender
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

        reactor.callFromThread(self.factory.parent.forwardMessage, xml)


class SocketToNodeForwarder(PubSubSender):
    """
    Reçoit les messages depuis la socket et les transmet sur le bus
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
        super(SocketToNodeForwarder, self).__init__(dbfilename, dbtable)

        self.factory = protocol.ServerFactory()
        self.factory.protocol = SocketReceiver
        self.factory.parent = self
        if os.path.exists(socket_filename):
            os.remove(socket_filename)
        self._socket = reactor.listenUNIX(socket_filename, self.factory)

