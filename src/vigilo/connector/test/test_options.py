# -*- coding: utf-8 -*-
# pylint: disable-msg=W0212,R0903,R0904,C0111,W0613
# Copyright (C) 2006-2013 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import unittest


from vigilo.connector.options import parsePublications

class OptionTestCase(unittest.TestCase):
    """Teste L{options.parsePublications}"""

    def test_nominal(self):
        """Analyse de publication avec et sans durée de vie"""
        publications = { "un":     "uno",
                         "deux":   " dos ",
                         "trois":  "tres:42",
                         "quatre": " cuatro : 42 "}
        res_ok =       { "un":     ("uno", None),
                         "deux":   ("dos", None),
                         "trois":  ("tres",  42000),
                         "quatre": ("cuatro",  42000) }

        self.assertEqual(res_ok, parsePublications(publications))

    def test_error(self):
        """Analyse de publication (mauvaise syntaxe : cas 1)"""
        publications = { "un":  "uno:douze"}
        self.assertRaises(ValueError, parsePublications, publications)

    def test_error2(self):
        """Analyse de publication (mauvaise syntaxe : cas 2)"""
        publications = { "un":  "uno:42:ABCD"}
        self.assertRaises(ValueError, parsePublications, publications)

    def test_error3(self):
        """Analyse de publication (mauvaise syntaxe : cas 3)"""
        publications = { "un":  "uno:",
                       }
        self.assertRaises(ValueError, parsePublications, publications)

    def test_error4(self):
        """Analyse de publication (mauvaise syntaxe : cas 4)"""
        publications = { "un":  ":"}
        self.assertRaises(ValueError, parsePublications, publications)

