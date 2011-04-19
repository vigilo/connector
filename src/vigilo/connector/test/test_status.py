# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0613
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor, deferred

from twisted.internet import defer

from vigilo.connector.status import StatusPublisher
from vigilo.pubsub.xml import NS_PERF

from helpers import XmlStreamStub, wait


class ForwarderStub(object):
    def getStats(self):
        return defer.succeed({"dummykey": "dummyvalue"})

class StatusPublisherTest(unittest.TestCase):
    """Teste la diffusion de l'état du connecteur"""

    @deferred(timeout=10)
    def test_send_stats(self):
        """Relai d'un ensemble de statistiques"""
        sp = StatusPublisher(ForwarderStub(), "dummyhost")
        xs = XmlStreamStub(autoreply=True)
        sp.xmlstream = xs.xmlstream
        sp.isConnected = lambda: True
        stats = {"key1": "value1", "key2": "value2", "key3": "value3"}
        msg = ('<perf xmlns=\''+NS_PERF+'\'>'
               '<d>%(datasource)s</d>'
               '<v>%(value)s</v>'
               '</perf>')
        sp._send_stats(stats, msg)
        def check(r_):
            print [ m.pubsub.publish.item.toXml() for m in xs.output ]
            self.assertEqual(len(xs.output), 3)
            msg_out = [ m.pubsub.publish.item.perf.toXml()
                        for m in xs.output ]
            msg_out.sort()
            msg_in = [ msg % {"datasource": k, "value": v}
                       for k, v in stats.iteritems() ]
            msg_in.sort()
            self.assertEqual(msg_in, msg_out)
        d = wait(0.2)
        d.addCallback(check)
        return d

    @deferred(timeout=10)
    def test_sendStatus(self):
        """Envoi de l'état (sendStatus)"""
        sp = StatusPublisher(ForwarderStub(), "dummyhost")
        xs = XmlStreamStub(autoreply=True)
        sp.xmlstream = xs.xmlstream
        sp.isConnected = lambda: True
        sp.sendStatus()
        def check(r):
            self.assertEqual(len(xs.output), 2)
            msg_cmd = xs.output[0].pubsub.publish.item.command
            self.assertEqual(str(msg_cmd.cmdname),
                             "PROCESS_SERVICE_CHECK_RESULT")
            self.assertTrue(str(msg_cmd.value).startswith(
                            "dummyhost;test;0;OK:"))
            msg_perf = xs.output[1].pubsub.publish.item.perf
            self.assertEqual(str(msg_perf.host), "dummyhost")
            self.assertEqual(str(msg_perf.datasource), "test-dummykey")
            self.assertEqual(str(msg_perf.value), "dummyvalue")
        d = wait(0.2)
        d.addCallback(check)
        return d

    @deferred(timeout=10)
    def test_servicename(self):
        """On force le nom du service à utiliser"""
        sp = StatusPublisher(ForwarderStub(), "dummyhost", "dummyservice")
        xs = XmlStreamStub(autoreply=True)
        sp.xmlstream = xs.xmlstream
        sp.isConnected = lambda: True
        sp.sendStatus()
        def check(r):
            msg_cmd = xs.output[0].pubsub.publish.item.command
            self.assertTrue(str(msg_cmd.value).startswith(
                            "dummyhost;dummyservice;"))
            msg_perf = xs.output[1].pubsub.publish.item.perf
            self.assertEqual(str(msg_perf.datasource),
                             "dummyservice-dummykey")
        d = wait(0.2)
        d.addCallback(check)
        return d

    @deferred(timeout=10)
    def test_force_node(self):
        """On force le nom du noeud pubsub à utiliser"""
        sp = StatusPublisher(ForwarderStub(), "dummyhost", node="/testnode")
        xs = XmlStreamStub(autoreply=True)
        sp.xmlstream = xs.xmlstream
        sp.isConnected = lambda: True
        sp.sendStatus()
        def check(r):
            for msg in xs.output:
                self.assertEqual(msg.pubsub.publish["node"], "/testnode")
        d = wait(0.2)
        d.addCallback(check)
        return d


