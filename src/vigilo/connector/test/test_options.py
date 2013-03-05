# -*- coding: utf-8 -*-
# pylint: disable-msg=W0212,R0903,R0904,C0111,W0613
# Copyright (C) 2006-2013 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import unittest


from vigilo.connector.options import parsePublications

class OptionTestCase(unittest.TestCase):
    """Teste L{options.parsePublications}"""

    def test_basique(self):
        """Analyse basique de publication sans durée de vie"""
        publications = { "un":    "testa",
                         "deux":  "testb",
                         "trois": "testc "}
        res_ok =       { "un":    ("testa", None),
                         "deux":  ("testb", None),
                         "trois": ("testc", None)}

        self.assertEqual(res_ok, parsePublications(publications))

    def test_basique(self):
        """Analyse basique de publication avec une durée de vie"""
        publications = { "un":     "un:42",
                         "deux":   "deux: 42",
                         "trois":  " trois : 42 ",
                         "quatre": " testc:42"}
        res_ok =       { "un":     ("un",     42000),
                         "deux":   ("deux",   42000),
                         "trois":  ("trois",  42000),
                         "quatre": ("testc",  42000) }

        self.assertEqual(res_ok, parsePublications(publications))

    def test_multiple(self):
        """Analyse de publication avec une durée de vie (données multiples)"""
        publications = { "un":   "testa:42",
                         "deux": "testb:12"}
        res_ok =       { "un":   ("testa", 42000),
                         "deux": ("testb",  12000) }

        self.assertEqual(res_ok, parsePublications(publications))

    def test_multiple2(self):
        """Analyse de publication avec et sans durée de vie"""
        publications = { "un":   "testa",
                         "deux": "testb:12"}
        res_ok =       { "un":   ("testa", None),
                         "deux": ("testb",  12000) }

        self.assertEqual(res_ok, parsePublications(publications))

    def test_erreur(self):
        """Analyse de publication (mauvaise syntaxe : cas 1)"""
        publications = { "un":  "test2:douze",
                       }
        self.assertRaises(ValueError, parsePublications, publications)

    def test_erreur2(self):
        """Analyse de publication (mauvaise syntaxe : cas 2)"""
        publications = { "un":  "test2:42:ABCD",
                       }
        self.assertRaises(ValueError, parsePublications, publications)

    def test_erreur3(self):
        """Analyse de publication (mauvaise syntaxe : cas 3)"""
        publications = { "un":  "test2:",
                       }
        self.assertRaises(ValueError, parsePublications, publications)

    def test_erreur4(self):
        """Analyse de publication (mauvaise syntaxe : cas 3)"""
        publications = { "un":  ":",
                       }
        self.assertRaises(ValueError, parsePublications, publications)

