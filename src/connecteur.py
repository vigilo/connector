# -*- coding: utf-8 -*-
"""
Connector for the Vigilo Project based on
UNIX socket,
Bus message using pubsub/XMPP
"""
import signal
import SocketServer
import time
import os
import ConfigParser
import logging
import syslog
import base64
import socket
#import pdb
#from twisted.internet.defer import inlineCallbacks, returnValue

from twisted.internet import reactor
from twisted.words.protocols.jabber import jid
from twisted.application import service
from wokkel import client, pubsub, xmppim
from wokkel.generic import parseXml

LEVELS = {'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL}

def logguage(text, facility=None):
    """  Call to log evenements to the syslog """
    #syslog.syslog(LEVELS['info'], text)
    print (text)

def encode(data):
    """ Encode data using Base64. """
    return base64.b64encode(data)

def decode(data):
    """ Decode data using Base64 """
    return base64.b64decode(data)

def text2xml(text):
    """ 
    Called to return the XML from text message read from socket
    @param text: The text to convert
    @type  text: C{str}
    """
    i = text.strip().split('|')
    if i:
        if i[0] == "event":
            try:
                return parseXml(event2xml(i)).toXml()
            except AttributeError:
                logguage("type de message inconnue")
                return ""
        elif i[0] == "perf":
            try:
                return parseXml(perf2xml(i)).toXml()
            except AttributeError:
                logguage("type de message inconnue")
                return ""
        else:
            logguage("type de message inconnue")
            return ""


def event2xml(event_list):
    """ Called to return the XML from event message list """
    
    # to avoid error from message length
    if len(event_list) != 7:
        return ""

    message = """<event xmlns="http://www.projet-vigilo.org/messages">
    <timestamp>%(timestamp)s</timestamp>
    <host>%(host)s</host>
    <ip>%(ip)s</ip>
    <service>%(service)s</service>
    <state>%(state)s</state>
    <message>%(message)s</message>
</event>
"""

    dico = { "timestamp": event_list[1], # MUST
             "host": event_list[2],      # MUST
             "ip": event_list[3],        # MAY
             "service": event_list[4],   # MAY
             "state": event_list[5],     # MUST
             "message": event_list[6]    # SHOULD
           }

    return message % dico

def perf2xml(perf_list):
    """ Called to return the XML from perf message list """

    # to avoid error from message length
    if len(perf_list) != 5:
        return ""

    message = """<perf xmlns="http://www.projet-vigilo.org/messages">
    <timestamp>%(timestamp)s</timestamp>
    <host>%(host)s</host>
    <datasource>%(datasource)s</datasource>
    <value>%(value)s</value>
</perf>
"""


    dico = { "timestamp": perf_list[1],  # MUST
             "host": perf_list[2],       # MUST
             "datasource": perf_list[3], # MUST
             "value": perf_list[4],      # MUST
            }

    return message % dico

class Configuration(object):
    """
    Use to configure connection variable
    such as name, password, server to connect ...
    """
    def __init__(self):
        config = ConfigParser.RawConfigParser()
        config.read('config.cfg')
        # the variables we want to define
        self.userfrom = config.get('Default', 'userfrom')
        self.password = self.userfrom
        self.host = config.get('Default', 'host')
        self.adrfrom = self.userfrom + '@' + self.host
        self.adrto = config.get('Default', 'adrto')
        self.nodeident = config.get('Default', 'nodeident')
        self.nodeident1 = config.get('Default', 'nodeident1')
        self.socketR = '/tmp/' + self.userfrom + "R"
        self.socketW = '/tmp/' + self.userfrom + "W"
        self.jidfrom = jid.JID(self.adrfrom + "/localhost")
        self.jidto = jid.JID(self.adrto)
        if config.get('Default', 'createnode') == "True" :
            self.createnode = True
        else:
            self.createnode = False



class XMPPClientVigilo(client.XMPPClient):
    """ Service that initiates an XMPP client connection """

    def __init__(self, cf, port=5222):

        self.conf = cf
        client.XMPPClient.__init__(self, conf.jidfrom, conf.password, conf.host, port)
        self.auth_ready = False
        if self.conf.createnode:
            self.node_ready = False
        else:
            self.node_ready = True
        self.subscribe_ready = False
        self.service = None
        self.pubsubHandler = None
        self._ItemQueue = []
        self.socket_server = None
        self.xs = None

    def _authd(self, xs):
        """ 
        Called when the stream has been initialized.
        
        Send out cached stanzas and call each handler's
        C{connectionInitialized} method.
        """
        client.XMPPClient._authd(self, xs)
        self.auth_ready = True
        self.xs = xs
        ## add a callback for the messages
        #xs.addObserver('/message', self.gotMessage)

    def messageObserver(self):
        """ Register a function to call each time a message arrive from the XMPP BUS """
        
        while not self.subscribe_ready:
            #logguage("messageObserver: waiting authentification to be done")
            time.sleep(4)

        # add a callback for the messages
        self.xs.addObserver('/message', self.fromBUS)



    def returnListItem(self, event_msg):
        """ Return a List of Item from an XMPP event message """
        it = []
        ev = [ e for e in event_msg.elements() if e.name == "event" ]
        for e in ev:
            its = [ its for its in e.elements() if its.name == "items" ]
            for it1 in its:
                it = [ it for it in it1.elements() if it.name == "item" ]
        return it


    def queueItem(self, items, sender=None):
        """ Called when an Item (in a publication node) need to be Queued """
        self._packetQueue.append([items, sender])

    def unQueueItem(self):
        """ Called when an Item (in a publication node) need to be UnQueued """
        for p in self._packetQueue:
            print "on depile %s, %s" % (p[1], p[0])
            items = p[0]
            sender = p[1]
            self.sendItem(items, sender)
        self._packetQueue = []

    def sendItem(self, items=None, sender=None):
        """ Called when an Item (in a publication node) need to be sent """

        def cb_publish (*args):
            """ Call Back to handle deferred object """
            pass

        def eb_publish (*args):
            """ Error Back to handle deferred object """
            logguage(" send Item KO")
            pass

        while not self.auth_ready:
            logguage("auth need to be done")
            time.sleep(4)

        #print "avant envoie"
        #pprint([ i.toXml() for i in items])
        if self.pubsubHandler:
            d = self.pubsubHandler.publish(self.service, self.conf.nodeident, items,
                    sender)
            d.addCallback(cb_publish)
            d.addErrback(eb_publish)
    
    def pubsubNodecreator(self, nodeIdentifier=None):
        """ 
        Called to create a pubsub Node from a XMPPClientVigilo
        And to listen from a socket to publish
        """
        if not nodeIdentifier:
            nodeIdentifier = self.conf.nodeident
        logguage("on commence reellement la création/subscription du noeud")

        def cb_create(content):
            """ Call Back to handle deferred object """
            self.node_ready = True
            logguage("on a fini la création du noeud")

        def eb_create(error):
            """ Error Back to handle deferred object """
            #print 'il y a eu une erreur lors de la création du noeud'
            #print error
            #print error.type
            ##print error.toXml()
            #print error.value
            #print error.type
            #print type(error.value)
            #print error.value.condition
            #print error.value.getElement()
            if error.value.condition == 'conflict':
                # We tried to create a node that exists.
                # This is the desired outcome.
                logguage("conflict error = Node already exist")
                self.node_ready = True
            elif error.value.condition == 'forbidden':
                # ejabberd's way of saying "create parent first"
                logguage("forbidden error = Create the parents Nodes first")
                # TODO create the parents
                pass
            else:
                raise error

        # tant que l authentification n'est pas OK on ne commence rien
        while not self.auth_ready:
            #logguage("pubsubNodecreator: waiting for authentification to be done")
            time.sleep(4)


        # gros hack pour accelerer le temps des tests
        #self.node_ready = True
        d1 = self.pubsubHandler.createNode(conf.jidto, nodeIdentifier=nodeIdentifier)
        d1.addErrback(eb_create)
        d1.addCallback(cb_create)
    
    def pubsubNodesubscriber(self):
        """ 
        Called to subscribe to a pubsub Node
        """
        logguage('on commence reellement la subscription au noeud')
        pubsubHandler = pubsub.PubSubClient()
        pubsubHandler.setHandlerParent(self)
        self.pubsubHandler = pubsubHandler
        if self.conf.createnode:
            self.pubsubNodecreator()
        
        # tant que l authentification n'est pas OK on ne commence rien
        while not self.node_ready:
            logguage("pubsubNodesubscriber: waiting for Node creation to be done")
            time.sleep(4)

        def cb_subscribe(content):
            """ Call Back to handle deferred object """
            logguage("on a fini la subscription au noeud")
            self.subscribe_ready = True
            self.service = conf.jidto
            presence = xmppim.PresenceClientProtocol()
            presence.setHandlerParent(self)
            presence.available()

        def eb_subscribe(error):
            """ Error Back to handle deferred object """
            logguage(error.__str__())
            logguage("il y a eu une erreur lors de la subscription au noeud")
            on_exit(1, 2)

        
        # gros hack pour accelerer le temps des tests
        #self.subscribe_ready = True
        #self.service = conf.jidto
        #self.pubsubHandler = pubsubHandler
        d2 = self.pubsubHandler.subscribe(conf.jidto, nodeIdentifier=conf.nodeident,
                                      subscriber=conf.jidfrom)
        d2.addErrback(eb_subscribe)
        d2.addCallback(cb_subscribe)


    def toBUS(self):
        """ Called when a message need to be sent to the message BUS """
        # Delete the socket file if it already exists
        if os.access(self.conf.socketR, 0):
            logguage("the socket was previously existing, we had to remove it before creating a new one")
            os.remove(self.conf.socketR)
        
        self.socket_server = VigiloSocketServer(self.conf.socketR,
                SocketReaderClient)
        self.socket_server.xmpp_client = self
        self.socket_server.serve_forever()
        
    def fromBUS(self, msg):
        """ Called when a message is received """
        items = self.returnListItem(msg)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.conf.socketW)
        if items:
            for it in items:
                #print "pub/sub item:"
                if it:
                    #print decode(it.__str__())
                    #print it.__str__()
                    #print [ i.toXml() for i in it.elements() ][0]
                    #s.send([ i.toXml() for i in it.elements() ][0])
                    s.send(decode(it.__str__()) + "\n\n")
                    #print it
        else:
            print "Not pub/sub message:"
            print msg.toXml()
            #s.send(msg.toXml())
        s.close()


class VigiloSocketServer(SocketServer.ThreadingMixIn, 
                         SocketServer.UnixStreamServer):
    """ Handle socket connexion and pass the treatment to an handler """
    pass


class SocketReaderClient(SocketServer.StreamRequestHandler):
    """ Handle socket data and then send a message """

    def handle(self):
        """ Read from a socket and then send a message """
        data = self.rfile.read()
        if data:
            sender = conf.jidfrom
            item = pubsub.Item(payload=encode(text2xml(data)))
            reactor.callFromThread(# pylint: disable-msg=E1101
                                   self.server.xmpp_client.sendItem, 
                                   [item], sender)


#def on_exit(*args):
def on_exit(signum, frame):
    """ Force the program to exit when a CTRL-C is received """
    logguage("exit")
    XMPPCLIENT.unQueueItem()
    if XMPPCLIENT.socket_server:
        XMPPCLIENT.socket_server.server_close()
        # not available before python 2.6 
        #XMPPCLIENT.socket_server.shutdown()
    reactor.stop()#pylint: disable-msg=E1101
    logguage("exited")
    # TODO see if it's possible to stop the socket_server an other way 
    # (less brutaly...)
    # removal of the socket file 
    if os.access(conf.socketR, 0):
        os.remove(conf.socketR)
    os._exit(0)

def main():
    """ the main program """
    global XMPPCLIENT
    global conf
    conf = Configuration()

    XMPPCLIENT = XMPPClientVigilo(conf)
    #application = service.Application('XMPP client')
    #XMPPCLIENT.logTraffic = True
    #XMPPCLIENT.setServiceParent(application)
    XMPPCLIENT.startService()
    signal.signal(signal.SIGINT, on_exit)

    reactor.callInThread(XMPPCLIENT.pubsubNodesubscriber) #pylint: disable-msg=E1101
    # the messageObserver will use the fromBUS when a message arrive 
    reactor.callInThread(XMPPCLIENT.messageObserver) #pylint: disable-msg=E1101
    reactor.callInThread(XMPPCLIENT.toBUS) #pylint: disable-msg=E1101
    reactor.run() # pylint: disable-msg=E1101


if __name__ == '__main__':
    main()
