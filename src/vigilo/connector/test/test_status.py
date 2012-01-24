# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0613
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import unittest
import socket

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor, deferred

from configobj import ConfigObj

from twisted.internet import defer

from vigilo.connector.status import statuspublisher_factory

from helpers import ClientStub, wait, json



class ProviderStub(object):

    def getStats(self):
        return defer.succeed({"dummykey": "dummyvalue"})



class StatusPublisherTestCase(unittest.TestCase):
    """Teste la diffusion de l'état du connecteur"""

    def setUp(self):
        self.settings = ConfigObj()
        self.settings["connector"] = {}
        self.localhn = socket.gethostname()
        if "." in self.localhn: # on ne veut pas le FQDN
            self.localhn = self.localhn[:self.localhn.index(".")]

    @deferred(timeout=10)
    def test_send_stats(self):
        """Relai d'un ensemble de statistiques"""
        client = ClientStub("testhost", None, None)
        self.settings["connector"]["status_service"] = "testsvc"
        sp = statuspublisher_factory(self.settings, client)
        sp.isConnected = lambda: True
        client.stub_connect()
        stats = {"key1": "value1", "key2": "value2", "key3": "value3"}
        msg = {"type": "perf"}
        sp._sendStats(stats, msg)
        def check(r_):
            output = client.channel.sent
            print output
            self.assertEqual(len(output), 3)
            msg_out = [ json.loads(m["content"].body)
                        for m in output ]
            msg_in = []
            for k, v in stats.iteritems():
                m = msg.copy()
                m.update({"datasource": "testsvc-%s" % k, "value": v})
                msg_in.append(m)
            self.assertEqual(msg_in, msg_out)
        d = wait(0.2)
        d.addCallback(check)
        return d

    @deferred(timeout=10)
    def test_sendStatus(self):
        """Envoi de l'état (sendStatus)"""
        client = ClientStub("testhost", None, None)
        self.settings["connector"]["status_service"] = "testservice"
        sp = statuspublisher_factory(self.settings, client, [ProviderStub()])

        sp.isConnected = lambda: True
        client.stub_connect()

        sp.sendStatus()

        def check(r):
            output = client.channel.sent
            print output
            self.assertEqual(len(output), 2)
            msg_perf = json.loads(output[0]["content"].body)
            self.assertEqual(msg_perf["type"], "perf")
            self.assertEqual(msg_perf["host"], self.localhn)
            self.assertEqual(msg_perf["datasource"], "testservice-dummykey")
            self.assertEqual(msg_perf["value"], "dummyvalue")
            msg_cmd = json.loads(output[1]["content"].body)
            self.assertEqual(msg_cmd["type"], "nagios")
            self.assertEqual(msg_cmd["cmdname"],
                             "PROCESS_SERVICE_CHECK_RESULT")
            self.assertTrue(msg_cmd["value"].startswith(
                            "%s;testservice;0;OK:" % self.localhn))
        d = wait(0.2)
        d.addCallback(check)
        return d

    @deferred(timeout=10)
    def test_servicename(self):
        """On force le nom du service à utiliser"""
        client = ClientStub("testhost", None, None)
        self.settings["connector"]["hostname"] = "changedhost"
        self.settings["connector"]["status_service"] = "changedsvc"
        sp = statuspublisher_factory(self.settings, client,
                                     [ProviderStub()])
        sp.isConnected = lambda: True
        client.stub_connect()
        sp.sendStatus()
        def check(r):
            output = client.channel.sent
            msg_perf = json.loads(output[0]["content"].body)
            self.assertEqual(msg_perf["type"], "perf")
            self.assertEqual(msg_perf["datasource"],
                             "changedsvc-dummykey")
            msg_cmd = json.loads(output[1]["content"].body)
            self.assertEqual(msg_cmd["type"], "nagios")
            self.assertTrue(msg_cmd["value"].startswith(
                            "changedhost;changedsvc;"))
        d = wait(0.2)
        d.addCallback(check)
        return d

    @deferred(timeout=10)
    def test_force_node(self):
        """On force le nom du noeud pubsub à utiliser"""
        self.settings["connector"]["status_exchange"] = "testnode"
        self.settings["connector"]["status_service"] = "dummyservice"
        client = ClientStub("testhost", None, None)
        sp = statuspublisher_factory(self.settings, client, [ProviderStub()])
        sp.isConnected = lambda: True
        client.stub_connect()
        sp.sendStatus()
        def check(r):
            output = client.channel.sent
            for msg in output:
                print msg
                self.assertEqual(msg["exchange"], "testnode")
        d = wait(0.2)
        d.addCallback(check)
        return d

