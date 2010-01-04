# -*- coding: utf-8 -*-
from __future__ import absolute_import

import unittest

from vigilo.connector.converttoxml import text2xml

NS_AGGR = 'http://www.projet-vigilo.org/xmlns/aggr1'
NS_EVENT = 'http://www.projet-vigilo.org/xmlns/event1'
NS_PERF = 'http://www.projet-vigilo.org/xmlns/perf1'
NS_DOWNTIME = 'http://www.projet-vigilo.org/xmlns/downtime1'



class TestSequenceFunctions(unittest.TestCase):
    """ Test the connector functions """

    def test_event2xml(self):
        """ Test the connector function event2xml """
        dico = {'ns': NS_EVENT}
        
        # subfunction event2xml 
        self.assertEqual("""<event xmlns='%(ns)s'><timestamp>1165939739</timestamp><host>serveur1.example.com</host><service>Load</service><state>CRITICAL</state><message>CRITICAL: load avg: 12 10 10</message></event>""" % dico, text2xml("""event|1165939739|serveur1.example.com|Load|CRITICAL|CRITICAL: load avg: 12 10 10""").toXml())

    def test_perf2xml(self):
        """ Test the connector function perf2xml """
        dico = {'ns': NS_PERF}

        # subfunction perf2xml 
        self.assertEqual("""<perf xmlns='%(ns)s'><timestamp>1165939739</timestamp><host>serveur1.example.com</host><datasource>Load</datasource><value>10</value></perf>""" % dico, text2xml("""perf|1165939739|serveur1.example.com|Load|10""").toXml())

    def test_downtime2xml(self):
        """ Test the connector function downtime2xml """
        dico = {'ns': NS_DOWNTIME}

        # subfunction state2xml 
        self.assertEqual("""<downtime xmlns='%(ns)s'><timestamp>1239104006</timestamp><host>server.example.com</host><service>Load</service><type>DOWNTIMESTART</type><author>manager</author><comment>Mise en maintenance planifiee via Vigicore</comment></downtime>""" % dico, text2xml("""downtime|1239104006|server.example.com|Load|DOWNTIMESTART|manager|Mise en maintenance planifiee via Vigicore""").toXml())

    def test_badinput2xml(self):
        """ Test the connector function text2xml with badinput"""
        # with bad input function shall return None
        self.assertEqual(None, text2xml(""))
        self.assertEqual(None, text2xml("azerty"))

if __name__ == "__main__": 
    unittest.main()
