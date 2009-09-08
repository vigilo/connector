# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
function to stock message to a sqlite DataBase
"""
from __future__ import absolute_import

from sqlite3 import dbapi2 as sqlite
import time
from vigilo.common.conf import settings
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)
from vigilo.common.gettext import translate
_ = translate(__name__)


def initializeDB(filename, tablelist):
    """ function to initialize the DB the first time """
    connection = sqlite.connect(filename)
    cursor = connection.cursor()
    #table = settings['VIGILO_MESSAGE_BACKUP_TABLE']
    for table in tablelist : 
        cursor.execute('CREATE TABLE IF NOT EXISTS %s \
                (id INTEGER PRIMARY KEY, msg TXT)' % table)
    connection.commit()
    cursor.close()
    connection.close()

def stockmessage(filename, msg, table):
    """ 
    function to stock the message on a DataBase 
    @param msg: The message to stock
    @param filename: The filename of the DB used to stock message
    @type  filename: C{str}
    @type  msg: C{str}
    return: True if the message was stocked, False otherwise
    @raise e: when the sqlite library raise a sqlite.OperationalError.

    """
    #table = settings['VIGILO_MESSAGE_BACKUP_TABLE']
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
            return stockmessage(filename, msg)
        else:
            raise e
    return False


def unstockmessage(filename, function, table):
    """ 
    function to unstock the message on a DataBase
    @param function: The function to treat the message
    @type  filename: C{str}
    return: True if the DB is the database is empty, False otherwise
    @raise e: When the sqlite library raise a sqlite.OperationalError or
              sqlite.Error.
    """
    msg = None
    #table = settings['VIGILO_MESSAGE_BACKUP_TABLE']
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
            function( msg.encode('utf8'))
        except sqlite.OperationalError, e:
            connection.rollback()
            if e.__str__() == "database is locked":
                LOGGER.warning(_(e.__str__()))
                time.sleep(1)
                return unstockmessage(filename, function)
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
