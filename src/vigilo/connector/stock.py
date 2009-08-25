# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

from sqlite3 import dbapi2 as sqlite
import time
from vigilo.common.conf import settings



def initializeDB(filename):
    """ function to initialize the DB the first time """
    connection = sqlite.connect(filename)
    cursor = connection.cursor()
    table = settings['VIGILO_MESSAGE_BACKUP_TABLE']
    cursor.execute('CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY, msg TXT)' % table)
    connection.commit()
    cursor.close()
    connection.close()

def stockmessage(filename, msg):
    """ 
    function to stock the message on a DataBase 
    return a boolean 
    True if the insertion in the DB is OK
    False otherwise
    """
    table = settings['VIGILO_MESSAGE_BACKUP_TABLE']
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


def unstockmessage(filename, function):
    """ 
    function to unstock the message on a DataBase
    return a Boolean (base is empty ?)
    the message unstocked is passed as argument of the function
    """
    msg = None
    table = settings['VIGILO_MESSAGE_BACKUP_TABLE']
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
            function(msg.encode('utf8'))
        except sqlite.OperationalError, e:
            connection.rollback()
            print e
            if e.__str__() == "database is locked":
                time.sleep(1)
                return unstockmessage(filename, function)
            else: 
                cursor.close()
                connection.close()
                raise e
        except sqlite.Error, e:
            connection.rollback()
            print e 
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
