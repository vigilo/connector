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
from wokkel.test.helpers import XmlStreamStub

from vigilo.common.conf import settings
settings.load_module(__name__)
from vigilo.pubsub.checknode import VerificationNode
from vigilo.common.logging import get_logger
from vigilo.connector.nodetoqueuefw import NodeToQueueForwarder
from vigilo.connector.queuetonodefw import QueueToNodeForwarder

LOGGER = get_logger(__name__)

class HandlerStub(object):
    def __init__(self, xmlstream):
        self.xmlstream = xmlstream
    def addHandler(self, dummy):
        pass
    def removeHandler(self, dummy):
        pass
    def send(self, obj):
        self.xmlstream.send(obj)

class TestForwarders(unittest.TestCase):
    """Teste les échangeurs (forwarders) de messages."""

    #@deferred(timeout=5)
    def setUp(self):
        """Initialisation du test."""

        # Mocks the behaviour of XMPPClient. No TCP connections made.
        self.stub = XmlStreamStub()

        self.tmpdir = tempfile.mkdtemp(prefix="test-connector-")
        self.base = os.path.join(self.tmpdir, "backup.sqlite")

        #self.xmpp_client = client.XMPPClient(
        #        JID(settings['bus']['jid']),
        #        settings['bus']['password'],
        #        settings['bus']['host'],
        #        )
        #self.xmpp_client.logTraffic = True
        #self.xmpp_client.startService()

        #conn_deferred = Deferred()
        #conn_handler = subprotocols.XMPPHandler()
        #def on_conn():
        #    reactor.callLater(1., lambda: conn_deferred.callback(None))
        #conn_handler.connectionInitialized = on_conn
        #conn_handler.setHandlerParent(self.xmpp_client)

        ## Wait a few seconds so the xml stream is established.
        ## This allows us to use shorter timeouts later.
        ## We have no way to get a deferred for startService,
        ## which would have been quicker.
        ##return deferToThread(lambda: time.sleep(1.5))
        #return conn_deferred

    def tearDown(self):
        """Destruction des objets de test."""
        #self.xmpp_client.stopService()
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
            d.callback(msg)
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

    #@deferred(timeout=30)
    #@inlineCallbacks
    #def testForwarders(self):
    #    """Transferts entre bus XMPP et des files."""
    #    in_queue = queue.Queue()
    #    out_queue = queue.Queue()

    #    ntqf = NodeToQueueForwarder(out_queue)
    #    ntqf.setHandlerParent(self.xmpp_client)

    #    qtnf = QueueToNodeForwarder(in_queue)
    #    qtnf.setHandlerParent(self.xmpp_client)

    #    # On envoie un évènement dans le QueueToNodeForwarder,
    #    # qui a été configuré pour le transmettre à NodeToQueueForwarder.
    #    dom = domish.Element(('foo', 'event'))
    #    cookie = str(random.random())
    #    dom['cookie'] = cookie
    #    in_queue.put_nowait(dom.toXml())

    #    # On tente de récupérer l'évènement via le NodeToQueueForwarder.
    #    # Causes pylint to crash: http://www.logilab.org/ticket/8771
    #    item = None
    #    while True:
    #        # on récupère le dernier, les premiers pouvant être des messages
    #        # réémis par le bus (avec attribut <delay>, non-accessible)
    #        try:
    #            newitem = yield deferToThread(out_queue.get, timeout=3.0)
    #        except queue.Empty:
    #            break
    #        if newitem:
    #            print u"Reçu: %s" % newitem.toXml().encode("utf-8")
    #            item = newitem
    #    if item is None:
    #        self.fail("Le message n'est pas arrivé dans le temps imparti")

    #    # On vérifie que ce qui a été reçu correspond à ce qui a été envoyé.
    #    self.assertEqual(item.attributes['cookie'], cookie,
    #                     "Le cookie n'est pas bon")
    #    self.assertEqual(item.toXml(), dom.toXml(),
    #                     "le message XML n'est pas bon")

    #    ntqf.disownHandlerParent(self.xmpp_client)
    #    qtnf.disownHandlerParent(self.xmpp_client)
