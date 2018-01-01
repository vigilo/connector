# -*- coding: utf-8 -*-
# pylint: disable-msg=W0212,R0903,R0904,C0111,W0613
# Copyright (C) 2006-2018 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

from __future__ import print_function
import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor, deferred

import mock
from twisted.internet import protocol, tcp, defer
from configobj import ConfigObj

from vigilo.connector.client import MultipleServerConnector
from vigilo.connector.client import client_factory, oneshotclient_factory
from vigilo.connector.client import VigiloClient
from vigilo.connector.client import split_host_port

class MSCTestCase(unittest.TestCase):
    """Teste L{MultipleServerConnector}"""

    def setUp(self):
        self.rcf = protocol.ReconnectingClientFactory()

    def tearDown(self):
        self.rcf.stopTrying()

    def test_pickServer_first(self):
        c = MultipleServerConnector(None, None, None, 30, None,
                                    reactor=reactor)
        c.setMultipleParams([("test1", 5222), ("test2", 5222)], tcp.Connector)
        c.pickServer()
        self.assertEqual(c.host, "test1")

    def test_change_host(self):
        # reconnexion manuelle
        self.rcf.stopTrying()
        c = MultipleServerConnector(None, None, self.rcf, 30, None,
                                    reactor=reactor)
        c.setMultipleParams([("test1", 5222), ("test2", 5222)], tcp.Connector)

        for attemptsLeft in range(3, 0, -1):
            self.assertEqual(c._attemptsLeft, attemptsLeft)
            c.connect()
            c.connectionFailed(None)
            self.rcf.stopTrying()
            self.assertEqual(c.host, "test1")

        self.assertEqual(c._attemptsLeft, 3)
        c.connect()
        c.connectionFailed(None)
        self.rcf.stopTrying()
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
        self.settings["bus"]["hosts"] = "testhost"
        vc = client_factory(self.settings)
        vc._getConnection()
        self.assertEqual(mockedConnectTCP.call_count, 1)
        self.assertEqual(mockedConnectTCP.call_args[0][:2], ("testhost", 5672))

    #@mock.patch("twisted.internet.reactor.stop")
    #@mock.patch("twisted.internet.reactor.run")
    @mock.patch("twisted.internet.reactor.connectTCP")
    #def test_host_and_port(self, mockedConnectTCP, mockedRun, mockedStop):
    def test_host_and_port(self, mockedConnectTCP):
        self.settings["bus"]["hosts"] = "testhost:5333"
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
        self.settings["bus"]["hosts"] = "testhost"
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
        self.settings["bus"]["hosts"] = "testhost:5333"
        osc = oneshotclient_factory(self.settings)
        osc.create_lockfile = mock.Mock()
        osc.create_lockfile.return_value = False
        osc.run()
        self.assertEqual(mockedConnectTCP.call_count, 1)
        self.assertEqual(mockedConnectTCP.call_args[0][:2], ("testhost", 5333))



class VigiloClientTestCase(unittest.TestCase):


    @deferred(timeout=30)
    def test_send(self):
        c = VigiloClient(None, None, None)
        c.channel = mock.Mock()
        c.channel.basic_publish.side_effect = \
                lambda *a, **kw: defer.succeed(None)
        d = c.send("exch", "key", "msg")
        def check(r):
            self.assertTrue(c.channel.basic_publish.called)
            args = c.channel.basic_publish.call_args_list[0][1]
            print(args)
            self.assertTrue("delivery-mode" in args["content"].properties)
            self.assertEqual(args["content"].properties["delivery-mode"], 2)
            self.assertEqual(args["content"].body, "msg")
            self.assertEqual(args["routing_key"], "key")
            self.assertEqual(args["exchange"], "exch")
            self.assertEqual(args["immediate"], False)
        d.addCallback(check)
        return d


    @deferred(timeout=30)
    def test_send_non_persistent(self):
        c = VigiloClient(None, None, None)
        c.channel = mock.Mock()
        c.channel.basic_publish.side_effect = \
                lambda *a, **kw: defer.succeed(None)
        d = c.send("exch", "key", "msg", persistent=False)
        def check(r):
            self.assertTrue(c.channel.basic_publish.called)
            args = c.channel.basic_publish.call_args_list[0][1]
            print(args)
            self.assertTrue("delivery-mode" in args["content"].properties)
            self.assertEqual(args["content"].properties["delivery-mode"], 1)
        d.addCallback(check)
        return d

class HostAndPortSplitting(unittest.TestCase):
    def test_valid_splits(self):
        """Éclatement hôte/port pour des chaînes valides."""
        values = {
            'localhost:1234':   ('localhost',   1234, 1234),
            'localhost':        ('localhost',   5672, 5671),
            'example.com:0123': ('example.com',  123,  123),
            'example.com':      ('example.com', 5672, 5671),
            '127.0.0.1:2345':   ('127.0.0.1',   2345, 2345),
            '127.0.0.1':        ('127.0.0.1',   5672, 5671),
            '[::1]:3456':       ('::1',         3456, 3456),
            '[::1]':            ('::1',         5672, 5671),
        }
        for inp, outp in values.iteritems():
            expectedHost, expectedTCP, expectedSSL = outp
            # On teste d'abord en plain-text.
            actualHost, actualPort = split_host_port(inp, False)
            self.assertEqual(expectedHost, actualHost)
            self.assertEqual(expectedTCP,  actualPort)
            # Puis en SSL/TLS.
            actualHost, actualPort = split_host_port(inp, True)
            self.assertEqual(expectedHost, actualHost)
            self.assertEqual(expectedSSL,  actualPort)

    def test_invalid_splits(self):
        """Éclatement hôte/port pour des chaînes non valides."""
        values = (
            'localhost:',       # Port manquant (hostname).
            'example.com:',     # Port manquant (hostname qualifié).
            '127.0.0.1:',       # Port manquant (IPv4).
            '[::1]:',           # Port manquant (IPv6).
            ':1234',            # Hôte manquant.
            '::1:2345',         # Crochets manquants autour d'une IPv6.
        )
        for value in values:
            try:
                split_host_port(value)
            except ValueError:
                pass
            else:
                self.fail('An exception was expected for value %s' % value)
