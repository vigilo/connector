# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2016 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import sys
import logging

from zope.interface import implements
from twisted.internet import reactor, defer
from twisted.internet.interfaces import IConsumer
from twisted.application import service

from vigilo.common.conf import settings
settings.load_file("./settings_tests.ini")

#from vigilo.common.logging import get_logger
#LOGGER = get_logger(__name__)


from vigilo.common.gettext import translate
_ = translate(__name__)

from vigilo.connector.client import VigiloClient
from vigilo.connector.handlers import BusHandler, QueueSubscriber, MessageHandler


class Tester(BusHandler):
    client = None
    def connectionInitialized(self, arg):
        print "initialized"
    def connectionLost(self, arg):
        print "lost"

class MsgLogger(MessageHandler):

    def processMessage(self, msg):
        print "RECV:", type(msg), msg, msg.__dict__
        #LOGGER.info("RECV2: %s", msg.content)

    def sendDummy(self):
        self.client.send("machin", "truc", "truc-machin")

client = VigiloClient(host="localhost", user="guest", password="guest", log_traffic=True)
client.addHandler(Tester())
msglogger = MsgLogger()
msglogger.setClient(client)
msglogger.subscribe("truc")
msglogger.sendDummy()


def stop():
    client.stopService()
    reactor.stop()
reactor.callLater(2, stop)
application = service.Application("essai")
client.setServiceParent(application)
