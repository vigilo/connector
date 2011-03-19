# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Tests sur la communication avec le bus XMPP."""

import os
import Queue as queue
import random
import tempfile
import shutil
import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor, deferred

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.threads import deferToThread
from twisted.words.xish import domish
from twisted.words.protocols.jabber.jid import JID
from wokkel import client, subprotocols
from wokkel.generic import parseXml
from helpers import XmlStreamStub, HandlerStub

from vigilo.common.conf import settings
settings.load_module(__name__)
from vigilo.pubsub.xml import NS_PERF
from vigilo.pubsub.checknode import VerificationNode
from vigilo.common.logging import get_logger
from vigilo.connector.forwarder import PubSubListener
from vigilo.connector.nodetoqueuefw import NodeToQueueForwarder
from vigilo.connector.queuetonodefw import QueueToNodeForwarder
from vigilo.connector.nodetosocketfw import NodeToSocketForwarder
from vigilo.connector.sockettonodefw import SocketToNodeForwarder

LOGGER = get_logger(__name__)

class TestForwarderSubclasses(unittest.TestCase):
    """Teste les échangeurs (forwarders) de messages."""

    #@deferred(timeout=5)
    def setUp(self):
        """Initialisation du test."""

        # Mocks the behaviour of XMPPClient. No TCP connections made.
        self.stub = XmlStreamStub()

        self.tmpdir = tempfile.mkdtemp(prefix="test-connector-")
        self.base = os.path.join(self.tmpdir, "backup.sqlite")

    def tearDown(self):
        """Destruction des objets de test."""
        shutil.rmtree(self.tmpdir)

    @deferred(timeout=10)
    def testQueueToNode(self):
        """Transfert entre une file et le bus XMPP"""
        in_queue = queue.Queue()
        qtnf = QueueToNodeForwarder(in_queue)
        qtnf.setHandlerParent(HandlerStub(self.stub.xmlstream))
        qtnf.xmlstream = self.stub.xmlstream
        qtnf.connectionInitialized()
        # On envoie un évènement
        dom = domish.Element(('foo', 'event'))
        cookie = str(random.random())
        dom['cookie'] = cookie
        in_queue.put_nowait(dom.toXml())
        d = Deferred()
        def get_output():
            msg = self.stub.output[-1]
            event = msg.pubsub.publish.item.event
            d.callback(event)
        def check_msg(msg):
            print msg.toXml().encode("utf-8")
            self.assertEquals(msg.toXml(), dom.toXml())
        reactor.callLater(0.5, get_output) # On laisse un peu de temps pour traiter
        d.addCallback(check_msg)
        return d

    @deferred(timeout=10)
    def testNodeToQueue(self):
        """Transferts entre bus XMPP et des files."""
        out_queue = queue.Queue()

        ntqf = NodeToQueueForwarder(out_queue)
        ntqf.setHandlerParent(HandlerStub(self.stub.xmlstream))
        ntqf.xmlstream = self.stub.xmlstream
        ntqf.connectionInitialized()

        # On envoie un évènement sur le pseudo-bus
        cookie = str(random.random())
        dom = parseXml("""<message from='pubsub.localhost' to='connectorx@localhost'>
            <event xmlns='http://jabber.org/protocol/pubsub#event'>
            <items node='/home/localhost/connectorx/bus'><item>
                <event xmlns='foo' cookie='%s'/>
            </item></items>
            </event></message>""" % cookie)
        self.stub.send(dom)
        def get_output():
            try:
                msg = out_queue.get(timeout=5)
            except queue.Empty:
                self.fail("Le message n'a pas été reçu à temps")
            return msg
        def check_msg(msg):
            try:
                dom.event.items.item.event
            except AttributeError:
                self.fail("Le message n'est pas conforme")
            self.assertEquals(msg.toXml(), dom.event.items.item.event.toXml(),
                              "Le message reçu n'est pas identique au message envoyé")
        d = deferToThread(get_output)
        d.addCallback(check_msg)
        return d

    @deferred(timeout=10)
    def testNodeToSocket(self):
        """Transferts entre bus XMPP et un socket UNIX"""

        from twisted.protocols.basic import LineOnlyReceiver
        from twisted.internet.protocol import Factory
        class TriggeringLineReceiver(LineOnlyReceiver):
            delimiter = "\n"
            def lineReceived(self, line):
                self.factory.received(line)
        class TriggeringFactory(Factory):
            protocol = TriggeringLineReceiver
            def __init__(self, deferred):
                self.deferred = deferred
            def received(self, line):
                self.deferred.callback(line)

        d = Deferred()
        socket = os.path.join(self.tmpdir, "ntsf.sock")
        reactor.listenUNIX(socket, TriggeringFactory(d))

        ntsf = NodeToSocketForwarder(socket, None, None)
        ntsf.setHandlerParent(HandlerStub(self.stub.xmlstream))
        ntsf.xmlstream = self.stub.xmlstream
        ntsf.connectionInitialized()

        # On envoie un évènement sur le pseudo-bus
        cookie = str(random.random())
        dom = parseXml("""<message from='pubsub.localhost' to='connectorx@localhost'>
            <event xmlns='http://jabber.org/protocol/pubsub#event'>
            <items node='/home/localhost/connectorx/bus'><item>
                <event xmlns='foo' cookie='%s'/>
            </item></items>
            </event></message>""" % cookie)
        self.stub.send(dom)

        def check_msg(msg):
            self.assertEquals(msg, dom.event.items.item.event.toXml(),
                              "Le message reçu n'est pas identique au message envoyé")
        d.addCallback(check_msg)
        return d

    @deferred(timeout=10)
    def testSocketToNode(self):
        """Transfert entre un socket UNIX et le bus XMPP"""

        from twisted.internet.protocol import ClientFactory
        from twisted.protocols.basic import LineOnlyReceiver
        class SendingHandler(LineOnlyReceiver):
            delimiter = "\n"
            def connectionMade(self):
                self.sendLine(self.factory.message)
        class SendingFactory(ClientFactory):
            protocol = SendingHandler
            def __init__(self, message):
                self.message = message

        cookie = str(random.random())
        msg_sent = "event|dummy|dummy|dummy|dummy|dummy"
        msg_sent_xml = parseXml("""
                <event xmlns='http://www.projet-vigilo.org/xmlns/event1'>
                    <timestamp>dummy</timestamp>
                    <host>dummy</host>
                    <service>dummy</service>
                    <state>dummy</state>
                    <message>dummy</message>
                </event>""")
        socket = os.path.join(self.tmpdir, "stnf.sock")

        # serveur
        stnf = SocketToNodeForwarder(socket, None, None)
        stnf.setHandlerParent(HandlerStub(self.stub.xmlstream))
        stnf.xmlstream = self.stub.xmlstream
        stnf.connectionInitialized()

        # client
        reactor.connectUNIX(socket, SendingFactory(msg_sent))

        d = Deferred()
        def get_output():
            msg = self.stub.output[-1]
            event = msg.pubsub.publish.item.event
            d.callback(event)
        def check_msg(msg):
            print msg.toXml().encode("utf-8")
            self.assertEquals(msg.toXml(), msg_sent_xml.toXml())
        reactor.callLater(0.5, get_output) # On laisse un peu de temps pour traiter
        d.addCallback(check_msg)
        return d

class PubSubListenerTest(unittest.TestCase):

    def setUp(self):
        """Initialisation du test."""
        # Mocks the behaviour of XMPPClient. No TCP connections made.
        self.stub = XmlStreamStub()
        self.received = []
        self.psl = PubSubListener()
        self.psl.isConnected = lambda: True
        self.psl.forwardMessage = self.received.append

    def test_recv_pubsub(self):
        """Ecoute du bus: pubsub"""
        self.psl.xmlstream = self.stub.xmlstream
        self.psl.connectionInitialized()

        # On envoie un évènement sur le pseudo-bus
        cookie = str(random.random())
        dom = parseXml("""<message from='pubsub.localhost' to='connectorx@localhost'>
            <event xmlns='http://jabber.org/protocol/pubsub#event'>
            <items node='/home/localhost/connectorx/bus'><item>
                <event xmlns='foo' cookie='%s'/>
            </item></items>
            </event></message>""" % cookie)
        self.stub.send(dom)

        print dom.toXml()
        self.assertEquals(len(self.received), 1)
        self.assertEquals(self.received[0].toXml(),
                          dom.event.items.item.event.toXml())

    def test_recv_chat(self):
        """Ecoute du bus: chat"""
        self.psl.xmlstream = self.stub.xmlstream
        self.psl.connectionInitialized()

        # On envoie un évènement sur le pseudo-bus
        cookie = str(random.random())
        message = parseXml("""
            <message from="dummy1" to="dummy2" type="chat">
                <body>
                    <event xmlns='foo' cookie='%s'/>
                </body>
            </message>""" % cookie)
        self.stub.send(message)

        self.assertEquals(len(self.received), 1)
        self.assertEquals(self.received[0].toXml(),
                          message.body.event.toXml())

    def test_recv_pubsub_aggr(self):
        """Ecoute du bus: pubsub avec aggregation"""
        self.psl.xmlstream = self.stub.xmlstream
        self.psl.connectionInitialized()

        # On envoie un évènement sur le pseudo-bus
        count = 42
        aggr_msg = domish.Element((NS_PERF, "perfs"))
        perf_msg = domish.Element((None, "perf"))
        perf_msg.content = "dummy"
        for i in range(count):
            aggr_msg.addChild(perf_msg)
        msg = parseXml("""<message from='dummy1' to='dummy2'>
            <event xmlns='http://jabber.org/protocol/pubsub#event'>
            <items node='/home/localhost/connectorx/bus'><item>
                %s
            </item></items>
            </event></message>""" % aggr_msg.toXml())
        self.stub.send(msg)
        self.assertEquals(len(self.received), count)

    def test_recv_chat_aggr(self):
        """Ecoute du bus: chat avec aggregation"""
        self.psl.xmlstream = self.stub.xmlstream
        self.psl.connectionInitialized()

        # On envoie un évènement sur le pseudo-bus
        count = 42
        aggr_msg = domish.Element((None, "perfs"))
        perf_msg = domish.Element((None, "perf"))
        perf_msg.content = "dummy"
        for i in range(count):
            aggr_msg.addChild(perf_msg)
        msg = domish.Element((None, "message"))
        msg["to"] = "dummy1"
        msg["from"] = "dummy2"
        msg["type"] = 'chat'
        msg.addElement("body", content=aggr_msg)
        self.stub.send(msg)
        self.assertEquals(len(self.received), count)

    def test_recv_retract(self):
        """Réception de messages retract"""
        self.psl.xmlstream = self.stub.xmlstream
        self.psl.connectionInitialized()
        # On envoie un évènement sur le pseudo-bus
        msg = parseXml("""<message from='pubsub.localhost' to='connectorx@localhost'>
            <event xmlns='http://jabber.org/protocol/pubsub#event'>
            <items node='/home/localhost/connectorx/bus'><retract /></items>
            </event></message>""")
        self.stub.send(msg)
        self.assertEquals(len(self.received), 0)


