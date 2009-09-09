import logging
LOGGING_PLUGINS = ()
LOGGING_SETTINGS = { 'level': logging.DEBUG, }
LOGGING_LEVELS = {}
LOGGING_SYSLOG = False

VIGILO_CONNECTOR_DAEMONIZE = True
VIGILO_CONNECTOR_PIDFILE = '/var/lib/vigilo/connector/connector.pid'
VIGILO_CONNECTOR_XMPP_SERVER_HOST = 'localhost'
VIGILO_CONNECTOR_XMPP_PUBSUB_SERVICE = 'pubsub.localhost'
# Respect the ejabberd namespacing, for now. It will be too restrictive soon.
VIGILO_CONNECTOR_JID = 'connector@localhost'
VIGILO_CONNECTOR_PASS = 'connector'

VIGILO_CONNECTOR_TOPIC = '/home/localhost/connector/alerts'
VIGILO_SOCKETW = '/var/lib/vigilo/connector/recv.sock'
#VIGILO_SOCKETW = None
VIGILO_SOCKETR = '/var/lib/vigilo/connector/send.sock'
VIGILO_MESSAGE_BACKUP_FILE = '/tmp/backup'
VIGILO_MESSAGE_BACKUP_TABLE = 'connector'

