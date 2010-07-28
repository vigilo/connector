# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Tests sur la communication avec le bus XMPP."""

import Queue as queue
import random
import threading

from twisted.trial import unittest
from twisted.internet import reactor

from twisted.internet.defer import Deferred
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

class TestForwarders(unittest.TestCase):
    """Teste les échangeurs (forwarders) de messages."""
    timeout = 10

    def setUp(self):
        """Initialisation du test."""

        # Mocks the behaviour of XMPPClient. No TCP connections made.
        # A bit useless for integration tests;
        # we use high-level apis and need the real deal.
        if False:
            self.stub = XmlStreamStub()
            self.protocol.xmlstream = self.stub.xmlstream
            self.protocol.connectionInitialized()

        self.xmpp_client = client.XMPPClient(
                JID(settings['bus']['jid']),
                settings['bus']['password'],
                settings['bus']['host'],
                )
        self.xmpp_client.logTraffic = True
        self.xmpp_client.startService()

        list_nodeOwner = settings['bus']['owned_topics']
        verifyNode = VerificationNode(
                        list_nodeOwner,
                        list_nodeOwner,
                        doThings=True)
        verifyNode.setHandlerParent(self.xmpp_client)

        conn_deferred = Deferred()
        conn_handler = subprotocols.XMPPHandler()
        def on_conn():
            reactor.callLater(1., lambda: conn_deferred.callback(None))
        conn_handler.connectionInitialized = on_conn
        conn_handler.setHandlerParent(self.xmpp_client)

        # Wait a few seconds so the xml stream is established.
        # This allows us to use shorter timeouts later.
        # We have no way to get a deferred for startService,
        # which would have been quicker.
        #return deferToThread(lambda: time.sleep(1.5))
        return conn_deferred

    def tearDown(self):
        """Destruction des objets de test."""
        return self.xmpp_client.stopService()

    def testForwarders(self):
        """Transferts entre bus XMPP et des files."""
        in_queue = queue.Queue()
        out_queue = queue.Queue()

        ntqf = NodeToQueueForwarder(out_queue, ':memory:', 'correlator')
        ntqf.setHandlerParent(self.xmpp_client)

        qtnf = QueueToNodeForwarder(
                in_queue, ':memory:', 'correlator',
                # On redirige la sortie de QueueToNodeForwarder
                # vers l'entrée de NodeToQueueForwarder.
                {'event': settings['bus']['owned_topics'][0]},
                JID(settings['bus']['service']),
                )
        qtnf.setHandlerParent(self.xmpp_client)

        # On envoie un évènement dans le QueueToNodeForwarder,
        # qui a été configuré pour le transmettre à NodeToQueueForwarder.
        dom = domish.Element(('foo', 'event'))
        cookie = str(random.random())
        dom['cookie'] = cookie
        in_queue.put_nowait(dom.toXml())

        # On tente de récupérer l'évènement via le NodeToQueueForwarder.
        # Causes pylint to crash: http://www.logilab.org/ticket/8771
        out_xml = yield deferToThread(lambda: out_queue.get(timeout=2.0))
        item = parseXml(out_xml)

        # On vérifie que ce qui a été reçu correspond à ce qui a été envoyé.
        assert item.children[0].attributes['cookie'] == cookie
        assert item.children[0].toXml() == dom.toXml()

        ntqf.disownHandlerParent(self.xmpp_client)
        qtnf.disownHandlerParent(self.xmpp_client)
        in_queue.close()
        out_queue.close()

