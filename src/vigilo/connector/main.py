# vim: set fileencoding=utf-8 sw=4 ts=4 et :
""" Connector Pubsub client. """
from __future__ import absolute_import


#import random



from twisted.application import app, service
from twisted.internet import reactor
from twisted.words.protocols.jabber.jid import JID
from vigilo.common.conf import settings

from wokkel import client

from vigilo.common.logging import get_logger

from vigilo.connector.nodetosocketfw import NodeToSocketForwarder
from vigilo.connector.sockettonodefw import SocketToNodeForwarder
from vigilo.pubsub import NodeOwner, Subscription

LOGGER = get_logger(__name__)

class ConnectorServiceMaker(object):
    """
    Creates a service that wraps everything the connector needs.
    """

    #implements(service.IServiceMaker, IPlugin)

    def makeService(self):
        """ the service that wraps everything the connector needs. """ 
        xmpp_client = client.XMPPClient(
                JID(settings['VIGILO_CONNECTOR_JID']),
                settings['VIGILO_CONNECTOR_PASS'],
                settings['XMPP_SERVER_HOST'])
        xmpp_client.logTraffic = True
        xmpp_client.setName('xmpp_client')

        node_owner = NodeOwner()
        node_owner.setHandlerParent(xmpp_client)

        connector_sub = Subscription(
                JID(settings['XMPP_PUBSUB_SERVICE']),
                settings['VIGILO_CONNECTOR_TOPIC'],
                node_owner)

        message_consumer = NodeToSocketForwarder(
                connector_sub, settings['VIGILO_SOCKETW'],
                settings['VIGILO_MESSAGE_BACKUP_FILE'])
        message_consumer.setHandlerParent(xmpp_client)

        message_publisher = SocketToNodeForwarder(
                settings['VIGILO_SOCKETR'], connector_sub)
        message_publisher.setHandlerParent(xmpp_client)

        root_service = service.MultiService()
        xmpp_client.setServiceParent(root_service)
        return root_service

def main():
    """ main function designed to launch the program """
    application = service.Application('Twisted PubSub component')
    conn_service = ConnectorServiceMaker().makeService()
    conn_service.setServiceParent(application)
    app.startApplication(application, False)
    reactor.run()
