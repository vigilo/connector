# -*- coding: utf-8 -*-
# pylint: disable-msg=C0301,R0904
# Copyright (C) 2006-2020 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

from __future__ import absolute_import

import unittest

from vigilo.connector.serialize import parseMessage



class SerializeTestCase(unittest.TestCase):


    def test_event(self):
        """Conversion d'un évènement"""
        message = ("event|1165939739|serveur1.example.com|Load|CRITICAL|"
                   "CRITICAL: load avg: 12 10 10")
        expected = {
                "type": u"event",
                "timestamp": u"1165939739",
                "host": u"serveur1.example.com",
                "service": u"Load",
                "state": u"CRITICAL",
                "message": u"CRITICAL: load avg: 12 10 10",
                }
        self.assertEqual(expected, parseMessage(message))

    def test_event_unicode(self):
        """Conversion d'un évènement unicode"""
        message = "event|1165939739|\xC3\xA7|\xC3\xA8|\xC3\xA9|\xC3\xAA"
        expected = {
                "type": u"event",
                "timestamp": u"1165939739",
                "host": u"\u00E7",
                "service": u"\u00E8",
                "state": u"\u00E9",
                "message": u"\u00EA",
                }
        self.assertEqual(expected, parseMessage(message))

    def test_event_latin(self):
        """Conversion d'un évènement iso-8859-15"""
        message = "event|1165939739|\xE7|\xE8|\xE9|\xEA"
        expected = {
                "type": u"event",
                "timestamp": u"1165939739",
                "host": u"\u00E7",
                "service": u"\u00E8",
                "state": u"\u00E9",
                "message": u"\u00EA",
                }
        self.assertEqual(expected, parseMessage(message))


    def test_perf(self):
        """Conversion d'un message de perf"""
        message = "perf|1165939739|serveur1.example.com|Load|10"
        expected = {
                "type": u"perf",
                "timestamp": u"1165939739",
                "host": u"serveur1.example.com",
                "datasource": u"Load",
                "value": u"10",
                }
        self.assertEqual(expected, parseMessage(message))

    def test_perf_unicode(self):
        """Conversion d'un message de perf unicode"""
        message = "perf|1165939739|\xC3\xA7|\xC3\xA8|10"
        expected = {
                "type": u"perf",
                "timestamp": u"1165939739",
                "host": u"\u00E7",
                "datasource": u"\u00E8",
                "value": u"10",
                }
        self.assertEqual(expected, parseMessage(message))

    def test_perf_latin(self):
        """Conversion d'un message de perf en iso-8859-15"""
        message = "perf|1165939739|\xE7|\xE8|10"
        expected = {
                "type": u"perf",
                "timestamp": u"1165939739",
                "host": u"\u00E7",
                "datasource": u"\u00E8",
                "value": u"10",
                }
        self.assertEqual(expected, parseMessage(message))


    def test_state(self):
        """Conversion d'un message de state"""
        message = ("state|1239104006|server.example.com|192.168.1.1|Load|1|"
                   "SOFT|2|WARNING: Load average is above 4 (4.5)")
        expected = {
                "type": u"state",
                "timestamp": u"1239104006",
                "host": u"server.example.com",
                "service": u"Load",
                "code": u"1",
                "statetype": u"SOFT",
                "attempt": u"2",
                "ip": "192.168.1.1",
                "message": u"WARNING: Load average is above 4 (4.5)",
                }
        self.assertEqual(expected, parseMessage(message))


    def test_nagios(self):
        """Conversion d'un message nagios"""
        message = ("nagios|1239104006|PROCESS_HOST_CHECK_RESULT|"
                   "server.example.com|OK|Test")
        expected = {
                "type": u"nagios",
                "timestamp": u"1239104006",
                "host": u"server.example.com",
                "cmdname": u"PROCESS_HOST_CHECK_RESULT",
                "value": u"server.example.com;OK;Test",
                }
        self.assertEqual(expected, parseMessage(message))


    def test_badinput2xml(self):
        """Sérialisation d'un texte invalide"""
        self.assertEqual(None, parseMessage(""))
        self.assertEqual(None, parseMessage("azerty"))


