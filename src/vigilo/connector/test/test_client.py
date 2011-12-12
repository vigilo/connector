# -*- coding: utf-8 -*-
# pylint: disable-msg=W0212,R0903,R0904,C0111,W0613
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor, deferred

import mock
from twisted.internet import protocol
from configobj import ConfigObj

from vigilo.connector.client import MultipleServerConnector
#from vigilo.connector.client import MultipleServersXmlStreamFactory
from vigilo.connector.client import client_factory, oneshotclient_factory


class MSCTestCase(unittest.TestCase):
    """Teste L{MultipleServerConnector}"""

    def test_pickServer_first(self):
        c = MultipleServerConnector([("test1", 5222), ("test2", 5222)], None)
        c.pickServer()
        self.assertEqual(c.host, "test1")

    def test_change_host(self):
        f = protocol.ReconnectingClientFactory()
        # reconnexion manuelle
        f.continueTrying = False
        c = MultipleServerConnector([("test1", 5222), ("test2", 5222)], f,
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



class VCTestCase(unittest.TestCase):

    def setUp(self):
        self.settings = ConfigObj()
        self.settings["bus"] = {
                "user": "test",
                "password": "test",
                }

    #@mock.patch("twisted.internet.reactor.stop")
    #@mock.patch("twisted.internet.reactor.run")
    @mock.patch("twisted.internet.reactor.connectTCP")
    #def test_host_no_port(self, mockedConnectTCP, mockedRun, mockedStop):
    def test_host_no_port(self, mockedConnectTCP):
        self.settings["bus"]["host"] = "testhost"
        vc = client_factory(self.settings)
        vc._getConnection()
        self.assertEqual(mockedConnectTCP.call_count, 1)
        self.assertEqual(mockedConnectTCP.call_args[0][:2], ("testhost", 5672))

    #@mock.patch("twisted.internet.reactor.stop")
    #@mock.patch("twisted.internet.reactor.run")
    @mock.patch("twisted.internet.reactor.connectTCP")
    #def test_host_and_port(self, mockedConnectTCP, mockedRun, mockedStop):
    def test_host_and_port(self, mockedConnectTCP):
        self.settings["bus"]["host"] = "testhost:5333"
        vc = client_factory(self.settings)
        vc._getConnection()
        self.assertEqual(mockedConnectTCP.call_count, 1)
        self.assertEqual(mockedConnectTCP.call_args[0][:2], ("testhost", 5333))



class OSCTestCase(unittest.TestCase):
    """
    Teste les méthodes de connexion en fonction de la configuration fournie
    """

    def setUp(self):
        self.settings = ConfigObj()
        self.settings["bus"] = {
                "user": "test",
                "password": "test",
                }
        self.settings["connector"] = {
                "lock_file": "/nonexistant",
                }

    @mock.patch("twisted.internet.reactor.stop")
    @mock.patch("twisted.internet.reactor.run")
    @mock.patch("twisted.internet.reactor.connectTCP")
    def test_host_no_port(self, mockedConnectTCP, mockedRun, mockedStop):
        self.settings["bus"]["host"] = "testhost"
        osc = oneshotclient_factory(self.settings)
        osc.create_lockfile = mock.Mock()
        osc.create_lockfile.return_value = False
        osc.run()
        self.assertEqual(mockedConnectTCP.call_count, 1)
        self.assertEqual(mockedConnectTCP.call_args[0][:2], ("testhost", 5672))

    @mock.patch("twisted.internet.reactor.stop")
    @mock.patch("twisted.internet.reactor.run")
    @mock.patch("twisted.internet.reactor.connectTCP")
    def test_host_and_port(self, mockedConnectTCP, mockedRun, mockedStop):
        self.settings["bus"]["host"] = "testhost:5333"
        osc = oneshotclient_factory(self.settings)
        osc.create_lockfile = mock.Mock()
        osc.create_lockfile.return_value = False
        osc.run()
        self.assertEqual(mockedConnectTCP.call_count, 1)
        self.assertEqual(mockedConnectTCP.call_args[0][:2], ("testhost", 5333))

