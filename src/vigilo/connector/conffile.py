# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2015 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Chargement d'une base sqlite de configuration générée par Vigiconf.
"""

from __future__ import absolute_import
from __future__ import with_statement

import os
import signal

from vigilo.connector import json

from twisted.internet import task
from twisted.application.service import Service
from twisted.enterprise import adbapi

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)
from vigilo.common.gettext import translate
_ = translate(__name__)



class NoConfError(Exception):
    pass



class ConfFile(Service, object):
    """
    Accès à la configuration fournie par VigiConf, classe abstraite.
    """


    def __init__(self, path):
        self.path = path
        self._timestamp = 0
        self._reload_task = task.LoopingCall(self.reload)
        self._cache = {}
        self._prev_sighup_handler = None


    def startService(self):
        Service.startService(self)

        if self._prev_sighup_handler is None:
            # Sauvegarde du handler courant pour SIGHUP
            # et ajout de notre propre handler pour recharger
            # le connecteur (lors d'un service ... reload).
            self._prev_sighup_handler = signal.getsignal(signal.SIGHUP)
            signal.signal(signal.SIGHUP, self._sighup_handler)

        if not self._reload_task.running:
            self._reload_task.start(10) # toutes les 10s


    def stopService(self):
        Service.stopService(self)
        if self._reload_task.running:
            self._reload_task.stop()


    def _sighup_handler(self, signum, frames):
        """
        Gestionnaire du signal SIGHUP: recharge la conf.

        @param signum: Signal qui a déclenché le rechargement (= SIGHUP).
        @type signum: C{int} ou C{None}
        @param frames: Frames d'exécution interrompues par le signal.
        @type frames: C{list}
        """
        LOGGER.info(_("Received signal to reload the configuration"))
        self.reload()
        # On appelle le précédent handler s'il y en a un.
        # Eventuellement, il s'agira de signal.SIG_DFL ou signal.SIG_IGN.
        if callable(self._prev_sighup_handler):
            self._prev_sighup_handler(signum, frames)


    def reload(self):
        """
        Provoque un rechargement de la conf si elle a changé
        """
        if not os.path.exists(self.path):
            LOGGER.warning(_("No configuration yet!"))
            return
        current_timestamp = os.stat(self.path).st_mtime
        if current_timestamp <= self._timestamp:
            return # ça n'a pas changé
        LOGGER.debug("Re-reading the configuration")
        self._timestamp = current_timestamp
        self._read_conf()
        self._rebuild_cache()


    def _read_conf(self):
        raise NotImplementedError


    def _rebuild_cache(self):
        self._cache = {}



class ConfDB(ConfFile):
    """
    Accès à la configuration fournie par VigiConf (dans une base SQLite)
    @ivar _db: Instance de connexion ADBAPI, voir
        U{http://twistedmatrix.com/documents/10.1.0/core/howto/rdbms.html}.
    @type _db: C{twisted.enterprise.adbapi.ConnectionPool}
    """


    def __init__(self, path):
        super(ConfDB, self).__init__(path)
        self._db = None


    def stopService(self):
        super(ConfDB, self).stopService()
        if self._db is not None:
            self._db.close()


    def _read_conf(self):
        if self._db is None:
            # threads: http://twistedmatrix.com/trac/ticket/3629
            self._db = adbapi.ConnectionPool("sqlite3", self.path,
                                             check_same_thread=False)
            LOGGER.debug("Connected to the configuration database")
        else:
            self._db.close()
        self._db.start()



class ConfFileJSON(ConfFile):
    """
    Accès à la configuration fournie par VigiConf (dans un fichier JSON)
    """


    def __init__(self, path):
        super(ConfFileJSON, self).__init__(path)
        self.data = None


    def _read_conf(self):
        with open(self.path) as conffile:
            self.data = json.load(conffile)
