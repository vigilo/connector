# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Stockage des messages en attente dans une base de données SQLite.

Peut-être faudrait-il passer à l'API BdD de Twisted ?
(twisted.enterprise.adbapi)
Peut-être pas, vu que la latence de SQLite est suffisamment basse.
"""
from __future__ import absolute_import

import sqlite3
from collections import deque

from twisted.internet import defer, task, reactor
from twisted.words.xish import domish
from twisted.enterprise import adbapi

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)
from vigilo.common.gettext import translate
_ = translate(__name__)


class DbRetry(object):
    """
    Implémente une base de données locale qui peut-être utilisée pour stocker
    des messages XML lorsque le destinataire final n'est pas joignable.
    """

    def __init__(self, filename, table):
        """
        Instancie une base de données locale pour la réémission des messages.

        @param filename: Le nom du fichier qui contiendra la base de données.
        @type filename: C{str}
        @param table: Le nom de la table SQL dans ce fichier.
        @type table: C{str}
        """

        self.buffer_in = deque()
        self.buffer_out = deque()
        self._buffer_in_max = 1000
        self._buffer_out_min = 1000
        self._load_batch_size = self._buffer_out_min * 10
        self._saving_buffer_in = False
        self._cache_isempty = False
        self._is_flushing_d = None
        self.initialized = False
        self._table = table
        # threads: http://twistedmatrix.com/trac/ticket/3629
        self._db = adbapi.ConnectionPool("sqlite3.dbapi2", filename,
                                         check_same_thread=False)

    def initdb(self):
        if self.initialized:
            return defer.succeed(None)
        # Création de la table. Si une erreur se produit, elle sera
        # tout simplement propagée à l'appelant, qui décidera de ce
        # qu'il convient de faire.
        d = self._db.runOperation('CREATE TABLE IF NOT EXISTS %s '
                    '(id INTEGER PRIMARY KEY, msg TXT)' % self._table)
        def set_empty_cache(count_result):
            self._cache_isempty = (count_result[0][0] == 0)
        def after_init(r):
            self.initialized = True
            return r
        d.addCallback(lambda x: self._db.runQuery("SELECT count(*) FROM %s"
                                                  % self._table))
        d.addCallback(set_empty_cache)
        d.addCallback(after_init)
        return d

    def flush(self):
        """
        Sauvegarde tout en base, avant de quitter
        """
        if self._is_flushing_d is not None:
            self._is_flushing_d.addCallback(lambda _x: self.flush())
            return self._is_flushing_d
        LOGGER.debug("Flushing the buffers into the base")
        self._is_flushing_d = self._db.runInteraction(self._flush)
        def cb(_x):
            LOGGER.debug("Done flushing")
            self._is_flushing_d = None
        def eb(f):
            LOGGER.debug("Error flushing: %s", f)
            self._is_flushing_d = task.deferLater(reactor, 0.5, self.flush)
            return self._is_flushing_d
        self._is_flushing_d.addCallbacks(cb, eb)
        return self._is_flushing_d

    def _flush(self, txn):
        """
        Fait réellement le flush, doit être lancé par self._db.runInteraction()
        """
        def get_from_buffer_out():
            while len(self.buffer_out) > 0:
                yield self.buffer_out.popleft()
        if self.buffer_out:
            try:
                txn.executemany("INSERT INTO %s VALUES (?, ?)"
                                % self._table, get_from_buffer_out())
            except sqlite3.IntegrityError, e:
                LOGGER.debug("IntegrityError while flushing: %s", e)
            except sqlite3.OperationalError, e:
                LOGGER.debug("OperationalError while flushing: %s", e)
            self._cache_isempty = False
        def get_from_buffer_in():
            while len(self.buffer_in) > 0:
                msg = self.buffer_in.popleft()
                if isinstance(msg, domish.Element):
                    msg = msg.toXml()
                yield (msg, )
        if self.buffer_in:
            txn.executemany("INSERT INTO %s VALUES (null, ?)" % self._table,
                            get_from_buffer_in())
            self._cache_isempty = False

    def qsize(self):
        def set_cache(dbresult): # simple sécurité
            self._cache_isempty = (dbresult[0][0] == 0)
            return dbresult
        def add_buffers(dbresult):
            return dbresult[0][0] + \
                   len(self.buffer_out) + \
                   len(self.buffer_in)
        d = self._db.runQuery("SELECT count(*) FROM %s" % self._table)
        d.addCallback(set_cache)
        d.addCallback(add_buffers)
        return d

    # -- Récupération depuis la base

    def get(self):
        """API similaire à C{Queue.Queue}. @see: L{pop}()"""
        return self.pop()

    def pop(self):
        """
        Récupère le prochain message en attente. Cette récupération est
        faite depuis le buffer, qui est re-rempli s'il atteint le seuil
        minimum.
        @return: Le prochain message, dans un C{Deferred}
        @rtype: C{Deferred}
        """
        def get_from_buffer(r): # pylint: disable-msg=W0612
            try:
                index, msg = self.buffer_out.popleft()
            except IndexError:
                return None # pas de message dans le buffer
            else:
                return msg
        if len(self.buffer_out) <= self._buffer_out_min:
            if not self._cache_isempty:
                # on prend dans la base
                d = self._db.runInteraction(self._fill_buffer_out)
            else:
                # la base est vide, on prend dans le buffer d'entrée
                self._get_from_buffer_in()
                d = defer.succeed(None)
        else:
            # pas besoin de remplir le buffer
            d = defer.succeed(None)
        d.addCallback(get_from_buffer)
        return d

    def _fill_buffer_out(self, txn):
        """
        Re-remplis le buffer de sortie depuis la base SQLite.
        @note: Executé dans un thread par runInteraction, donc on a le droit
            de bloquer
        """
        msg_count = self._load_batch_size
        try:
            txn.execute("SELECT id, msg FROM %s ORDER BY id LIMIT %s"
                        % (self._table, msg_count))
        except sqlite3.OperationalError, e:
            LOGGER.warning(_("Could not fill the output buffer: %s"), e)
            return
        msgs = txn.fetchall()
        if not msgs:
            # base vide, on utilise le contenu du buffer d'entrée
            self._get_from_buffer_in()
            if not self._cache_isempty:
                # on vient de vider la base, on en profite pour nettoyer
                reactor.callLater(0.5, self._vacuum)
            LOGGER.debug("Backup database is now empty")
            self._cache_isempty = True
            return
        min_id = msgs[0][0]
        max_id = msgs[-1][0]
        self.buffer_out.extend(msgs) # On stocke (id, msg)
        txn.execute("DELETE FROM %s WHERE id >= ? AND id <= ?" % self._table,
                    (min_id, max_id))
        LOGGER.debug("Filled output buffer with %d messages from database",
                     len(msgs))

    def _get_from_buffer_in(self):
        """
        Quand la base est vide, on utilise le contenu de la file d'entrée
        temporaire
        """
        if not len(self.buffer_in):
            return
        LOGGER.debug("Filling output buffer with %d messages from "
                     "input buffer", len(self.buffer_in))
        while len(self.buffer_in) > 0:
            msg = self.buffer_in.popleft()
            self.buffer_out.append((None, msg))

    def _vacuum(self):
        LOGGER.debug("Starting VACUUM")
        d = self._db.runOperation("VACUUM")
        def eb(f):
            f.trap(sqlite3.OperationalError, sqlite3.IntegrityError)
            # on ignore l'erreur, c'est pas grave, on fera un vacuum la
            # prochaine fois
            LOGGER.info(_("Could not VACUUM the database: %s"),
                        f.getErrorMessage())
            # On met la cache à False pour provoquer un vacuum
            self._cache_isempty = False
        d.addErrback(eb)
        def log(r):
            LOGGER.debug("VACUUM is done")
        d.addBoth(log)
        return d

    # -- Insertion dans la base

    def put(self, msg):
        """API similaire à C{Queue.Queue}. @see: L{append}"""
        return self.append(msg)

    def append(self, msg):
        """
        Enregristre le message en base. L'enregistrement est fait dans le
        buffer d'entrée, qui est vidé en base SQLite s'il atteint le seuil
        maximum défini.
        @return: un C{Deferred} qui se déclenche quand l'insertion est
            effectivement terminée (éventuellement en base)
        @rtype: C{Deferred}
        """
        self.buffer_in.append(msg)
        if len(self.buffer_in) > self._buffer_in_max:
            return self._db.runInteraction(self._save_buffer_in)
        else:
            return defer.succeed(None)

    def _save_buffer_in(self, txn):
        """
        Enregistre en base SQLite la totalité du buffer d'entrée. Un lock
        est mis en place pour ne jamais exécuter cette fonction deux fois
        simultanément.
        @note: Executé dans un thread par runInteraction, donc on a le droit
            de bloquer
        """
        if self._saving_buffer_in:
            return
        total = len(self.buffer_in)
        if total == 0:
            return
        self._saving_buffer_in = True
        def get_from_buffer_in():
            while len(self.buffer_in) > 0:
                msg = self.buffer_in.popleft()
                if isinstance(msg, domish.Element):
                    msg = msg.toXml()
                yield (msg, )
        try:
            txn.executemany("INSERT INTO %s VALUES (null, ?)" % self._table,
                            get_from_buffer_in())
        except sqlite3.OperationalError, e:
            LOGGER.warning(_("Could not fill the output buffer: %s"), e)
        else:
            LOGGER.debug("Saved %d messages from the input buffer", total)
            self._cache_isempty = False
        self._saving_buffer_in = False

