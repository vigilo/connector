# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

from sqlite3 import dbapi2 as sqlite
import time




def initializeDB(filename):
    connection = sqlite.connect(filename)
    cursor = connection.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS connector (id INTEGER PRIMARY KEY, msg TXT)')
    connection.commit()
    cursor.close()
    connection.close()

def stockmessage(filename, msg):
    """ function to stock the message on a DataBase 
        return a boolean 
        True if the insertion in the DB is OK
        False otherwise
    """
    nom_table='connector'
    connection = sqlite.connect(filename)
    cursor = connection.cursor()

    try:
        cursor.execute('INSERT INTO connector VALUES (null, ?)', (msg,))
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
            return stockmessagesqlite(filename, msg)
        else:
            raise e
            return False


def unstockmessage(filename, function):
    """ function to unstock the message on a DataBase
        return a Boolean (base is empty ?)
        the message unstocked is passed as argument of the function
    """
    msg = None
    nom_table='connector'
    connection = sqlite.connect(filename)
    cursor = connection.cursor()
    cursor.execute('SELECT MIN(id) FROM connector')
    id_min = cursor.fetchone()[0]
    empty = True
    
    if id_min :
        empty = False
        try:
            cursor.execute('SELECT msg FROM connector WHERE id = ?', (id_min,))
            msg = cursor.fetchone()[0]
            cursor.execute('DELETE FROM connector WHERE id = ?', (id_min,))
            connection.commit()
            function(msg.encode('utf8'))
        except sqlite.OperationalError, e:
            connection.rollback()
            print e
            if e.__str__() == "database is locked":
                time.sleep(1)
                return unstockmessagesqlite(filename, function)
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
    connection = sqlite.connect(filename)
    cursor = connection.cursor()
    cursor.execute('VACUUM')
    connection.commit()
    cursor.close()
    connection.close()
