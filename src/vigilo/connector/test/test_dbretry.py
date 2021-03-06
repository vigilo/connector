# -*- coding: utf-8 -*-
# Copyright (C) 2006-2020 CS GROUP - France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

# pylint: disable-msg=C0111,W0613,R0904,W0212
# - C0111: Missing docstring
# - W0613: Unused argument
# - R0904: Too many public methods
# - W0212: Access to a protected member of a client class

"""
Teste la sauvegarde et la récupération d'un message en utilisant
une base de données SQLite locale via la classe DbRetry.
"""
from __future__ import print_function

import os
import tempfile
import unittest

from mock import Mock

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module.
#from twisted.trial import unittest
from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred

from twisted.internet import defer
from vigilo.connector.store import DbRetry
from vigilo.connector.test.helpers import ConnectionPoolStub, wait


class TestDbRetry(unittest.TestCase):
    """
    Teste la classe DbRetry.
    """

    @deferred(timeout=30)
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


    @deferred(timeout=30)
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
            d.addCallback(self.assertEqual, xml)
            return d
        for xml in xmls:
            main_d.addCallback(try_get, xml)

        # Arrivé ici, la base doit être vide, donc unstore()
        # renvoie None pour indiquer la fin des messages.
        def try_final_get(r):
            d = self.db.get()
            d.addCallback(self.assertEqual, None)
            return d
        main_d.addCallback(try_final_get)

        return main_d

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_put_buffer(self):
        """
        Teste le buffer d'entrée
        """
        xml = '<abc foo="bar">def</abc>'
        yield self.db.put(xml)
        self.assertEqual(len(self.db.buffer_in), 1)
        for _i in range(self.db._buffer_in_max):
            yield self.db.put(xml)
        self.assertEqual(len(self.db.buffer_in), 0)
        backup_size = yield self.db.qsize()
        self.assertEqual(backup_size, self.db._buffer_in_max + 1)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_get_buffer(self):
        """
        Teste le buffer de sortie
        """
        xml = '<abc foo="bar">def</abc>'
        msg_count = (self.db._buffer_in_max + 1) * 2
        for _i in range(msg_count):
            yield self.db.put(xml)
        self.assertEqual(len(self.db.buffer_out), 0)
        yield self.db.get()
        self.assertEqual(len(self.db.buffer_out), msg_count - 1) # il y a un message en moins, c'est 'got_xml'
        backup_size = yield self.db.qsize()
        self.assertEqual(backup_size, len(self.db.buffer_out))

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_qsize(self):
        """
        Teste le buffer de sortie
        """
        xml = '<abc foo="bar">def</abc>'
        msg_count = (self.db._buffer_in_max + 1)
        for _i in range(msg_count):
            self.db.buffer_in.append(xml)
            self.db.buffer_out.append((None, xml))
        yield self.db.flush()
        self.assertEqual(len(self.db.buffer_in), 0)
        self.assertEqual(len(self.db.buffer_out), 0)
        backup_size = yield self.db.qsize()
        self.assertEqual(backup_size, msg_count * 2)

    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_vacuum(self):
        """
        Teste le nettoyage de la base
        """
        db = DbRetry(self.db_path, 'tmp_table')
        stub = ConnectionPoolStub(db._db)
        db._db = stub

        xml = '<abc foo="bar">def</abc>'
        yield db.put(xml)
        yield db.flush()

        # On récupère 2 fois un élément: une fois pour vider la base, et la
        # seconde fois déclenche un VACUUM
        yield db.get()
        yield db.get()

        # On attend un peu, le VACUUM est décalé
        yield wait(1)
        print(stub.requests)
        self.assertEqual( (("VACUUM", ), {}), stub.requests.pop() )

    @deferred(timeout=30)
    def test_flush_double(self):
        """
        Un double flush doit être mis en file d'attente
        """
        db = DbRetry(self.db_path, 'tmp_table')
        db._flush = Mock()
        self.assertTrue(db._is_flushing_d is None)

        d = db.flush()
        self.assertTrue(db._is_flushing_d is not None)
        def check(r):
            self.assertTrue(db._flush.called)
            self.assertEqual(len(db._flush.call_args_list), 2)
            # le 2e appel a été déclenché avec le 1er
            self.assertTrue(d2.called)
        d2 = db.flush()
        d.addCallback(check)
        return d


