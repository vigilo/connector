# vim: set fileencoding=utf-8 sw=4 ts=4 et :
""" Connector Pubsub client. """
from __future__ import absolute_import, with_statement

import os, sys
from twisted.application import app, service
from twisted.internet import reactor
from twisted.words.protocols.jabber.jid import JID
from vigilo.pubsub.checknode import VerificationNode

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
        from vigilo.common.conf import settings
        xmpp_client = client.XMPPClient(
                JID(settings['VIGILO_CONNECTOR_JID']),
                settings['VIGILO_CONNECTOR_PASS'],
                settings['VIGILO_CONNECTOR_XMPP_SERVER_HOST'])
        xmpp_client.logTraffic = True
        xmpp_client.setName('xmpp_client')

        node_owner = NodeOwner()
        node_owner.setHandlerParent(xmpp_client)

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


def daemonize(pidfile=None):
    """
    Call this method to daemonize a program.
    
    @param pidfile: The name of the file where the daemon's PID will be stored.
    @type pidfile: C{str}
    """

    import daemon
    import daemon.pidlockfile

    stalepid = False
    alreadyRunning = False

    if pidfile is not None:
        pidfile = daemon.pidlockfile.PIDLockFile(pidfile)

        if pidfile.is_locked():
            pid = pidfile.read_pid()
            try:
                os.kill(pid, 0) # Just check if it exists
            except OSError: # Stale PID
                # Display a message before daemonization.
                stalepid = True
                pidfile.break_lock()
            else:
                # Display a message and don't daemonize.
                alreadyRunning = True

    if alreadyRunning :
        from vigilo.common.logging import get_logger
        LOGGER = get_logger(__name__)
        LOGGER.warning(_('Already running, pid is %(pid)d.') % {'pid' : pid})
        sys.exit(1)

    if stalepid:
        from vigilo.common.logging import get_logger
        LOGGER = get_logger(__name__)
        LOGGER.info(_('Removing stale pid file at %(pidfile)s (%(pid)d).') % 
                {'pidfile': pidfile, 'pid': pid})

    return daemon.DaemonContext(detach_process=True, pidfile=pidfile)


def main():
    """ main function designed to launch the program """
    from vigilo.common.conf import settings
    if settings.get('VIGILO_CONNECTOR_DAEMONIZE', False) == True:
        with daemonize(settings.get('VIGILO_CONNECTOR_PIDFILE', None)):
            pass

    application = service.Application('Twisted PubSub component')
    conn_service = ConnectorServiceMaker().makeService()
    conn_service.setServiceParent(application)
    app.startApplication(application, False)
    reactor.run()


if __name__ == '__main__':
    result = main()
    sys.exit(result)

