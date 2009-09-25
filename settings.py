# vim: set fileencoding=utf-8 sw=4 ts=4 et :
import logging
LOGGING_PLUGINS = (
        'vigilo.pubsub.logging',       
        )
LOGGING_SETTINGS = { 'level': logging.DEBUG, }
LOGGING_LEVELS = {}
LOGGING_SYSLOG = True
LOG_TRAFFIC = True


LOGGING_SETTINGS = {
        # 5 is the 'SUBDEBUG' level.
        'level': logging.DEBUG,
        'format': '%(levelname)s::%(name)s::%(message)s',
        }
LOGGING_LEVELS = {
        'multiprocessing': logging.DEBUG,
        'twisted': logging.DEBUG,
        'vigilo.pubsub': logging.DEBUG,
        'vigilo.connector': logging.INFO,
    }


VIGILO_CONNECTOR_DAEMONIZE = True
VIGILO_CONNECTOR_DAEMONIZE = False
VIGILO_CONNECTOR_PIDFILE = '/var/lib/vigilo/connector/connector.pid'
VIGILO_CONNECTOR_XMPP_SERVER_HOST = 'tburguie3'
VIGILO_CONNECTOR_XMPP_PUBSUB_SERVICE = 'pubsub.tburguie3'
# Respect the ejabberd namespacing, for now. It will be too restrictive soon.
VIGILO_CONNECTOR_JID = 'connectorx@tburguie3'
VIGILO_CONNECTOR_PASS = 'connectorx'

# listen on this node (écoute de ce noeud)
VIGILO_CONNECTOR_TOPIC = ['/home/tburguie3/connectorx/BUS']
# create this node (créer ce noeud)
VIGILO_CONNECTOR_TOPIC_OWNER = ['/home/tburguie3/connectorx/BUS']
# publish on those node (publier sur ces noeuds)
VIGILO_CONNECTOR_TOPIC_PUBLISHER = { 
        'perf': '/home/tburguie3/connectorx/BUS',
        'state': '/home/tburguie3/connectorx/BUS',
        'event': '/home/tburguie3/connectorx/BUS',
        }

VIGILO_SOCKETW = '/var/lib/vigilo/connector/recv.sock'
VIGILO_SOCKETR = '/var/lib/vigilo/connector/send.sock'
VIGILO_MESSAGE_BACKUP_FILE = '/var/lib/vigilo/connector/backup'
VIGILO_MESSAGE_BACKUP_TABLE_TOBUS = 'connector_tobus'
VIGILO_MESSAGE_BACKUP_TABLE_FROMBUS = 'connector_frombus'

