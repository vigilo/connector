# -*- coding: utf-8 -*-
'''
Created on 30 sept. 2009

@author: smoignar
'''
# Teste la sauvegarde d'un message nagios dans la database 
# Cas ou le bus n'est pas actif 
from __future__ import absolute_import
import unittest
#from subprocess import Popen, PIPE
#from os import kill, remove, putenv, system, getcwd
#import time
#from socket import socket, AF_UNIX, SOCK_STREAM
from vigilo.common.conf import settings

import sqlite3

NS_EVENT = 'http://www.projet-vigilo.org/xmlns/event1'
NS_PERF = 'http://www.projet-vigilo.org/xmlns/perf1'


class TestSauveDB(unittest.TestCase):
    # Message from Socket impossible to forward(XMPP BUS not connected)
    # Vérification que le message est sauvegardé dans la database 
    def test_startconnector(self):
        from wokkel import client
        from twisted.words.protocols.jabber.jid import JID
        xmpp_client = client.XMPPClient(
                JID(settings['VIGILO_CONNECTOR_JID']),
                settings['VIGILO_CONNECTOR_PASS'],
                settings['VIGILO_CONNECTOR_XMPP_SERVER_HOST'])
        _service = JID(settings.get('VIGILO_CONNECTOR_XMPP_PUBSUB_SERVICE',
                                    None))
        from vigilo.connector.sockettonodefw import SocketToNodeForwarder
        sr = settings.get('VIGILO_SOCKETR', None)
        bkp = settings['VIGILO_MESSAGE_BACKUP_FILE']
        message_publisher = SocketToNodeForwarder(
                sr,
                bkp,
                settings['VIGILO_MESSAGE_BACKUP_TABLE_TOBUS'],
                settings.get('VIGILO_CONNECTOR_TOPIC_PUBLISHER', None),
                _service)
        message_publisher.setHandlerParent(xmpp_client)


        # connection à la database puis récupération du nombre d'enregistrement
        base = settings.get('VIGILO_MESSAGE_BACKUP_FILE',[])
        conn = sqlite3.connect(base)
        cur = conn.cursor()
        # récupération du nombre de message dans la table avant send
        requete = 'select count(*) from ' + settings.get('VIGILO_MESSAGE_BACKUP_TABLE_TOBUS',[])
        cur.execute(requete)
        raw_av = cur.fetchone()[0]

        #message_publisher.__factory.protocol.lineReceived("oneToOne|test@localhost|event|1165939739|serveur1.example.com|192.168.0.1|Load|CRITICAL|CRITICAL: load avg: 12 10 10\n")
        from vigilo.connector.converttoxml import text2xml
        xml1 = text2xml(
                "oneToOne|test@localhost|event|1165939739|serveur1.example." + 
                "com|192.168.0.1|Load|CRITICAL|CRITICAL: load avg: 12 10 10")
        message_publisher.sendOneToOneXml(xml1)
        xml2 = text2xml(
                "event|1165939739|serveur1.example." +
                "com|192.168.0.1|Load|CRITICAL|CRITICAL: load avg: 12 10 10")
        message_publisher.publishXml(xml2)
        
        #message_publisher.xmlstream = 12
        #message_publisher.sendOneToOneXml(xml1)
        #message_publisher.publishXml(xml2)
        nb_msg_save_in_DB = 2

        # on enleve la socket qui ne peut etre enlever via le reactor 
        #  (il n'est pas démarré)
        import os
        os.remove(sr)
        os.remove(bkp)

        

    
        # récupération du nombre de message dans la table après send
        cur.execute(requete)
        raw_ap = cur.fetchone()[0]
             
        cur.close()
        conn.close()
        
        # vérification que les messages ont été sauvegardés
        self.assertEqual(raw_av + nb_msg_save_in_DB  ,raw_ap)      

    
if __name__ == "__main__": 
    unittest.main()
