# -*- coding: utf-8 -*-
"""
Connector for the Vigilo Project based on
UNIX socket,
Bus message using pubsub/XMPP
"""
import signal
import SocketServer

from twisted.internet import reactor
#from twisted.words.xish import domish
#from twisted.words.protocols.jabber import jid, xmlstream
from twisted.words.protocols.jabber import jid
import time, threading, socket, os
from wokkel import client, pubsub, xmppim
from twisted.application import service
import ConfigParser, logging, syslog


LEVELS = {'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL}




class configuration(object):
    """
    Use to configure connection variable
    such as name, password, server to connect ...
    """
    def __init__(self):
        config = ConfigParser.RawConfigParser()
        config.read('config.cfg')
       # syslog.syslog('Hello from Python!')

        #logging.debug('This is a debug message')
        #logging.info('This is an info message')
        #logging.warning('This is a warning message')
        #logging.error('This is an error message')
        #logging.critical('This is a critical error message')
        
        # the variables we want to define
        self.userfrom = config.get('Default', 'userfrom')

        self.pwdfrom = self.userfrom
        self.host = config.get('Default', 'host')
        self.adrfrom = self.userfrom + '@' + self.host
        #self.adrto = 'test2@vigilo-dev.local'
        self.adrto = config.get('Default', 'adrto')
        self.mynodeidentifier = config.get('Default', 'mynodeidentifier')
        self.mynodeidentifier1 = config.get('Default', 'mynodeidentifier1')
        self.mysocket = '/tmp/' + self.userfrom



class XMPPClientVigilo(client.XMPPClient):
    """ Service that initiates an XMPP client connection """

    def __init__(self, jabberid, password, host=None, port=5222):

        client.XMPPClient.__init__(self, jabberid, password, host, port)
        self.auth_ready = False
        self.subscribe_ready = False
        self.service = None
        self.nodeIdentifier = None
        self.pubsubHandler = None
        self._ItemQueue = []

    def _authd(self, xs):
        """ 
        Called when the stream has been initialized.
        
        Send out cached stanzas and call each handler's
        C{connectionInitialized} method.
        """
        client.XMPPClient._authd(self, xs)
        self.auth_ready = True
        # add a callback for the messages
        xs.addObserver('/message', self.gotMessage)

    def gotMessage(self, msg):
        """ 
        Called when a message is received
        """
        # sorry for the __str__(), makes unicode happy
        #print "from: %s" % msg["from"]
        #print msg.toXml()
        items = self.returnListItem(msg)
        for it in items:
            print it

    def returnListItem(self, event_msg):
        """
        Return a List of Item from an XMPP event message
        """
        ev = [ e for e in event_msg.elements() if e.name == "event" ]
        for e in ev:
            its = [ its for its in e.elements() if its.name == "items" ]
            for it1 in its:
                it = [ it for it in it1.elements() if it.name == "item" ]
                return it


    def queueItem(self, items, sender=None):
        """ 
        Called when an Item (in a publication node) need to be Queued
        """
        self._packetQueue.append([items, sender])

    def unQueueItem(self):
        """ 
        Called when an Item (in a publication node) need to be Queued
        """
        for p in self._packetQueue:
            items = p[0]
            sender = p[1]
            self.sendItem(items, sender)
        self._packetQueue = []

    #def send(self, object):
    #    """ 
    #    Called when a message need to be sent
    #    """
    #    client.XMPPClient.send(self, object)

    def sendItem(self, items=None, sender=None):
        """ 
        Called when an Item (in a publication node) need to be sent
        """

        def cb_publish (o):
            """
            Call Back to handle deferred object 
            """
            print 'sendItem OK'

        def eb_publish (o):
            """
            Error Back to handle deferred object 
            """
            print 'KO'
        
        while not self.auth_ready:
            time.sleep(1)

        d = self.pubsubHandler.publish(self.service, self.nodeIdentifier, items,
                sender)
        d.addCallback(cb_publish)
        d.addErrback(eb_publish)


def texttoxml(text):
    """ 
    Called to return the XML from text message read from socket
    @param text: The text to convert
    @type  text: C{str}
    """
    return text

def mypubsubNodecreator(myXMPPClient, conf):
    """ 
    Called to create a pubsub Node from a XMPPClientVigilo
    And to listen from a socket to publish
    """
    print 'on commence reellement la création/subscription du noeud'
    jidto = jid.JID(conf.adrto)
    pubsubHandler = pubsub.PubSubClient()
    pubsubHandler.setHandlerParent(myXMPPClient)
    def cb_create(content):
        """
        Call Back to handle deferred object 
        """
        #print content
        print 'on a fini la création du noeud'
        d2 = pubsubHandler.subscribe(jidto, nodeIdentifier=conf.mynodeidentifier,
                subscriber=jid.JID(ADRFROM + "/localhost"))
        d2.addCallback(cb_subscribe)
        d2.addErrback(eb_subscribe)

    def eb_create(error):
        """
        Error Back to handle deferred object 
        """
        #print error
        print 'il y a eu une erreur lors de la création du noeud'
        reactor.stop() # pylint: disable-msg=E1101

    def cb_subscribe(content):
        """
        Call Back to handle deferred object 
        """
        #print content
        print 'on a fini la subscription au noeud'
        myXMPPClient.ready = True
        myXMPPClient.nodeIdentifier = conf.mynodeidentifier
        myXMPPClient.service = jidto
        myXMPPClient.pubsubHandler = pubsubHandler
        myXMPPClient.nodeIdentifier = conf.mynodeidentifier

        #socketServer(myXMPPClient, conf)
        #reactor.callFromThread(socketServer, myXMPPClient, conf)
        #reactor.callInThread(socketServer, myXMPPClient, conf)
        print 'on a appelle le thread de creation de la socket'

    def eb_subscribe(error):
        """
        Error Back to handle deferred object 
        """
        #print error
        print 'il y a eu une erreur lors de la subscription au noeud'
        reactor.stop() # pylint: disable-msg=E1101

    # tant que l authentification n'est pas OK on ne commence rien
    while not myXMPPClient.auth_ready:
        time.sleep(1)
    #d1 = pubsubHandler.createNode(jidto, nodeIdentifier=conf.mynodeidentifier)
    #d1 = pubsubHandler.deleteNode(jidto, nodeIdentifier=conf.mynodeidentifier)
    #d1.addCallback(cb_create)
    #d1.addErrback(eb_create)
    #d2 = pubsubHandler.subscribe(jidto, nodeIdentifier=conf.mynodeidentifier,
    #                              subscriber=jid.JID(ADRFROM + "/localhost"))
    #d2.addCallback(cb_subscribe)
    #d2.addErrback(eb_subscribe)

    # gros hack de barbare pour faire croire que l'on a souscrit
    myXMPPClient.ready = True
    myXMPPClient.nodeIdentifier = conf.mynodeidentifier
    myXMPPClient.service = jidto
    myXMPPClient.pubsubHandler = pubsubHandler
    myXMPPClient.nodeIdentifier = conf.mynodeidentifier
    #socketServer(myXMPPClient, conf)
    socket_server = VigiloSocketServer(conf.mysocket, SocketReaderClient)
    socket_server.xmpp_client = myXMPPClient
    socket_server.conf = conf
    socket_server.serve_forever()


class VigiloSocketServer(SocketServer.ThreadingMixIn, SocketServer.UnixStreamServer):
    pass

def socketServer(myclientXMPP, conf):
    """
    Function to serve from a UNIX socket to the XMPP BUS 
    """
    try:
        while 1:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                os.remove(conf.mysocket)
            except OSError:
                pass
            print conf.mysocket
            s.bind(conf.mysocket)
            s.listen(5)
            while 1:
                conn, addr = s.accept()
                print 'on a eu une connexion'
                # the socket is handled in a separated thread
                src = SocketReaderClient(conn, addr, myclientXMPP)
                src.start()
    except KeyboardInterrupt:
        print "KeyboardInterrupt"

class SocketReaderClient(SocketServer.BaseRequestHandler):
    """ Handle socket data and then send a message """

    def handle(self):
        """ Read from a socket and then send a message """
        self.data = self.rfile.readline().strip()
        sender = jid.JID(self.server.conf.adrfrom)
        item = pubsub.Item(payload=texttoxml(self.data))
        reactor.callFromThread(# pylint: disable-msg=E1101
                               self.server.xmpp_client.sendItem, 
                               [item], sender)


def on_exit(*args):
    print "on exit"
    reactor.stop()
    print "exited"

def main():
    conf = configuration()
    PWDFROM = conf.pwdfrom
    HOST = conf.host
    ADRFROM = conf.adrfrom
    ADRTO = conf.adrto
    MYNODEIDENTIFIER = conf.mynodeidentifier
    MYNODEIDENTIFIER1 = conf.mynodeidentifier1
    MYSOCKET = conf.mysocket

    JIDFROM = jid.JID(ADRFROM + "/localhost")
    XMPPCLIENT = XMPPClientVigilo(JIDFROM, PWDFROM, host=HOST)
    APPLICATION = service.Application('XMPP client')
    XMPPCLIENT.logTraffic = True
    XMPPCLIENT.setServiceParent(APPLICATION)
    PRESENCE = xmppim.PresenceClientProtocol()
    PRESENCE.setHandlerParent(XMPPCLIENT)
    PRESENCE.available()
    XMPPCLIENT.startService()
    signal.signal(signal.SIGINT, on_exit)
    reactor.callInThread(mypubsubNodecreator, XMPPCLIENT, conf)#pylint: disable-msg=E1101
    reactor.run() # pylint: disable-msg=E1101


if __name__ == '__main__':
    main()
