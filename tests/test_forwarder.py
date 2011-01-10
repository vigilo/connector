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


class TestForwarder(unittest.TestCase):
    """Teste la sauvegarde locale de messages en cas d'erreur."""

    @deferred(timeout=5)
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


if __name__ == "__main__":
    unittest.main()

