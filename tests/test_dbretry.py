# -*- coding: utf-8 -*-
"""
Teste la sauvegarde et la récupération d'un message en utilisant
une base de données SQLite locale via la classe DbRetry.
"""

import unittest
from vigilo.connector.store import DbRetry


class TestDbRetry(unittest.TestCase):
    """ 
    Teste la classe DbRetry.
    """

    def setUp(self):
        self.db_retry = DbRetry(':memory:', 'tmp_table')

    def tearDown(self):
        del self.db_retry

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
        for xml in xmls:
            self.db_retry.store(xml)

        # On vérifie qu'on peut récupérer les messages stockés
        # et qu'ils nous sont transmis dans le même ordre que
        # celui dans lequel on les a stocké, comme une FIFO.
        for xml in xmls:
            self.assertEquals(xml, self.db_retry.unstore())

        # Arrivé ici, la base doit être vide, donc unstore()
        # renvoie None pour indiquer la fin des messages.
        self.assertEquals(None, self.db_retry.unstore())

if __name__ == "__main__": 
    unittest.main()
