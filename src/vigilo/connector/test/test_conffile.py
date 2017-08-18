# -*- coding: utf-8 -*-
# vim: set et sw=4 ts=4 ai:
# Copyright (C) 2006-2016 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

# pylint: disable-msg=C0111,W0613,R0904,W0212
# - C0111: Missing docstring
# - W0613: Unused argument
# - R0904: Too many public methods
# - W0212: Access to a protected member of a client class

from __future__ import absolute_import, print_function

import tempfile
import os
from shutil import rmtree, copy
import sqlite3
import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module.
#from twisted.trial import unittest
from nose.twistedtools import reactor  # pylint: disable-msg=W0611
from nose.twistedtools import deferred


from twisted.internet import defer
from mock import Mock

from vigilo.connector.conffile import ConfDB



class ConfDBTest(unittest.TestCase):
    """
    Gestion du protocole SNMP entre avec le démon
    """

    @deferred(timeout=30)
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test-connector-")
        dbpath = os.path.join(self.tmpdir, "conf.db")
        self._create_db(dbpath)
        self.confdb = ConfDB(dbpath)
        return defer.succeed(None)

    @deferred(timeout=30)
    def tearDown(self):
        self.confdb.stopService()
        rmtree(self.tmpdir)
        return defer.succeed(None)


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
        self.confdb.reload()
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
        self.confdb.reload()
        self.confdb._db.close = Mock()
        self.confdb._db.start = Mock()
        yield self.confdb._db.runQuery("SELECT idtest FROM test")
        old_connection_threads = set(self.confdb._db.connections.keys())
        self.confdb.reload()
        yield self.confdb._db.runQuery("SELECT idtest FROM test")
        new_connection_threads = set(self.confdb._db.connections.keys())
        self.assertFalse(self.confdb._db.close.called)
        self.assertFalse(self.confdb._db.start.called)
        print(old_connection_threads, new_connection_threads)
        self.assertTrue(old_connection_threads <= new_connection_threads)


    @deferred(timeout=30)
    def test_nodb(self):
        """La base n'existe pas"""
        confdb = ConfDB(os.path.join(self.tmpdir, "nonexistant.db"))
        confdb._read_conf = Mock()
        confdb._rebuild_cache = Mock()
        confdb.reload()
        self.assertFalse(confdb._read_conf.called)
        self.assertFalse(confdb._rebuild_cache.called)
        return defer.succeed(None)


    @deferred(timeout=30)
    def test_reload_nodb(self):
        """Rechargement alors que la base n'existe pas"""
        confdb = ConfDB(os.path.join(self.tmpdir, "nonexistant.db"))
        confdb._db = Mock()
        self.assertFalse(confdb._db.close.called)
        self.assertFalse(confdb._db.start.called)
        return defer.succeed(None)
