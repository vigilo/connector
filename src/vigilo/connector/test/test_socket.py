# -*- coding: utf-8 -*-
# Copyright (C) 2006-2018 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

# pylint: disable-msg=C0111,W0613,R0904,W0212
# - C0111: Missing docstring
# - W0613: Unused argument
# - R0904: Too many public methods
# - W0212: Access to a protected member of a client class
from __future__ import print_function

import os, os.path
import tempfile
import shutil
import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred

from twisted.internet import defer

from vigilo.connector.socket import SocketListener

from vigilo.connector.test.helpers import ConsumerStub

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)


# Client d'une socket UNIX
from twisted.internet.protocol import ClientFactory
from twisted.protocols.basic import LineOnlyReceiver
class SendingHandler(LineOnlyReceiver):
    # pylint: disable-msg=W0223
    # W0223: Method 'lineReceived' is abstract but is not overridden
    delimiter = "\n"
    def connectionMade(self):
        self.sendLine(self.factory.message)

class SendingFactory(ClientFactory):
    protocol = SendingHandler
    def __init__(self, message):
        self.message = message



class SocketListenerTestCase(unittest.TestCase):


    @deferred(timeout=30)
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test-connector-")
        self.socket = os.path.join(self.tmpdir, "sl.sock")
        self.sl = SocketListener(self.socket)
        return self.sl.startService()

    @deferred(timeout=30)
    def tearDown(self):
        d = self.sl.stopService()
        d.addCallback(lambda _x: shutil.rmtree(self.tmpdir))
        return d


    @deferred(timeout=10)
    def testSocketToNode(self):
        """Transfert entre un socket UNIX et le bus"""
        msg_sent = "event|dummy|dummy|dummy|dummy|dummy"
        msg_sent_dict = {
                "type": "event",
                "timestamp": "dummy",
                "host": "dummy",
                "service": "dummy",
                "state": "dummy",
                "message": "dummy",
                }

        consumer = ConsumerStub()
        self.sl.consumer = consumer

        # client
        reactor.connectUNIX(self.socket, SendingFactory(msg_sent))

        d = defer.Deferred()
        def get_output():
            self.assertEqual(len(consumer.written), 1)
            msg = consumer.written[0]
            d.callback(msg)
        def check_msg(msg):
            print(msg)
            self.assertEqual(msg, msg_sent_dict)
        # On laisse un peu de temps pour traiter
        reactor.callLater(0.5, get_output)
        d.addCallback(check_msg)
        return d

