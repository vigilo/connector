# -*- coding: utf-8 -*-
# pylint: disable-msg=C0111,W0613,R0904
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import os, os.path
import tempfile
import shutil
import unittest
from collections import deque

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor, deferred

from mock import Mock

from twisted.internet import defer

from vigilo.connector.handlers import BackupProvider, BusPublisher

from helpers import ClientStub, wait, json, ConsumerStub

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)



class BackupProviderTestCase(unittest.TestCase):
    """Teste la sauvegarde locale de messages en cas d'erreur."""


    @deferred(timeout=30)
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test-connector-")
        self.base = os.path.join(self.tmpdir, "backup.sqlite")
        self.bp = BackupProvider(self.base, "tobus")
        return self.bp.startService()

    @deferred(timeout=30)
    def tearDown(self):
        d = self.bp.stopService()
        d.addCallback(lambda _x: shutil.rmtree(self.tmpdir))
        return d


    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_store_message(self):
        """Stockage local d'un message lorsque le bus est indisponible."""
        msg = {"type": "perf"}
        self.bp.pauseProducing()

        before = yield self.bp.retry.qsize()
        self.bp.queue.append(msg)
        yield self.bp.processQueue()
        after = yield self.bp.retry.qsize()
        self.assertEqual(after, before + 1)


    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_unstore_order(self):
        msg1 = {"type": "perf", "value": "1"}
        self.bp.pauseProducing()
        consumer = ConsumerStub()
        self.bp.consumer = consumer
        yield self.bp.write(msg1)
        # Le message est maintenant en base de backup
        backup_size = yield self.bp.retry.qsize()
        self.assertEqual(backup_size, 1)
        # On se connecte
        self.bp.resumeProducing()
        # On attend un peu
        yield wait(0.5)
        # On en envoie un deuxième
        msg2 = {"type": "perf", "value": "2"}
        yield self.bp.write(msg2)
        # On attend un peu
        yield wait(0.5)
        # On vérifie que les deux messages ont bien été envoyés dans le bon
        # ordre
        self.assertEqual(len(consumer.written), 2)
        for index, msg in enumerate([msg1, msg2]):
            msg_out = consumer.written[index]
            self.assertEqual(msg_out, msg)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_begin_with_backup(self):
        """
        Les messages sauvegardés doivent être prioritaires sur les messages temps-réel
        """
        msg1 = {"type": "perf", "value": "1"}
        msg2 = {"type": "perf", "value": "2"}
        yield self.bp.retry.put(json.dumps(msg1))
        self.bp.queue.append(msg2)
        #yield self.bp.processQueue()
        # On attend un peu
        #yield wait(0.5)
        for msg in [msg1, msg2]:
            next_msg = yield self.bp._getNextMsg()
            self.assertEqual(next_msg, msg)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_save_to_db(self):
        self.bp.pauseProducing()
        count = 42
        for i in range(count):
            msg = {"type": "perf", "value": "dummy"}
            self.bp.write(msg)
        yield self.bp._saveToDb()
        self.assertEqual(len(self.bp.queue), 0)
        db_size = yield self.bp.retry.qsize()
        self.assertEqual(db_size, count)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_stats_1(self):
        msg = {"type": "perf", "value": "dummy"}
        # On se connecte
        consumer = ConsumerStub()
        self.bp.consumer = consumer
        yield self.bp.resumeProducing()
        # On envoie des messages
        print "envoi 1"
        for i in range(10):
            self.bp.queue.append(msg)
        yield self.bp.processQueue()
        self.assertEqual(len(self.bp.queue), 0)
        # On se déconnecte (ça flushe les messages)
        self.bp.pauseProducing()
        # On envoie des messages (-> backup)
        print "envoi 2"
        for i in range(20):
            self.bp.queue.append(msg)
        yield self.bp.processQueue()
        self.assertEqual(len(self.bp.queue), 0)
        # Les messages sont maintenant soit envoyés soit en base de backup
        # on vide les buffers (pour fiabiliser le test)
        yield self.bp.retry.flush()
        backup_size = yield self.bp.retry.qsize()
        print (self.bp.retry._cache_isempty,
               len(self.bp.retry.buffer_in),
               len(self.bp.retry.buffer_out),
               len(consumer.written), backup_size)
        LOGGER.debug("Beginning assertions")
        self.assertEqual(backup_size, 20)
        self.assertEqual(len(consumer.written), 10)
        stats = yield self.bp.getStats()
        print stats
        self.assertEqual(stats, {
            "queue": 0,
            "backup": 20,
            "backup_in_buf": 0,
            "backup_out_buf": 0,
            })



class BusPublisherTestCase(unittest.TestCase):


    def setUp(self):
        self.bp = BusPublisher()
        client = ClientStub("testhostname", None, None)
        self.bp.setClient(client)


    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_accumulate_perfs(self):
        yield defer.succeed(None)
        count = 42
        self.bp.batch_send_perf = count
        msg = {"type": "perf", "value": "dummy"}
        # On se connecte
        self.bp.client.stub_connect()
        output = self.bp.client.channel.sent
        # on traite n-1 message, ce qui ne doit rien envoyer sur le bus
        for i in range(count - 1):
            yield self.bp.write(msg)
        self.assertEqual(output, [])
        # on en envoie un de plus, ce qui doit envoyer un message accumulé
        self.bp.write(msg)
        self.assertEqual(len(output), 1)
        sent = json.loads(output[0]["content"].body)
        self.assertEqual(len(sent["messages"]), count)


    def test_on_connect(self):
        """À la connexion, on demande des données à l'émetteur"""
        producer = Mock()
        self.bp.registerProducer(producer, True)
        self.bp.connectionInitialized()
        self.assertTrue(producer.resumeProducing.called)

    def test_pause_producing(self):
        """Si on est déconnecté, on pause l'émetteur"""
        producer = Mock()
        self.bp.registerProducer(producer, True)
        self.bp.connectionLost(None)
        self.assertTrue(producer.pauseProducing.called)

