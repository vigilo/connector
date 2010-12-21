# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Stockage des messages en attente dans une base de données SQLite.

Peut-être faudrait-il passer à l'API BdD de Twisted ?
(twisted.enterprise.adbapi)
Peut-être pas, vu que la latence de SQLite est suffisamment basse.
"""
from __future__ import absolute_import

from twisted.internet import reactor, defer
from sqlite3 import dbapi2 as sqlite
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)
from vigilo.common.gettext import translate
_ = translate(__name__)

class MustRetryError(Exception):
    """L'opération doit être retentée."""
    pass

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

        self.__table = table
        # XXX Il faudrait s'assurer que les différents composants
        # sont thread-safe, car check_same_thread=False désactive
        # toutes les vérifications faites normalement par pysqlite.
        self.__connection = sqlite.connect(filename, check_same_thread=False)

        # Création de la table. Si une erreur se produit, elle sera
        # tout simplement propagée à l'appelant, qui décidera de ce
        # qu'il convient de faire.
        cursor = self.__connection.cursor()
        try:
            cursor.execute('CREATE TABLE IF NOT EXISTS %s \
                    (id INTEGER PRIMARY KEY, msg TXT)' % table)
            self.__connection.commit()
        finally:
            cursor.close()

    def __del__(self):
        """Libère la base de données locale."""
        self.__connection.close()

    def store(self, msg):
        """
        Stocke un message XML dans la base de données locale en attendant
        de pouvoir le retransmettre à son destinataire final.

        @param msg: Le message à stocker.
        @type  msg: C{str}
        @return: Un booléen indiquant si l'opération a réussi ou non.
        @rtype: C{bool}
        @raise sqlite.OperationalError: Une exception levée par sqlite.
        """

        cursor = self.__connection.cursor()
        must_retry = False

        try:
            cursor.execute('INSERT INTO %s VALUES (null, ?)' %
                self.__table, (msg,))
            self.__connection.commit()
            cursor.close()
            return defer.succeed(True)

        except sqlite.OperationalError, e:
            self.__connection.rollback()
            if str(e) == "database is locked":
                LOGGER.warning(_("The database is locked"))
                must_retry = True
            else:
                LOGGER.exception(_("Got an exception:"))
                raise e

        except Exception, e:
            self.__connection.rollback()
            LOGGER.exception(_("Got an exception:"))
            raise e

        finally:
            cursor.close()

        if must_retry:
            return reactor.callLater(1, self.store, msg)
        return defer.fail()

    def unstore(self):
        """
        Renvoie un message issu de la base de données locale.
        Utilisez cette méthode lorsque la connexion avec le destinataire
        du message est rétablie pour retransmettre les données.

        @return: Un message stocké en attente de retransmission
            ou None lorsqu'il n'y a plus de message.
        @rtype: C{str} ou C{None}
        @raise sqlite.OperationalError: Une erreur possible
        @raise sqlite.Error:
        """
        cursor = self.__connection.cursor()
        must_retry = False

        try:
            cursor.execute('SELECT MIN(id) FROM %s' % self.__table)

            entry = cursor.fetchone()
            if entry is None:
                return defer.succeed(None)

            id_min = entry[0]
            del entry

            if id_min is None:
                return defer.succeed(None)

            res = cursor.execute('SELECT msg FROM %s WHERE id = ?' %
                self.__table, (id_min, ))

            entry = cursor.fetchone()
            if entry is None:
                raise MustRetryError()

            msg = entry[0]
            del entry
            cursor.execute('DELETE FROM %s WHERE id = ?' %
                self.__table, (id_min, ))

            if cursor.rowcount != 1:
                raise MustRetryError()

            self.__connection.commit()
            return defer.succeed(msg.encode('utf8'))

        except MustRetryError:
            must_retry = True

        except sqlite.OperationalError, e:
            self.__connection.rollback()
            if str(e) == "database is locked":
                LOGGER.warning(_("The database is locked"))
                must_retry = True
            else:
                LOGGER.exception(_("Got an exception:"))
                raise e

        except Exception, e:
            self.__connection.rollback()
            LOGGER.exception(_("Got an exception:"))
            raise e

        finally:
            cursor.close()

        if must_retry:
            return reactor.callLater(1, self.unstore)
        return self.succeed(None)

    def vacuum(self):
        """
        Effectue une réorganisation de la base de données
        afin d'optimiser les temps d'accès.
        """
        cursor = self.__connection.cursor()

        try:
            cursor.execute('VACUUM')
            self.__connection.commit()
        finally:
            cursor.close()
