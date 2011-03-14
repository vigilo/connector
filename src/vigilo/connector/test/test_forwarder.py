# -*- coding: utf-8 -*-
"""
Teste la sauvegarde d'un message dans la database si on est pas connectés
"""
import os, os.path
import tempfile
import shutil
import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor, deferred

from twisted.internet import defer
from twisted.words.xish import domish

from vigilo.connector.forwarder import PubSubSender
from vigilo.pubsub.xml import NS_PERF

from helpers import XmlStreamStub, wait


class TestForwarder(unittest.TestCase):
    """Teste la sauvegarde locale de messages en cas d'erreur."""

    @deferred(timeout=30)
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test-connector-")
        self.base = os.path.join(self.tmpdir, "backup.sqlite")
        self.publisher = PubSubSender(self.base, "tobus")
        # le initdb est déjà fait en __init__ mais ça permet de s'assurer
        # qu'on est bien initialisés
        return self.publisher.retry.initdb()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_store_message(self):
        """Stockage local d'un message lorsque le bus est indisponible."""
        # Preparation du message
        msg = domish.Element((NS_PERF, 'perf'))
        msg.addElement('test', content="this is a test")

        before = yield self.publisher.retry.qsize()
        yield self.publisher.processMessage(msg)
        after = yield self.publisher.retry.qsize()
        self.assertEqual(after, before + 1)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_unstore_order(self):
        msg1 = domish.Element((NS_PERF, 'perf'))
        msg1.addElement('test', content="1")
        stub = XmlStreamStub()
        yield self.publisher.processMessage(msg1)
        # Le message est maintenant en base de backup
        backup_size = yield self.publisher.retry.qsize()
        self.assertEqual(backup_size, 1)
        # On se connecte
        self.publisher.xmlstream = stub.xmlstream
        self.publisher.connectionInitialized()
        # On attend un peu
        yield wait(0.5)
        # On en envoie un deuxième
        msg2 = domish.Element((NS_PERF, 'perf'))
        msg2.addElement('test', content="2")
        # pas de yield, la réponse n'arrivera jamais (stub)
        self.publisher.processMessage(msg2)
        # On attend un peu
        yield wait(0.5)
        # On vérifie que les deux messages ont bien été envoyés dans le bon ordre
        self.assertEqual(len(stub.output), 2)
        for index, msg in enumerate([msg1, msg2]):
            msg_out = stub.output[index]
            try:
                msg_out.pubsub.publish.item.perf
            except AttributeError:
                self.fail("Le message n'a pas été transmis correctement")
            self.assertEqual(msg_out.pubsub.publish.item.perf.toXml(), msg.toXml())

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_begin_with_backup(self):
        """
        Les messages sauvegardés doivent être prioritaires sur les messages
        temps-réel
        """
        msg1 = domish.Element((NS_PERF, 'perf'))
        msg1.addElement('test', content="1")
        msg2 = domish.Element((NS_PERF, 'perf'))
        msg2.addElement('test', content="2")
        yield self.publisher.retry.put(msg1)
        self.publisher.queue.append(msg2)
        # On attend un peu
        #yield wait(0.5)
        for msg in [msg1, msg2]:
            next_msg = yield self.publisher._get_next_msg()
            self.assertEqual(next_msg.toXml(), msg.toXml())

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_save_to_db(self):
        count = 42
        for i in range(count):
            msg = domish.Element((NS_PERF, 'perf'))
            msg.addElement('test', content="dummy")
            self.publisher.queue.append(msg)
        yield self.publisher._save_to_db()
        self.assertEqual(len(self.publisher.queue), 0)
        db_size = yield self.publisher.retry.qsize()
        self.assertEqual(db_size, count)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_stats_1(self):
        msg = domish.Element((NS_PERF, 'perf'))
        msg.addElement('test', content="dummy")
        # On se connecte
        stub = XmlStreamStub()
        self.publisher.xmlstream = stub.xmlstream
        self.publisher.connectionInitialized()
        # On envoie des messages
        print "envoi 1"
        for i in range(10):
            self.publisher.forwardMessage(msg)
        # On attend un peu
        yield wait(0.2)
        # On simule une réponse du bus
        for d in self.publisher._pending_replies:
            d.callback(None)
        # On attend un peu
        yield wait(0.2)
        # On se déconnecte
        self.publisher.xmlstream = None
        #self.publisher._initialized = False
        self.publisher.connectionLost(None)
        # On envoie des messages (-> backup)
        print "envoi 2"
        for i in range(20):
            self.publisher.forwardMessage(msg)
        # On attend un peu
        yield wait(0.5)
        # Les messages sont maintenant soit envoyés soit en base de backup
        self.assertEqual(len(stub.output), 10)
        backup_size = yield self.publisher.retry.qsize()
        self.assertEqual(backup_size, 20)
        # on vide les buffers (pour fiabiliser le test)
        yield self.publisher.retry.flush()
        stats = yield self.publisher.getStats()
        print stats
        self.assertEqual(stats, {
            "queue": 0,
            "forwarded": 30,
            "sent": 10,
            "backup": 20,
            "backup_in_buf": 0,
            "backup_out_buf": 0,
            })

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_accumulate_perfs(self):
        count = 42
        self.publisher.batch_send_perf = count
        msg = domish.Element((NS_PERF, 'perf'))
        msg.addElement('test', content="dummy")
        # On se connecte
        stub = XmlStreamStub()
        self.publisher.xmlstream = stub.xmlstream
        self.publisher.connectionInitialized()
        # on traite n-1 message, ce qui ne doit rien envoyer sur le bus
        for i in range(count - 1):
            yield self.publisher.processMessage(msg)
        self.assertEqual(stub.output, [])
        # on en envoie un de plus, ce qui doit envoyer un message accumulé
        self.publisher.processMessage(msg)
        self.assertEqual(len(stub.output), 1)
        sent = stub.output[0].pubsub.publish.item
        self.assertEqual(len(list(sent.elements())), 1)
        acc_msg = list(sent.elements())[0]
        self.assertEqual(acc_msg.name, "perfs")
        self.assertEqual(len(list(acc_msg.elements())), count)



if __name__ == "__main__":
    unittest.main()

