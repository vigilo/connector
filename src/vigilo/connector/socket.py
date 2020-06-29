# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2020 CS GROUP – France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

from __future__ import absolute_import

import os

from zope.interface import implements

from twisted.internet import reactor, protocol, defer
from twisted.internet.interfaces import IPushProducer
from twisted.application.service import Service
from twisted.protocols.basic import LineReceiver

from vigilo.common.gettext import translate
_ = translate(__name__)

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

from vigilo.connector.serialize import parseMessage



class VigiloLineReceiver(LineReceiver):
    """ Protocol used for each line received from the socket"""
    # pylint: disable-msg=W0223
    # W0223: Method 'writeSomeData' is abstract but is not overridden

    delimiter = '\n'

    def lineReceived(self, line):
        if len(line) == 0:
            # empty line -> can't parse it
            return

        msg = parseMessage(line)
        if msg is None:
            LOGGER.warning(_("Unparsable line: %s"), line)
            # Couldn't parse this line
            return

        self.factory.parent.write(msg)



class SocketListener(Service):
    """
    Producteur pour les messages depuis la socket UNIX
    """

    implements(IPushProducer)


    def __init__(self, socket_filename):
        """
        Instancie un connecteur socket vers le bus.

        @param socket_filename: le nom du fichier pipe qui accueillra les
                                messages
        @type  socket_filename: C{str}
        """
        self.socket_filename = socket_filename
        self.consumer = None
        self.factory = protocol.ServerFactory()
        self.factory.protocol = VigiloLineReceiver
        self.factory.parent = self
        self._socket = None


    def startService(self):
        Service.startService(self)
        if os.path.exists(self.socket_filename):
            os.remove(self.socket_filename)
        self._socket = reactor.listenUNIX(
            self.socket_filename,
            self.factory,
            # rw-rw---- vigilo-nagios:vigilo-nagios
            mode=0660,
        )
        return defer.succeed(None)


    def stopService(self):
        Service.stopService(self)
        if self._socket is not None:
            d = defer.maybeDeferred(self._socket.stopListening)
        else:
            d = defer.succeed(None)
        def loseConnection(_ignored):
            if (self.factory.protocol and
                    self.factory.protocol.transport is not None):
                self.factory.protocol.transport.loseConnection()
        d.addCallback(loseConnection)
        return d


    def write(self, data):
        if self.consumer is not None:
            return self.consumer.write(data)


    def pauseProducing(self):
        """On ne sait pas faire ! """
        pass


    def resumeProducing(self):
        """
        Comme on ne sait pas faire de pause, cette méthode n'a pas de sens.
        """
        pass



def socketlistener_factory(socket_filename):
    if not os.path.exists(os.path.dirname(socket_filename)):
        msg = _("Directory not found: '%(dir)s'") % \
                {'dir': os.path.dirname(socket_filename)}
        LOGGER.error(msg)
        raise OSError(msg)

    if not os.access(os.path.dirname(socket_filename),
                     os.R_OK | os.W_OK | os.X_OK):
        msg = _("Wrong permissions on directory: '%(dir)s'") % \
                {'dir': os.path.dirname(socket_filename)}
        LOGGER.error(msg)
        raise OSError(msg)

    return SocketListener(socket_filename)
