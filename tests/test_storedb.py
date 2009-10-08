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
from wokkel import client
from twisted.words.protocols.jabber.jid import JID
from vigilo.connector.sockettonodefw import SocketToNodeForwarder
from vigilo.connector.nodetosocketfw import NodeToSocketForwarder
from vigilo.connector.converttoxml import text2xml
from vigilo.connector.store import DbRetry

import sqlite3

NS_EVENT = 'http://www.projet-vigilo.org/xmlns/event1'
NS_PERF = 'http://www.projet-vigilo.org/xmlns/perf1'


class TestSauveDB(unittest.TestCase):
    """ 
    Message from Socket impossible to forward(XMPP BUS not connected)
    Vérification que le message est sauvegardé dans la database 
    """
    def test_sockettonodeDbStore(self):
        """ 
        test the storage of message in case of XMPP server non working 
        in the socketToNode module
        """
        nb_msg_save_in_DB = 0

        dbfilename = settings['VIGILO_MESSAGE_BACKUP_FILE']
        dbtable =  settings['VIGILO_MESSAGE_BACKUP_TABLE_TOBUS']
        # on initialise la database
        store = DbRetry(dbfilename, dbtable)
        store.__del__()
        # connection à la database puis récupération du nombre d'enregistrement
        base = settings.get('VIGILO_MESSAGE_BACKUP_FILE',[])
        conn = sqlite3.connect(base)
        cur = conn.cursor()
        # récupération du nombre de message dans la table avant send
        requete = 'select count(*) from ' + dbtable
        cur.execute(requete)
        raw_av = cur.fetchone()[0]


        xmpp_client = client.XMPPClient(
                JID(settings['VIGILO_CONNECTOR_JID']),
                settings['VIGILO_CONNECTOR_PASS'],
                settings['VIGILO_CONNECTOR_XMPP_SERVER_HOST'])
        _service = JID(settings.get('VIGILO_CONNECTOR_XMPP_PUBSUB_SERVICE',
                                    None))
        sr = settings.get('VIGILO_SOCKETR', None)
        message_publisher = SocketToNodeForwarder(
                sr,
                dbfilename,
                dbtable,
                settings.get('VIGILO_CONNECTOR_TOPIC_PUBLISHER', None),
                _service)
        message_publisher.setHandlerParent(xmpp_client)



        #message_publisher.__factory.protocol.lineReceived("oneToOne|test@localhost|event|1165939739|serveur1.example.com|192.168.0.1|Load|CRITICAL|CRITICAL: load avg: 12 10 10\n")
        xml1 = text2xml(
                "oneToOne|test@localhost|event|1165939739|serveur1.example." + 
                "com|192.168.0.1|Load|CRITICAL|CRITICAL: load avg: 12 10 10")
        message_publisher.sendOneToOneXml(xml1)
        nb_msg_save_in_DB += 1
        
        xml2 = text2xml(
                "event|1165939739|serveur1.example." +
                "com|192.168.0.1|Load|CRITICAL|CRITICAL: load avg: 12 10 10")
        message_publisher.publishXml(xml2)
        nb_msg_save_in_DB += 1
        
        #message_publisher.xmlstream = 12
        #message_publisher.sendOneToOneXml(xml1)
        #nb_msg_save_in_DB += 1
        #message_publisher.publishXml(xml2)
        #nb_msg_save_in_DB += 1

        
        # on enleve la socket qui ne peut etre enlever via le reactor 
        #  (il n'est pas démarré)
        import os
        os.remove(sr)
        # on enleve le fichier de database
        os.remove(dbfilename)

    
        # récupération du nombre de message dans la table après les envoies
        cur.execute(requete)
        raw_ap = cur.fetchone()[0]
             
        cur.close()
        conn.close()
        
        # vérification que tous les messages ont été sauvegardés
        self.assertEqual(raw_av + nb_msg_save_in_DB, raw_ap)      
        
    def test_nodeToSocketDbStore(self):
        """ 
        test the storage of message in case of XMPP server non working 
        in the nodeToSocket module
        """

        nb_msg_save_in_DB = 0
        dbfilename = settings['VIGILO_MESSAGE_BACKUP_FILE']
        dbtable =  settings['VIGILO_MESSAGE_BACKUP_TABLE_FROMBUS']
        # on initialise la database
        store = DbRetry(dbfilename, dbtable)
        store.__del__()
        # connection à la database puis récupération du nombre d'enregistrement
        base = settings.get('VIGILO_MESSAGE_BACKUP_FILE',[])
        conn = sqlite3.connect(base)
        cur = conn.cursor()
        # récupération du nombre de message dans la table avant send
        requete = 'select count(*) from ' + dbtable
        cur.execute(requete)
        raw_av = cur.fetchone()[0]


        xmpp_client = client.XMPPClient(
                JID(settings['VIGILO_CONNECTOR_JID']),
                settings['VIGILO_CONNECTOR_PASS'],
                settings['VIGILO_CONNECTOR_XMPP_SERVER_HOST'])
        _service = JID(settings.get('VIGILO_CONNECTOR_XMPP_PUBSUB_SERVICE',
                                    None))
        sw = settings.get('VIGILO_SOCKETW', None)
        message_publisher = NodeToSocketForwarder(
                sw,
                dbfilename,
                dbtable)
        message_publisher.setHandlerParent(xmpp_client)



        xml = text2xml(
                "event|1165939739|serveur1.example." +
                "com|192.168.0.1|Load|CRITICAL|CRITICAL: load avg: " +
                "12 10 10")
        message_publisher.messageForward(xml.toXml().encode('utf8'))
        nb_msg_save_in_DB += 1

        
        #message_publisher.xmlstream = 12
        #message_publisher.sendOneToOneXml(xml1)
        #message_publisher.publishXml(xml2)

        
        # on enleve le fichier de database
        import os
        os.remove(dbfilename)

    
        # récupération du nombre de message dans la table après les envoies
        cur.execute(requete)
        raw_ap = cur.fetchone()[0]
             
        cur.close()
        conn.close()
        
        # vérification que les messages ont été sauvegardés
        self.assertEqual(raw_av + nb_msg_save_in_DB, raw_ap)      


    
if __name__ == "__main__": 
    unittest.main()
