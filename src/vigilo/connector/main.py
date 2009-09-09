# vim: set fileencoding=utf-8 sw=4 ts=4 et :
""" Connector Pubsub client. """
from __future__ import absolute_import, with_statement


import os, sys
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
        from vigilo.pubsub import NodeOwner, Subscription
        from vigilo.common.conf import settings
        xmpp_client = client.XMPPClient(
                JID(settings['VIGILO_CONNECTOR_JID']),
                settings['VIGILO_CONNECTOR_PASS'],
                settings['VIGILO_CONNECTOR_XMPP_SERVER_HOST'])
        xmpp_client.logTraffic = True
        xmpp_client.setName('xmpp_client')

        node_owner = NodeOwner()
        node_owner.setHandlerParent(xmpp_client)

        connector_sub = Subscription(
                JID(settings['VIGILO_CONNECTOR_XMPP_PUBSUB_SERVICE']),
                settings['VIGILO_CONNECTOR_TOPIC'],
                node_owner)

        sw = settings.get('VIGILO_SOCKETW', None)
        if sw is not None:
            message_consumer = NodeToSocketForwarder(
                    sw, connector_sub,
                    settings['VIGILO_MESSAGE_BACKUP_FILE'],
                    settings['VIGILO_MESSAGE_BACKUP_TABLE_FROMBUS'])
            message_consumer.setHandlerParent(xmpp_client)

        sr = settings.get('VIGILO_SOCKETR', None)
        if sr is not None:
            message_publisher = SocketToNodeForwarder(
                    sr, connector_sub,
                    settings['VIGILO_MESSAGE_BACKUP_FILE'],
                     settings['VIGILO_MESSAGE_BACKUP_TABLE_TOBUS'])
            message_publisher.setHandlerParent(xmpp_client)

        root_service = service.MultiService()
        xmpp_client.setServiceParent(root_service)
        return root_service

def daemonize():
    """ Called to daemonize a program """
   
    from vigilo.common.conf import settings
    import daemon
    import daemon.pidlockfile
    stalepid = False
    alreadyRunning = False

    if settings['VIGILO_CONNECTOR_DAEMONIZE']:
        pidfile = settings['VIGILO_CONNECTOR_PIDFILE']
        if pidfile is not None:
            # We must remove a stale pidfile by hand :/
            if os.path.exists(pidfile):
                with open(pidfile) as oldpidfile:
                    pid = int(oldpidfile.read())
                try:
                    os.kill(pid, 0) # Just checks it exists
                    # This has false positives, no matter.
                except OSError: # Stale pid
                    # delaying message after daemonization
                    stalepid = True
                    os.unlink(pidfile)
                else:
                    # delaying message after daemonization
                    alreadyRunning = True
            pidfile = daemon.pidlockfile.PIDLockFile(pidfile)
        else:
            pidfile = None

        if alreadyRunning :
            from vigilo.common.logging import get_logger
            LOGGER = get_logger(__name__)
            LOGGER.warning(_('Already running, pid is %(pid)d.') % \
                           {'pid' : pid})
            return(1)

        with daemon.DaemonContext(detach_process=True, pidfile=pidfile):
            if stalepid:
                from vigilo.common.logging import get_logger
                LOGGER = get_logger(__name__)
                LOGGER.info(_('Removing stale pid file at %(pidfile)s ' + \
                            '(%(pid)d).') % 
                            {'pidfile': pidfile, 'pid': pid})
            
    # never seen
    print _("daemon mode ON (you should not see this message " + \
            "except in debug mode")
    return main()

def main():

    """ main function designed to launch the program """
    application = service.Application('Twisted PubSub component')
    conn_service = ConnectorServiceMaker().makeService()
    conn_service.setServiceParent(application)
    app.startApplication(application, False)
    reactor.run()

if __name__ == '__main__':
    sys.exit(daemonize())
