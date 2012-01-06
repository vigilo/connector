# -*- coding: utf-8 -*-
# vim: set et sw=4 ts=4 ai:
# pylint: disable-msg=R0904,C0111,W0613,W0212
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

from __future__ import absolute_import

import tempfile
import os
from shutil import rmtree, copy
import sqlite3
import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor, deferred

from twisted.internet import defer
from mock import patch, Mock

from vigilo.connector.confdb import ConfDB, NoConfDBError



class ConfDBTest(unittest.TestCase):
    """
    Gestion du protocole SNMP entre avec le démon
    """

    @deferred(timeout=5)
    @patch('signal.signal') # erreurs de threads
    def setUp(self, signal):
        self.tmpdir = tempfile.mkdtemp(prefix="test-connector-")
        dbpath = os.path.join(self.tmpdir, "conf.db")
        self._create_db(dbpath)
        self.confdb = ConfDB(dbpath)
        return defer.succeed(None)

    def tearDown(self):
        self.confdb.stopService()
        rmtree(self.tmpdir)


    def _create_db(self, db_path):
        db = sqlite3.connect(db_path)
        c = db.cursor()
        c.execute("""CREATE TABLE test (
                         idtest INTEGER NOT NULL,
                         PRIMARY KEY (idtest)
                     )""")
        c.execute("INSERT INTO test VALUES (1)")
        db.commit()
        c.close()
        db.close()


    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_reload(self):
        """Reconnexion à la base"""
        self.confdb.start_db()
        old_content = yield self.confdb._db.runQuery("SELECT idtest FROM test")
        # On change le fichier de la base de données
        dbpath = os.path.join(self.tmpdir, "conf.db")
        os.rename(dbpath, dbpath + ".orig.db")
        copy(dbpath + ".orig.db", dbpath)
        # On modifie la base de données
        conn = sqlite3.connect(dbpath)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO test VALUES (2)")
        conn.commit()
        cursor.close()
        conn.close()
        # On désactive la vérification du timestamp
        self.confdb._timestamp = 1
        # Reload et test
        self.confdb.reload()
        new_content = yield self.confdb._db.runQuery("SELECT idtest FROM test")
        self.assertNotEqual(len(old_content), len(new_content))


    @deferred(timeout=30)
    @defer.inlineCallbacks
    def test_reload_nochange(self):
        """Pas de reconnexion à la base si elle n'a pas changé"""
        self.confdb.start_db()
        yield self.confdb._db.runQuery("SELECT idtest FROM test")
        old_connection_threads = set(self.confdb._db.connections.keys())
        self.confdb.reload()
        yield self.confdb._db.runQuery("SELECT idtest FROM test")
        new_connection_threads = set(self.confdb._db.connections.keys())
        self.assertTrue(old_connection_threads <= new_connection_threads)


    def test_nodb(self):
        """La base n'existe pas"""
        confdb = ConfDB(os.path.join(self.tmpdir, "nonexistant.db"))
        self.assertRaises(NoConfDBError, confdb.start_db)


    def test_reload_nodb(self):
        """Rechargement alors que la base n'existe pas"""
        confdb = ConfDB(os.path.join(self.tmpdir, "nonexistant.db"))
        confdb._db = Mock()
        self.assertFalse(confdb._db.close.called)
        self.assertFalse(confdb._db.start.called)
