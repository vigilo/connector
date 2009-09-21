# -*- coding: utf-8 -*-
from __future__ import absolute_import

import unittest

from vigilo.connector.converttoxml import text2xml

NS_AGGR = 'http://www.projet-vigilo.org/xmlns/aggr1'
NS_EVENT = 'http://www.projet-vigilo.org/xmlns/event1'
NS_PERF = 'http://www.projet-vigilo.org/xmlns/perf1'
NS_STATE = 'http://www.projet-vigilo.org/xmlns/state1'



class TestSequenceFunctions(unittest.TestCase):
    """ Test the connector functions """

    def test_event2xml(self):
        """ Test the connector function event2xml """
        dico = {'ns': NS_EVENT}
        
        # subfunction event2xml 
        self.assertEqual("""<event xmlns='%(ns)s'><timestamp>1165939739</timestamp><host>serveur1.example.com</host><ip>192.168.0.1</ip><service>Load</service><state>CRITICAL</state><message>CRITICAL: load avg: 12 10 10</message></event>""" % dico, text2xml("""event|1165939739|serveur1.example.com|192.168.0.1|Load|CRITICAL|CRITICAL: load avg: 12 10 10"""))

    def test_perf2xml(self):
        """ Test the connector function perf2xml """
        dico = {'ns': NS_PERF}

        # subfunction perf2xml 
        self.assertEqual("""<perf xmlns='%(ns)s'><timestamp>1165939739</timestamp><host>serveur1.example.com</host><datasource>Load</datasource><value>10</value></perf>""" % dico, text2xml("""perf|1165939739|serveur1.example.com|Load|10"""))

    def test_state2xml(self):
        """ Test the connector function state2xml """
        dico = {'ns': NS_STATE}

        # subfunction state2xml 
        self.assertEqual("""<state xmlns='%(ns)s'><timestamp>1239104006</timestamp><host>server.example.com</host><ip>192.168.1.1</ip><service>Load</service><statename>WARNING</statename><type>SOFT</type><attempt>2</attempt><message>WARNING: Load average is above 4 (4.5)</message></state>""" % dico, text2xml("""state|1239104006|server.example.com|192.168.1.1|Load|WARNING|SOFT|2|WARNING: Load average is above 4 (4.5)"""))

    def test_badinput2xml(self):
        """ Test the connector function text2xml with badinput"""
        # with bad input function shall return None
        self.assertEqual(None, text2xml(""))
        self.assertEqual(None, text2xml("azerty"))

if __name__ == "__main__": 
    unittest.main()
