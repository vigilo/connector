# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
function to store message to a sqlite DataBase
"""
from __future__ import absolute_import

from sqlite3 import dbapi2 as sqlite
import time
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

        self.__table = table
        # XXX Il faudrait s'assurer que les différents composants
        # sont thread-safe, car check_same_thread=False désactive
        # toutes les vérifications faites normalement par pysqlite.
        self.__connection = sqlite.connect(filename, check_same_thread=False)
        cursor = self.__connection.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS %s \
                (id INTEGER PRIMARY KEY, msg TXT)' % table)
        self.__connection.commit()
        cursor.close()

    def __del__(self):
        """Libère la base de données locale."""
        self.__connection.close()

    def store(self, msg):
        """ 
        Stocke un message XML dans la base de données locale en attendant
        de pouvoir le retransmettre à son destinataire finale. 

        @param msg: Le message à stocker.
        @type  msg: C{str}
        @return: Un booléen indiquant si l'opération a réussi ou non.
        @rtype: C{bool}
        @raise sqlite.OperationalError: Une exception levée par sqlite.
        """

        cursor = self.__connection.cursor()

        try:
            cursor.execute('INSERT INTO %s VALUES (null, ?)' %
                self.__table, (msg,))
            self.__connection.commit()
            cursor.close()
            return True

        except sqlite.OperationalError, e:
            self.__connection.rollback()
            cursor.close()

            if e.__str__() == "database is locked":
                time.sleep(1)
                return self.store(msg)
            else:
                raise e
        return False

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
        cursor.execute('SELECT MIN(id) FROM %s' % self.__table)
        id_min = cursor.fetchone()[0]
        
        if id_min:
            try:
                cursor.execute('SELECT msg FROM %s WHERE id = ?' %
                    self.__table, (id_min,))
                msg = cursor.fetchone()[0]
                cursor.execute('DELETE FROM %s WHERE id = ?' %
                    self.__table, (id_min,))
                self.__connection.commit()
                cursor.close()
                return msg.encode('utf8')
 
            except sqlite.OperationalError, e:
                self.__connection.rollback()
                cursor.close()

                if str(e) == "database is locked":
                    LOGGER.warning(_("The database is locked"))
                    time.sleep(5)
                    return self.unstoremessage()
                else:
                    LOGGER.error(
                        _("Some operational error occured. " +
                          "Original error message was: %s") %
                        str(e))
                    raise e
 
            except sqlite.Error, e:
                self.__connection.rollback()
                cursor.close()
                LOGGER.error(
                    _("Some error occured. " +
                      "Original error message was: %s") %
                    str(e))
                raise e

        cursor.close()
        return None

    def vacuum(self):
        """Effectue une optimisation de la base de données."""
        cursor = self.__connection.cursor()
        cursor.execute('VACUUM')
        self.__connection.commit()
        cursor.close()


def initializeDB(filename, tablelist):
    """ function to initialize the DB the first time """
    connection = sqlite.connect(filename)
    cursor = connection.cursor()
    for table in tablelist : 
        cursor.execute('CREATE TABLE IF NOT EXISTS %s \
                (id INTEGER PRIMARY KEY, msg TXT)' % table)
    connection.commit()
    cursor.close()
    connection.close()

def storemessage(filename, msg, table):
    """ 
    function to store the message on a DataBase 
    @param msg: The message to store
    @param filename: The filename of the DB used to store message
    @type  filename: C{str}
    @type  msg: C{str}
    return: True if the message was stored, False otherwise
    @raise e: when the sqlite library raise a sqlite.OperationalError.

    """
    connection = sqlite.connect(filename)
    cursor = connection.cursor()

    try:
        cursor.execute('INSERT INTO %s VALUES (null, ?)' % table, (msg,))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except sqlite.OperationalError, e:
        connection.rollback()
        if e.__str__() == "database is locked":
            cursor.close()
            connection.close()
            time.sleep(1)
            return storemessage(filename, msg)
        else:
            raise e
    return False


def unstoremessage(filename, table):
    """ 
    function to unstore the message on a DataBase
    @param function: The function to treat the message
    @type  filename: C{str}
    return: True if the DB is the database is empty, the msg otherwise
    @raise e: When the sqlite library raise a sqlite.OperationalError or
              sqlite.Error.
    """
    msg = None
    connection = sqlite.connect(filename)
    cursor = connection.cursor()
    cursor.execute('SELECT MIN(id) FROM %s' % table)
    id_min = cursor.fetchone()[0]
    empty = True
    
    if id_min :
        empty = False
        try:
            cursor.execute('SELECT msg FROM %s WHERE id = ?' % table, (id_min,))
            msg = cursor.fetchone()[0]
            cursor.execute('DELETE FROM %s WHERE id = ?' % table, (id_min,))
            connection.commit()
            return msg.encode('utf8')
        except sqlite.OperationalError, e:
            connection.rollback()
            if e.__str__() == "database is locked":
                LOGGER.warning(_(e.__str__()))
                time.sleep(5)
                return unstoremessage(filename, table)
            else: 
                LOGGER.error(_(e.__str__()))
                cursor.close()
                connection.close()
                raise e
        except sqlite.Error, e:
            connection.rollback()
            LOGGER.warning(_(e.__str__()))
    cursor.close()
    connection.close()
    return empty


def sqlitevacuumDB(filename):
    """ function to vacuum (clean) the DB """
    connection = sqlite.connect(filename)
    cursor = connection.cursor()
    cursor.execute('VACUUM')
    connection.commit()
    cursor.close()
    connection.close()