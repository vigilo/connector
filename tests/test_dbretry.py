# -*- coding: utf-8 -*-
"""
Teste la sauvegarde et la récupération d'un message en utilisant
une base de données SQLite locale via la classe DbRetry.
"""

import os
import tempfile
import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor, deferred

from twisted.internet import defer
from vigilo.connector.store import DbRetry


class TestDbRetry(unittest.TestCase):
    """
    Teste la classe DbRetry.
    """

    @deferred(timeout=5)
    def setUp(self):
        db_h, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_h)
        self.db = DbRetry(self.db_path, 'tmp_table')
        # le initdb est déjà fait en __init__ mais ça permet de s'assurer
        # qu'on est bien initialisés
        d = self.db.initdb()
        return d

    def tearDown(self):
        del self.db
        os.remove(self.db_path)


    @deferred(timeout=5)
    def test_retrieval(self):
        """
        Teste l'enregistrement et la récupération d'un message avec DbRetry.
        """
        xmls = [
            u'<abc foo="bar">def</abc>',
            u'<root />',
            u'<toto><tutu/><titi><tata/></titi></toto>',
        ]

        # On stocke un certain nombre de messages.
        puts = []
        for xml in xmls:
            d = self.db.put(xml)
            puts.append(d)
        main_d = defer.DeferredList(puts)

        # On vérifie qu'on peut récupérer les messages stockés
        # et qu'ils nous sont transmis dans le même ordre que
        # celui dans lequel on les a stocké, comme une FIFO.
        def try_get(r, xml):
            d = self.db.get()
            d.addCallback(self.assertEquals, xml)
            return d
        for xml in xmls:
            main_d.addCallback(try_get, xml)

        # Arrivé ici, la base doit être vide, donc unstore()
        # renvoie None pour indiquer la fin des messages.
        def try_final_get(r):
            d = self.db.get()
            d.addCallback(self.assertEquals, None)
            return d
        main_d.addCallback(try_final_get)

        return main_d

    @deferred(timeout=5)
    @defer.inlineCallbacks
    def test_put_buffer(self):
        """
        Teste le buffer d'entrée
        """
        xml = '<abc foo="bar">def</abc>'
        yield self.db.put(xml)
        self.assertEqual(len(self.db.buffer_in), 1)
        for i in range(self.db._buffer_in_max):
            yield self.db.put(xml)
        self.assertEqual(len(self.db.buffer_in), 0)
        backup_size = yield self.db.qsize()
        self.assertEqual(backup_size, self.db._buffer_in_max + 1)

    @deferred(timeout=5)
    @defer.inlineCallbacks
    def test_get_buffer(self):
        """
        Teste le buffer de sortie
        """
        xml = '<abc foo="bar">def</abc>'
        msg_count = (self.db._buffer_in_max + 1) * 2
        for i in range(msg_count):
            yield self.db.put(xml)
        self.assertEqual(len(self.db.buffer_out), 0)
        got_xml = yield self.db.get()
        self.assertEqual(len(self.db.buffer_out), msg_count - 1) # il y a un message en moins, c'est 'got_xml'
        backup_size = yield self.db.qsize()
        self.assertEqual(backup_size, len(self.db.buffer_out))


if __name__ == "__main__": 
    unittest.main()
