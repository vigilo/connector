# -*- coding: utf-8 -*-
# pylint: disable-msg=W0212,R0903,R0904,C0111,W0613
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor, deferred

from twisted.internet import protocol
from vigilo.connector.client import MultipleServerConnector
from vigilo.connector.client import MultipleServersXmlStreamFactory


class MSCTestCase(unittest.TestCase):
    """Teste L{MultipleServerConnector}"""

    def test_pickServer_first(self):
        c = MultipleServerConnector(["test1", "test2"], None, None)
        c.pickServer()
        self.assertEqual(c.host, "test1")

    def test_change_host(self):
        f = MultipleServersXmlStreamFactory(None)
        # reconnexion manuelle
        f.continueTrying = False
        c = MultipleServerConnector(["test1", "test2"], None, f,
                                    attempts=3, reactor=reactor)

        for attemptsLeft in range(3, 0, -1):
            self.assertEqual(c._attemptsLeft, attemptsLeft)
            c.connect()
            c.connectionFailed(None)
            self.assertEqual(c.host, "test1")

        self.assertEqual(c._attemptsLeft, 3)
        c.connect()
        c.connectionFailed(None)
        self.assertEqual(c.host, "test2")

