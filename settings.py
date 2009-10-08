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
        'twisted': logging.DEBUG,
        'vigilo.pubsub': logging.DEBUG,
        'vigilo.connector': logging.DEBUG,
    }


VIGILO_CONNECTOR_XMPP_SERVER_HOST = 'vigilo-dev'
VIGILO_CONNECTOR_XMPP_PUBSUB_SERVICE = 'pubsub.localhost'
# Respect the ejabberd namespacing, for now. It will be too restrictive soon.
VIGILO_CONNECTOR_JID = 'connectorx@localhost'
VIGILO_CONNECTOR_PASS = 'connectorx'

# listen on this node (écoute de ce noeud)
VIGILO_CONNECTOR_TOPIC = ['/home/localhost/connectorx/BUS']
# create this node (créer ce noeud)
VIGILO_CONNECTOR_TOPIC_OWNER = ['/home/localhost/connectorx/BUS']
# publish on those node (publier sur ces noeuds)
VIGILO_CONNECTOR_TOPIC_PUBLISHER = { 
        'perf': '/home/localhost/connectorx/BUS',
        'state': '/home/localhost/connectorx/BUS',
        'event': '/home/localhost/connectorx/BUS',
        }

VIGILO_SOCKETW = '/var/lib/vigilo/connector/recv.sock'
VIGILO_SOCKETR = '/var/lib/vigilo/connector/send.sock'
VIGILO_MESSAGE_BACKUP_FILE = '/var/lib/vigilo/connector/backup'
#VIGILO_MESSAGE_BACKUP_FILE = ':memory:'
VIGILO_MESSAGE_BACKUP_TABLE_TOBUS = 'connector_tobus'
VIGILO_MESSAGE_BACKUP_TABLE_FROMBUS = 'connector_frombus'

