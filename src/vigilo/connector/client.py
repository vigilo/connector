# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import os

try:
    import json
except ImportError:
    import simplejson as json

from zope.interface import implements

from twisted.internet import reactor, defer, error, tcp, interfaces
from twisted.application import service
from twisted.python import log, failure

from txamqp.content import Content
from txamqp.queue import Closed

from vigilo.common.gettext import translate, l_
_ = translate(__name__)

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

from vigilo.common.lock import grab_lock # après get_logger

from vigilo.connector.amqp import AmqpFactory, PERSISTENT
from vigilo.connector.interfaces import InterfaceNotProvided
from vigilo.connector.interfaces import IBusHandler, IBusProducer


def split_host_port(hostdef):
    """
    Découpe une définition hostname:port en couple (hostname, port)
    @todo: Support IPv6
    """
    hostdef = hostdef.strip()
    if ":" in hostdef:
        host, port = hostdef.split(":")
        port = int(port)
    else:
        host = hostdef
        port = 5672
    return host, port



class VigiloClient(service.Service):
    """Client du bus Vigilo"""


    def __init__(self, host, user, password, use_ssl=False,
                 max_delay=60, log_traffic=False):
        """
        Initialise le client.
        @param host: le serveur AMQP
        @type  host: C{str}
        @param user: Identifiant du client.
        @type  user: C{str}
        @param password: Mot de passe associé au compte.
        @type  password: C{str}
        @param use_ssl: Indique si la connexion doit être chiffrée ou non.
        @type  use_ssl: C{bool}
        @param max_delay: le délai maximum entre chaque tentative de
            reconnexion.
        @type  max_delay: C{int}
        """
        self.host = host
        self.user = user
        self.password = password
        self.use_ssl = use_ssl
        self.log_traffic = log_traffic

        self.handlers = []
        self.deferred = defer.Deferred()
        self.queues = []
        self._packetQueue = [] # List of messages waiting to be sent.
        self.channel = None

        self.factory = AmqpFactory(parent=self, user=self.user,
                password=self.password, logTraffic=log_traffic)
        self.factory.maxDelay = max_delay


    def startService(self):
        service.Service.startService(self)
        self._connection = self._getConnection()
        # Notify all child services
        dl = []
        for h in self.handlers:
            if hasattr(h, "startService"):
                dl.append(defer.maybeDeferred(h.startService))
        return defer.gatherResults(dl)


    def stopService(self):
        service.Service.stopService(self)
        # Notify all child services
        dl = []
        for h in self.handlers:
            if hasattr(h, "stopService"):
                dl.append(defer.maybeDeferred(h.stopService))
        # On se déconnecte nous-même
        dl.append(self.factory.stop())
        return defer.gatherResults(dl)


    def _getConnection(self):
        if isinstance(self.host, list):
            hosts = [ split_host_port(h) for h in self.host ]
            c = MultipleServerConnector(hosts, self.factory,
                                        reactor=reactor)
            c.connect()
            return c
        else:
            host, port = split_host_port(self.host)
            return reactor.connectTCP(host, port, self.factory)


    def initializationFailed(self, reason):
        self.stopService()
        reason.raiseException()


    def isConnected(self):
        return (self.channel is not None)


    def addHandler(self, handler):
        if not IBusHandler.providedBy(handler):
            raise InterfaceNotProvided(IBusHandler, handler)
        self.handlers.append(handler)
        # get protocol handler up to speed when a connection has already
        # been established
        if self.isConnected():
            handler.connectionInitialized()

    def removeHandler(self, handler):
        handler.client = None
        self.handlers.remove(handler)


    def connectionLost(self, reason):
        # Notify all child services
        for h in self.handlers:
            if hasattr(h, "connectionLost"):
                h.connectionLost(reason)


    def connectionInitialized(self):
        """
        Send out cached stanzas and call each handler's
        C{connectionInitialized} method.
        """
        # Flush all pending packets
        d = self._sendPacketQueue()
        def doneSendingQueue(_ignore):
            # Trigger the deferred
            if not self.deferred.called:
                self.deferred.callback(self)
            # Notify all child services
            for h in self.handlers:
                if hasattr(h, "connectionInitialized"):
                    h.connectionInitialized()
        d.addCallback(doneSendingQueue)


    @defer.inlineCallbacks
    def _sendPacketQueue(self):
        while self._packetQueue:
            e, k, m = self._packetQueue.pop(0)
            yield self.send(e, k, m)

    # Wrappers

    def getQueue(self, *args, **kwargs):
        if not self.isConnected():
            return None
        return self.factory.p.queue(*args, **kwargs)

    def send(self, exchange, routing_key, message):
        if self.isConnected():
            msg = Content(message)
            msg["delivery mode"] = PERSISTENT
            if self.log_traffic:
                LOGGER.debug("PUBLISH to %s with key %s: %s"
                             % (exchange, routing_key, msg))
            d = self.channel.basic_publish(exchange=exchange,
                            routing_key=routing_key, content=msg)
            d.addErrback(self._sendFailed)
            return d
        else:
            self._packetQueue.append( (exchange, routing_key, message) )
            return defer.succeed(None)

    def _sendFailed(self, fail):
        log.err(fail)
        return fail



class BusHandler(object):
    """Abonnement à une file d'attente"""

    implements(IBusHandler)


    def __init__(self):
        self.client = None

    def setClient(self, client):
        self.client = client
        self.client.addHandler(self)



class QueueSubscriber(BusHandler):
    """Abonnement à une file d'attente"""

    implements(IBusProducer, IBusHandler)


    def __init__(self, queue_name):
        BusHandler.__init__(self)
        self.queue_name = queue_name
        self.consumer = None
        self._channel = None
        self._queue = None
        self._do_consume = True
        self.ready = defer.Deferred()


    def connectionInitialized(self):
        self._channel = self.client.channel
        d = self._create()
        d.addCallback(lambda _x: self._subscribe())
        return d

    def connectionLost(self, reason):
        self._channel = None
        self._queue = None
        self.ready = defer.Deferred()


    def _create(self):
        if not self._channel:
            return defer.succeed(None)
        d = self._channel.queue_declare(queue=self.queue_name, durable=True,
                                        exclusive=False, auto_delete=False)
        return d

    def _subscribe(self):
        if not self._channel:
            return
        d = self._channel.basic_consume(queue=self.queue_name,
                                        consumer_tag=self.queue_name)
        d.addCallback(lambda reply: self.client.getQueue(reply.consumer_tag))
        def store_queue(queue):
            self._queue = queue
        d.addCallback(store_queue)
        d.addCallback(self.ready.callback)
        return d


    def resumeProducing(self):
        if not self._queue:
            return defer.fail(NotConnected(
                        _("Can't resume producing: not connected yet")))
        d = self._queue.get()
        def cb(msg):
            if self.client.log_traffic:
                qname, msgid, unknown, exch, rkey = msg.fields
                LOGGER.debug("RECEIVED from %s on %s with key %s: %s"
                             % (exch, qname, rkey, msg.content.body))
            return self.consumer.write(msg)
        def eb(f):
            f.trap(Closed) # déconnexion pendant le get()
        d.addCallbacks(cb, eb)
        return d


    # Proxies

    def ack(self, msg, multiple=False):
        return self._channel.basic_ack(msg.delivery_tag, multiple=multiple)

    def send(self, exchange, routing_key, message):
        return self.client.send(exchange, routing_key, message)



class MessageHandler(BusHandler):

    implements(interfaces.IConsumer, IBusHandler)


    def __init__(self):
        BusHandler.__init__(self)
        self.producer = None
        self.keepProducing = True


    def write(self, msg):
        content = json.loads(msg.content.body)
        if "messages" in content:
            d = self._processList(content["messages"])
        else:
            d = defer.maybeDeferred(self.processMessage, content)
        d.addCallbacks(self.processingSucceeded, self.processingFailed,
                       callbackArgs=(msg, ))
        if self.keepProducing:
            d.addBoth(lambda _x: self.producer.resumeProducing())
        return d

    def _processList(self, msglist):
        def processOne(_ignored):
            if not msglist:
                return
            msg = msglist.pop(0)
            d = defer.maybeDeferred(self.processMessage, msg)
            d.addCallback(processOne)
            return d
        return processOne(None)

    def processMessage(self, msg):
        raise NotImplementedError()

    def processingSucceeded(self, _ignored, msg):
        self.producer.ack(msg)

    def processingFailed(self, error):
        LOGGER.error(error)


    def subscribe(self, queue_name):
        # attention, pas d'injection de deps, faire le vrai boulot dans
        # registerProducer()
        subscriber = QueueSubscriber(queue_name)
        subscriber.setClient(self.client)
        self.registerProducer(subscriber, False)

    def unsubscribe(self):
        return self.unregisterProducer()

    def registerProducer(self, producer, streaming):
        #assert streaming == False # on ne prend que des PullProducers
        self.producer = producer
        self.producer.consumer = self
        self.producer.ready.addCallback(
                lambda _x: self.producer.resumeProducing())

    def unregisterProducer(self):
        self.producer = None



class MultipleServerConnector(tcp.Connector):
    def __init__(self, hosts, factory, timeout=30, attempts=3,
                 reactor=None):
        """
        @param host: le serveur XMPP
        @type host: C{str}
        @param port: le port du serveur
        @type port C{int}
        @param factory: Une factory pour le connecteur Twisted.
        @type factory: L{twisted.internet.interfaces.IProtocolFactory}
        @param timeout: Le timeout de connexion.
        @type timeout: C{int}
        @param attempts: Le nombre de tentative de connexion.
        @type: C{int}
        @param reactor: Une instance d'un réacteur de Twisted.
        @type reactor: L{twisted.internet.reactor}
        """
        tcp.Connector.__init__(self, None, None, factory, timeout, None,
                               reactor=reactor)
        self.hosts = hosts
        self.attempts = attempts
        self._attemptsLeft = attempts
        self._usableHosts = None

    def pickServer(self):
        if not self._usableHosts:
            self._usableHosts = self.hosts[:]
        self.host, self.port = self._usableHosts[0]
        log.msg("Connecting to %s:%s" % (self.host, self.port))

    def connectionFailed(self, reason):
        assert self._attemptsLeft is not None
        self._attemptsLeft -= 1
        if self._attemptsLeft == 0:
            LOGGER.warning(_("Server %(oldserver)s did not answer after "
                    "%(attempts)d attempts"),
                    {"oldserver": self.host, "attempts": self.attempts})
            self._usableHosts.remove((self.host, self.port))
            self.resetAttempts()
            if hasattr(self.factory, "resetDelay"):
                self.factory.resetDelay()
        return tcp.Connector.connectionFailed(self, reason)

    def resetAttempts(self):
        self._attemptsLeft = self.attempts

    def _makeTransport(self):
        self.pickServer()
        return tcp.Connector._makeTransport(self)



def client_factory(settings):
    # adresse du bus
    host = settings['bus'].get('host')
    if host is not None:
        host = host.strip()
        if " " in host:
            host = [ h.strip() for h in host.split(" ") ]

    # SSL
    try:
        use_ssl = settings['bus'].as_bool('use_ssl')
    except KeyError:
        use_ssl = False

    # Temps max entre 2 tentatives de connexion (par défaut 1 min)
    max_delay = int(settings["bus"].get("max_reconnect_delay", 60))

    try:
        log_traffic = settings['bus'].as_bool('log_traffic')
    except (KeyError, ValueError):
        log_traffic = False

    vigilo_client = VigiloClient(
            host,
            settings['bus']['user'],
            settings['bus']['password'],
            use_ssl=use_ssl,
            max_delay=max_delay,
            log_traffic=log_traffic)
    vigilo_client.setName('vigilo_client')

    #try:
    #    subscriptions = settings['bus'].as_list('subscriptions')
    #except KeyError:
    #    subscriptions = []
    #vigilo_client.setupSubscriptions(subscriptions)

    return vigilo_client



class LockingError(Exception):
    """Exception remontée quand un fichier de lock est trouvé"""
    pass



class OneShotClient(object):
    """Gestionnaire de client en vue d'un usage unique"""

    client_class = VigiloClient

    def __init__(self, host, user, password, use_ssl=False,
                 lock_file=None, timeout=30):
        """
        @param host: le hostname du serveur AMQP (si besoin, spécifier le port
            après des deux-points)
        @type  host: C{str}
        @param user: Identifiant AMQP du client.
        @type  user: C{str}
        @param password: Mot de passe associé au compte AMQP.
        @type  password: C{str}
        @param use_ssl: Indique si la connexion doit être chiffrée ou non.
        @type  use_ssl: C{bool}
        @param timeout: Durée maximale d'exécution du connecteur,
            afin d'éviter des connecteurs "fous".
        @type  timeout: C{int}
        """
        self.client = self.client_class(host, user, password, use_ssl)
        self.lock_file = lock_file
        self.timeout = timeout
        self._result = 0
        self._func = None
        self._args = ()
        self._kwargs = {}
        self._logger = LOGGER


    def create_lockfile(self):
        if self.lock_file is None:
            return
        self._logger.debug(_("Creating lock file in %s"), self.lock_file)
        result = grab_lock(self.lock_file)
        if result:
            self._logger.debug(_("Lock file successfully created in %s"),
                               self.lock_file)
        else:
            self._stop(failure.Failure(LockingError()), 4)


    def _stop(self, result, code):
        """
        Arrête proprement le connecteur, en affichant un message d'erreur en
        cas de timeout.
        """
        if isinstance(result, failure.Failure):
            if result.check(defer.TimeoutError):
                self._logger.error(_("Timeout"))
            else:
                # Message générique pour signaler l'erreur
                self._logger.error(
                    _("Error: %(message)s (%(type)r)"), {
                        'message': result.getErrorMessage(),
                        'type': str(result),
                    }
                )
        else:
            self._logger.debug(_("Exiting with no error"))
        self._result = code
        d = self.client.stopService()
        d.addCallback(lambda _x: reactor.stop())
        return d


    def setHandler(self, func, *args, **kwargs):
        """
        @param func: Configure la fonction à exécuter pour déclencher
            les traitements de ce connecteur.
        @type func: C{callable}
        @note: Les paramètres supplémentaires (nommés ou non) passés
            à cette méthode seront transmis à L{func} lors de son appel.
        """
        self._func = func
        self._args = args
        self._kwargs = kwargs


    def run(self, log_traffic=False, app_name='Vigilo client'):
        """
        Fait fonctionner le connecteur (connexion, traitement, déconnexion).

        @param log_traffic: Indique si le trafic échangé avec le serveur
            doit être journalisé ou non.
        @type log_traffic: C{bool}
        @param app_name: Nom à donner au client (peut aider au débogage).
        @type app_name: C{str}
        @return: Code de retour de l'exécution du connecteur.
            La valeur 0 est renvoyée lorsque le connecteur a fini son
            exécution normalement. Toute autre valeur signale une erreur.
        @rtype: C{int}
        """
        service.Application(app_name)
        self.create_lockfile()
        # Création du client
        self.client.factory.logTraffic = log_traffic
        self.client.startService()
        d = self.client.deferred

        # Ajout de la fonction de traitement.
        if self._func:
            d.addCallback(
                self._func,
                *self._args,
                **self._kwargs
            )
        else:
            self._logger.warning(_("No handler registered for this "
                                    "one-shot client"))

        d.addErrback(lambda fail: self._stop(fail, code=1))

        # Déconnecte le client du bus.
        #d.addCallback(lambda _dummy: self.client.factory.stop())
        d.addCallback(self._stop, code=0)
        #d.addErrback(lambda _dummy: None)
        d.addErrback(log.err)

        # Garde-fou : on limite la durée de vie du connecteur.
        reactor.callLater(
            self.timeout,
            self._stop,
            result=failure.Failure(defer.TimeoutError()),
            code=3
        )
        reactor.run()
        return self._result



def oneshotclient_factory(settings):
    try:
        use_ssl = settings['bus'].as_bool('use_ssl')
    except KeyError:
        use_ssl = False

    vigilo_client = OneShotClient(
            host=settings['bus'].get('host', 'localhost'),
            user=settings['bus'].get('user', 'guest'),
            password=settings['bus'].get('password', 'guest'),
            use_ssl=use_ssl,
            timeout=int(settings['connector'].get('timeout', 30)),
            lock_file=settings['connector'].get('lock_file'),
            )

    return vigilo_client
