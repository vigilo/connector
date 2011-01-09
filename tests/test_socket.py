# -*- coding: utf-8 -*-
from __future__ import absolute_import

import unittest
import tempfile
import os

# A faire avant Twisted
from nose.twistedtools import reactor

from twisted.words.protocols.jabber.jid import JID

from vigilo.connector.sockettonodefw import SocketToNodeForwarder


class Socket(unittest.TestCase):
    """ Test the connector functions """

    def setUp(self):
        tmphandle, self.tmpsocket = tempfile.mkstemp()
        tmphandle, self.tmpbackup = tempfile.mkstemp()

    def tearDown(self):
        os.remove(self.tmpsocket)
        os.remove(self.tmpbackup)

    def test_clean_send(self):
        """Suppression de la socket precedente si encore presente"""
        SocketToNodeForwarder(self.tmpsocket, self.tmpbackup, "dummytable")


if __name__ == "__main__": 
    unittest.main()
