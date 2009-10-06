# vim: set fileencoding=utf-8 sw=4 ts=4 et :
""" Connector Pubsub client. """
from __future__ import absolute_import, with_statement

from twisted.application import app, service
from twisted.internet import reactor
from twisted.words.protocols.jabber.jid import JID


from wokkel import client
from vigilo.common.gettext import translate
_ = translate(__name__)

class ConnectorServiceMaker(object):
    """
    Creates a service that wraps everything the connector needs.
    """

    #implements(service.IServiceMaker, IPlugin)

    def makeService(self):
        """ the service that wraps everything the connector needs. """ 
        from vigilo.connector.nodetosocketfw import NodeToSocketForwarder
        from vigilo.connector.sockettonodefw import SocketToNodeForwarder
        from vigilo.pubsub import NodeOwner 
        from vigilo.pubsub.checknode import VerificationNode
        from vigilo.common.conf import settings
        xmpp_client = client.XMPPClient(
                JID(settings['VIGILO_CONNECTOR_JID']),
                settings['VIGILO_CONNECTOR_PASS'],
                settings['VIGILO_CONNECTOR_XMPP_SERVER_HOST'])
        xmpp_client.logTraffic = True
        xmpp_client.setName('xmpp_client')

        list_nodeOwner = settings.get('VIGILO_CONNECTOR_TOPIC_OWNER', [])
        list_nodeSubscriber = settings.get('VIGILO_CONNECTOR_TOPIC', [])
        verifyNode = VerificationNode(list_nodeOwner, list_nodeSubscriber, 
                                      doThings=True)
        verifyNode.setHandlerParent(xmpp_client)
        nodetopublish = settings.get('VIGILO_CONNECTOR_TOPIC_PUBLISHER', None)
        _service = JID(settings.get('VIGILO_CONNECTOR_XMPP_PUBSUB_SERVICE',
                                    None))

        sw = settings.get('VIGILO_SOCKETW', None)
        if sw is not None:
            message_consumer = NodeToSocketForwarder(
                    sw,
                    settings['VIGILO_MESSAGE_BACKUP_FILE'],
                    settings['VIGILO_MESSAGE_BACKUP_TABLE_FROMBUS'])
            message_consumer.setHandlerParent(xmpp_client)

        sr = settings.get('VIGILO_SOCKETR', None)
        if sr is not None:
            message_publisher = SocketToNodeForwarder(
                    sr,
                    settings['VIGILO_MESSAGE_BACKUP_FILE'],
                    settings['VIGILO_MESSAGE_BACKUP_TABLE_TOBUS'],
                    nodetopublish,
                    _service)
            message_publisher.setHandlerParent(xmpp_client)

        root_service = service.MultiService()
        xmpp_client.setServiceParent(root_service)
        return root_service

def do_main_programm():
    """ main function designed to launch the program """
    application = service.Application('Twisted PubSub component')
    conn_service = ConnectorServiceMaker().makeService()
    conn_service.setServiceParent(application)
    app.startApplication(application, False)
    reactor.run()

def main():
    """ main function designed to launch the program """

    from vigilo.common.daemonize import daemonize
    context = daemonize()
    with context:
        do_main_programm()


if __name__ == '__main__':
    main()

