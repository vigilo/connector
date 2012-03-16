# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2011-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Gestionnaires de messages
"""

from __future__ import absolute_import

import os
import time
from datetime import datetime
from collections import deque
from platform import python_version_tuple

from zope.interface import implements

from twisted.internet import defer
from twisted.internet.interfaces import IConsumer, IPushProducer
from twisted.application.service import Service
from twisted.python.failure import Failure

import txamqp

from vigilo.connector import json
from vigilo.connector.interfaces import IBusHandler, IBusProducer
from vigilo.connector.store import DbRetry
from vigilo.connector.amqp import getErrorMessage

from vigilo.common.gettext import translate
_ = translate(__name__)
from vigilo.common.logging import get_logger, get_error_message
LOGGER = get_logger(__name__)



class BusHandler(object):
    """Gestionnaire de base à brancher à un client du bus"""

    implements(IBusHandler)


    def __init__(self):
        self.client = None

    def setClient(self, client):
        """Affecte l'instance du client AMQP.

        @param client: instance du client AMQP
        @type  client: L{vigilo.connector.client.VigiloClient}
        """
        self.client = client
        self.client.addHandler(self)

    def connectionInitialized(self):
        """Opérations à réaliser à la connexion au bus."""
        pass

    def connectionLost(self, reason):
        """Opérations à réaliser à la perte de connexion au bus"""
        pass



class QueueSubscriber(BusHandler):
    """Abonnement à une file d'attente

    @ivar queue_name: nom de la file d'attente AMQP
    @type queue_name: C{str}
    @ivar consumer: destinataire des messages reçus
    @type consumer: instance de L{MessageHandler}
    @ivar ready: I{Deferred} pour l'abonnement à la file d'attente
    @type ready: C{Deferred}
    """

    implements(IBusProducer, IBusHandler)


    def __init__(self, queue_name):
        """
        @param queue_name: nom de la file d'attente AMQP
        @type  queue_name: C{str}
        """
        BusHandler.__init__(self)
        self.queue_name = queue_name
        self._bindings = []
        self.consumer = None
        self._channel = None
        self._queue = None
        self._do_consume = True
        self.ready = defer.Deferred()
        self._production_interrupted = False


    def connectionInitialized(self):
        """Opérations à réaliser à la connexion au bus:
        - on déclare la file d'attente
        - on abonne la file d'attente aux I{exchanges} désirés
        - on prépare la récupération des messages de la file

        Si on a été déconnecté et qu'on était en train de dépiler les messages,
        on reprend le dépilement. Sinon, on attend que la méthode
        L{resumeProducing} soit appelée.
        """
        super(QueueSubscriber, self).connectionInitialized()
        self._channel = self.client.channel
        d = self._create()
        d.addCallback(lambda _x: self._bind())
        d.addCallback(lambda _x: self._subscribe())
        if self._production_interrupted:
            self._production_interrupted = False
            d.addCallback(lambda _x: self.resumeProducing())
        def on_error(fail):
            """Sur un échec d'initialisation, on se déconnecte."""
            errmsg = _('Could not initialize the queue: %(reason)s')
            LOGGER.warning(errmsg % {"reason": getErrorMessage(fail)})
            self.client.disconnect()
        d.addCallbacks(self.ready.callback, on_error)

    def connectionLost(self, reason):
        """
        Perte de connexion au bus, on réinitialise les variables internes
        """
        super(QueueSubscriber, self).connectionLost(reason)
        self._channel = None
        self._queue = None
        self.ready = defer.Deferred()


    def bindToExchange(self, exchange, routing_key=None):
        """
        Permet de demander l'abonnement de la file d'attente à un I{exchange}
        AMQP. Cet abonnement ne sera véritablement réalisé qu'à la connexion au
        bus.
        """
        if routing_key is None:
            routing_key = self.queue_name
        self._bindings.append( (exchange, routing_key) )


    def _create(self):
        """
        Déclare la file d'attente auprès du bus. Si la file existe déjà, elle
        est réutilisée de manière transparente.
        """
        if not self._channel:
            return defer.succeed(None)
        d = self._channel.queue_declare(queue=self.queue_name,
                    durable=True, exclusive=False, auto_delete=False)
        return d

    def _bind(self):
        """
        Abonne une file d'attente à un I{exchange} AMQP du bus
        """
        dl = []
        for exchange, routing_key in self._bindings:
            d = self.client.channel.queue_bind(queue=self.queue_name,
                    exchange=exchange, routing_key=routing_key)
            dl.append(d)
        return defer.DeferredList(dl)

    def _subscribe(self):
        """
        Prépare le dépilement des messages de la file, mais ne commence pas à
        dépiler tout de suite (pour cela, appeler L{resumeProducing}).
        """
        if not self._channel:
            return
        # On se laisse un buffer de 5 en mémoire, de toute façon il faut les
        # acquitter donc en cas de plantage ils ne seront pas perdus
        d = self._channel.basic_qos(prefetch_count=5)
        d.addCallback(lambda _reply: self._channel.basic_consume(
                      queue=self.queue_name, consumer_tag=self.queue_name))
        d.addCallback(lambda reply: self.client.getQueue(reply.consumer_tag))
        def store_queue(queue):
            self._queue = queue
            return queue
        d.addCallback(store_queue)
        return d


    def resumeProducing(self):
        """
        Dépile un (seul) message de la file d'attente. Appeler une deuxième
        fois pour dépiler un autre message (mode PullProducer).
        """
        if not self._queue:
            if self.ready.called:
                return defer.fail(Exception(
                            _("Can't resume producing: not connected yet")))
            else:
                self.ready.addCallback(lambda _x: self.resumeProducing())
                return
        d = self._queue.get()
        def cb(msg):
            if self.client.log_traffic:
                # Unused variable:
                # pylint: disable-msg=W0612
                qname, msgid, unknown, exch, rkey = msg.fields
                LOGGER.debug("RECEIVED from %s on %s with key %s: %s"
                             % (exch, qname, rkey, msg.content.body))
            return self.consumer.write(msg)
        def eb(f):
            f.trap(txamqp.queue.Closed) # déconnexion pendant le get()
            self._production_interrupted = True
        d.addCallbacks(cb, eb)
        # On ne retourne pas le deferred ici pour éviter des recursion errors:
        # resumeProducing -> write -> resumeProducing -> ...
        #return d


    # Proxies

    def ack(self, msg, multiple=False):
        """
        Acquitter un message du bus
        @param msg: message à acquitter
        @type  msg: C{txamqp.message.Message}
        """
        return self._channel.basic_ack(msg.delivery_tag, multiple=multiple)

    def nack(self, msg, multiple=False, requeue=True):
        """
        C{basic_nack()} semble être une extension spécifique RabbitMQ au
        protocole, au moins à la version 0.8. On utilise donc
        C{basic_reject()}.

        Références:
         - U{http://www.rabbitmq.com/amqp-0-9-1-quickref.html#basic.nack}
         - U{http://www.rabbitmq.com/extensions.html#consuming}
        """
        #return self._channel.basic_nack(msg.delivery_tag, multiple=multiple,
        #                                requeue=requeue)
        return self._channel.basic_reject(msg.delivery_tag, requeue=requeue)

    def send(self, exchange, routing_key, message):
        """
        Envoyer un message sur le bus
        @param exchange: nom de l'I{exchange} où publier
        @type  exchange: C{str}
        @param routing_key: clé de routage
        @type  routing_key: C{str}
        @param message: message à publier
        @type  message: C{str}
        """
        return self.client.send(exchange, routing_key, message)



class MessageHandler(BusHandler):
    """
    Gère la réception des messages. Peut aussi agir comme un IPushProducer.

    @ivar producer: instance de L{QueueSubscriber} qui fournit les messages.
    @type producer: L{QueueSubscriber}
    """

    implements(IConsumer, IPushProducer, IBusHandler)


    def __init__(self):
        BusHandler.__init__(self)
        self.producer = None
        self.keepProducing = True
        # Stats
        self._messages_received = 0


    def write(self, msg):
        """
        Méthode à appeler pour traiter un message en provenance du bus.

        Si le traitement se passe bien (pas d'I{errback}), le message sera
        acquitté, sinon il sera rejeté, puis le message suivant sera demandé au
        bus.

        @param msg: message à traiter
        @type  msg: C{txamqp.message.Message}
        """
        try:
            content = json.loads(msg.content.body)

        except ValueError:
            LOGGER.warning(_("Received message is not JSON-encoded: %r"),
                           msg.content.body)
            d = defer.succeed(None)

        else:
            if "messages" in content and content["messages"]:
                d = self._processList(content["messages"])
            else:
                d = defer.maybeDeferred(self.processMessage, content)
            d.addCallbacks(self.processingSucceeded, self.processingFailed,
                           callbackArgs=(msg, ), errbackArgs=(msg, ))

        if self.keepProducing:
            d.addBoth(lambda _x: self.producer.resumeProducing())
        return d


    @defer.inlineCallbacks
    def _processList(self, msglist):
        while msglist:
            msg = msglist.pop(0)
            yield defer.maybeDeferred(self.processMessage, msg)


    def processMessage(self, msg):
        """
        Méthode à réimplémenter pour traiter véritablement un message.
        @param msg: message à traiter
        @type  msg: C{txamqp.message.Message}
        """
        raise NotImplementedError()


    def processingSucceeded(self, _ignored, msg):
        """
        Appelée quand un message est traité correctement : le message est
        acquitté.
        """
        self._messages_received += 1
        return self.producer.ack(msg)

    def processingFailed(self, error, msg):
        """
        Appelée quand le traitement d'un message a échoué : le message est
        rejeté.
        """
        LOGGER.warning(error.getErrorMessage())
        return self.producer.nack(msg)


    def pauseProducing(self):
        """Permet d'arrêter le dépilement des messages."""
        self.keepProducing = False

    def resumeProducing(self):
        """
        Permet de rémarrer ou de reprendre le dépilement des messages. Un seul
        appel suffit, le message suivant sera automatiquement demandé après
        traitement.
        """
        self.keepProducing = True
        self.producer.resumeProducing()


    def getStats(self):
        """Récupère des métriques de fonctionnement du connecteur"""
        stats = {
            "received": self._messages_received,
            }
        return defer.succeed(stats)


    def subscribe(self, queue_name, bindings=None):
        """
        Spéficie la file d'attente AMQP à dépiler, avec optionnellements des
        abonnements à réaliser.

        @param queue_name: nom de la file d'attente
        @type  queue_name: C{str}
        @param bindings: abonnements de la file d'attente. Il s'agit d'une liste de couples C{(exchange, routing_key)}.
        @type  bindings: C{list}
        """
        # attention, pas d'injection de deps, faire le vrai boulot dans
        # registerProducer()
        subscriber = QueueSubscriber(queue_name)
        if bindings is None:
            bindings = []
        for exchange, routing_key in bindings:
            subscriber.bindToExchange(exchange, routing_key)
        subscriber.setClient(self.client)
        self.registerProducer(subscriber, False)

    def unsubscribe(self):
        """Supprime la connexion à la file d'attente AMQP."""
        return self.unregisterProducer()

    def registerProducer(self, producer, streaming):
        """
        Enregistre l'instance du L{QueueSubscriber} comme producteur.
        @param producer: instance de L{QueueSubscriber}
        @type  producer: L{QueueSubscriber}
        @param streaming: mode de production (C{PullProducer} ou
            C{PushProducer}). Ici, on n'accepte que les C{PullProducer}s.
        @type  streaming: C{boolean}
        """
        #assert streaming == False # on ne prend que des PullProducers
        self.producer = producer
        self.producer.consumer = self
        self.producer.ready.addCallback(
                lambda _x: self.producer.resumeProducing())

    def unregisterProducer(self):
        """@see: L{unsubscribe}"""
        self.producer = None



class BusPublisher(BusHandler):
    """
    Gère la publication de messages

    @ivar producer: le producteur de données à destination du bus
    @ivar batch_send_perf: doit-on accumuler les messages de perf ?
    @type batch_send_perf: C{bool}
    """

    implements(IConsumer, IBusHandler)


    def __init__(self, publications={}, batch_send_perf=1):
        BusHandler.__init__(self)
        self.name = self.__class__.__name__
        self.producer = None
        self._is_streaming = True
        self._publications = publications
        self._initialized = False
        # Stats
        self._messages_sent = 0
        # Accumulation des messages de perf
        self.batch_send_perf = batch_send_perf
        self._batch_perf_queue = deque()


    def connectionInitialized(self):
        """
        Lancée à la connexion (ou re-connexion).
        Redéfinie pour pouvoir vider les messages en attente.
        """
        super(BusPublisher, self).connectionInitialized()
        self._initialized = True
        # les stats sont des COUNTERs, on peut réinitialiser
        self._messages_sent = 0
        if self.producer is not None:
            self.producer.resumeProducing()


    def connectionLost(self, reason):
        """
        Lancée à la perte de la connexion au bus. Permet d'arrêter d'envoyer
        les messages en attente.
        """
        super(BusPublisher, self).connectionLost(reason)
        self._initialized = False
        if self.producer is not None:
            self.producer.pauseProducing()
        if reason is None:
            reason = Failure(Exception())


    def isConnected(self):
        """
        Teste si on est connecté au bus
        """
        return self._initialized


    def getStats(self):
        """Récupère des métriques de fonctionnement du connecteur"""
        stats = {
            "sent": self._messages_sent,
            }
        return defer.succeed(stats)


    def registerProducer(self, producer, streaming):
        """Enregistre le producteur des messages"""
        self.producer = producer
        self._is_streaming = streaming
        self.producer.consumer = self
        if self.isConnected():
            self.producer.resumeProducing()

    def unregisterProducer(self):
        """Débranche le producteur des messages"""
        self.producer.pauseProducing()
        self.producer = None


    def write(self, data):
        """
        Méthode appelée par le producteur pour envoyer un message sur le bus.
        """
        d = self.sendMessage(data)
        def doneSending(result):
            """Si on a un PullProducer, on demande le message suivant"""
            if self.producer is not None and not self._is_streaming:
                self.producer.resumeProducing()
            return result
        d.addBoth(doneSending)
        return d


    def sendMessage(self, msg):
        """
        Traite un message en l'envoyant sur le bus.

        @param msg: message à traiter
        @type  msg: C{str} ou C{dict}
        @return: le C{Deferred} avec la réponse, ou C{None} si cela n'a pas
            lieu d'être (message envoyé en push)
        """
        self._messages_sent += 1
        if isinstance(msg, basestring):
            msg = json.loads(msg)
        try:
            if isinstance(msg["timestamp"], datetime):
                msg["timestamp"] = time.mktime(msg["timestamp"].timetuple())
        except (KeyError, TypeError):
            pass
        # accumulation des messages de perf
        msg = self._accumulate_perf_msgs(msg)
        if msg is None:
            return defer.succeed(None)
        msg_text = json.dumps(msg)

        if msg["type"] in self._publications:
            exchange = self._publications[msg["type"]]
        else:
            exchange = msg["type"]

        routing_key = msg.get("routing_key", msg["type"])
        persistent = msg.get("persistent", True)
        result = self.client.send(exchange, str(routing_key), msg_text,
                                  persistent, content_type="application/json")
        return result


    def _accumulate_perf_msgs(self, msg):
        """
        Accumule les messages de performance dans un plus gros message, pour
        limiter le nombre de messages circulant sur le bus (et donc aussi les
        acquittements correspondants)
        """
        if self.batch_send_perf <= 1 or msg["type"] != "perf":
            return msg # on est pas concerné
        self._batch_perf_queue.append(msg)
        if len(self._batch_perf_queue) < self.batch_send_perf:
            return None
        batch_msg = {"type": "perf",
                     "messages": list(self._batch_perf_queue)}
        self._batch_perf_queue.clear()
        #LOGGER.info("Sent a batch perf message with %d messages",
        #            self.batch_send_perf)
        return batch_msg



class BackupProvider(Service):
    """
    Ajoute à un PushProducer la possibilité d'être mis en pause. Les données
    vont alors dans une file d'attente mémoire qui est sauvegardée sur le
    disque dans une base.

    @ivar producer: source de messages
    @ivar consumer: destination des messages
    @ivar paused: etat de la production
    @type paused: C{bool}
    @ivar queue: file d'attente mémoire
    @type queue: C{deque}
    @ivar max_queue_size: taille maximum de la file d'attente mémoire
    @type max_queue_size: C{int}
    @ivar retry: base de données de stockage
    @type retry: L{DbRetry}
    @ivar stat_names: nom des données de performances produites à destination de
        Vigilo
    @type stat_names: C{dict}
    """

    implements(IPushProducer, IConsumer)


    def __init__(self, dbfilename=None, dbtable=None, max_queue_size=None):
        self.producer = None
        self.consumer = None
        self.paused = True
        # File d'attente mémoire
        self.max_queue_size = max_queue_size
        self.queue = None
        self._build_queue()
        self._processing_queue = False
        # Base de backup
        if dbfilename is None or dbtable is None:
            self.retry = None
        else:
            self.retry = DbRetry(dbfilename, dbtable)
        # Stats
        self.stat_names = {
                "queue": "queue",
                "backup_in_buf": "backup_in_buf",
                "backup_out_buf": "backup_out_buf",
                "backup": "backup",
                }


    def _build_queue(self):
        if self.max_queue_size is not None:
            self.queue = deque(maxlen=self.max_queue_size)
        else:
            # sur python < 2.6, il n'y a pas de maxlen
            self.queue = deque()


    def startService(self):
        """Executé au démarrage du connecteur"""
        d = self.retry.initdb()
        if self.producer is not None:
            d.addCallback(lambda _x: self.producer.startService())
        return d


    def stopService(self):
        """Executé à l'arrêt du connecteur"""
        if self.producer is not None:
            d = self.producer.stopService()
        else:
            d = defer.succeed(None)
        d.addCallback(lambda _x: self._saveToDb())
        d.addCallback(lambda _x: self.retry.flush())
        return d


    def registerProducer(self, producer, streaming):
        """
        Enregistre le producteur des messages, qui doit être un PushProducer.
        Si c'était un PullProducer, cette classe ne serait pas nécessaire,
        puisqu'il suffirait de ne pas appeler C{resumeProducing}.
        """
        assert streaming == True # Ça n'a pas de sens avec un PullProducer
        self.producer = producer
        self.producer.consumer = self

    def unregisterProducer(self):
        """Supprime le producteur"""
        #self.producer.pauseProducing() # A priori il sait pas faire
        self.producer = None


    def getStats(self):
        """Récupère des métriques de fonctionnement"""
        stats = {
            self.stat_names["queue"]: len(self.queue),
            self.stat_names["backup_in_buf"]: len(self.retry.buffer_in),
            self.stat_names["backup_out_buf"]: len(self.retry.buffer_out),
            }
        backup_size_d = self.retry.qsize()
        def add_backup_size(backup_size):
            stats[ self.stat_names["backup"] ] = backup_size
            return stats
        backup_size_d.addCallbacks(add_backup_size,
                                   lambda e: add_backup_size("U"))
        return backup_size_d


    def write(self, data):
        """Méthode appelée par le producteur pour transférer un message."""
        self.queue.append(data)
        self.processQueue()


    def pauseProducing(self):
        """
        Met en pause la production vers le consommateur. Les messages en entrée
        seront stockés en base de données à partir de maintenant.
        """
        self.paused = True
        d = self._saveToDb()
        d.addCallback(lambda _x: self.retry.flush())
        return d


    def resumeProducing(self):
        """
        Débute ou reprend la production vers le consommateur. Les messages
        seront pris en priorité depuis le backup.
        """
        self.paused = False
        if self.retry.initialized.called:
            d = self.processQueue()
        else:
            d = self.retry.initialized
            d.addCallback(lambda _x: self.processQueue())
        return d


    def stopProducing(self):
        pass


    @defer.inlineCallbacks
    def processQueue(self):
        """
        Traite les messages en attente, en donnant la priorité à la base de
        backup (L{retry}).
        """
        if self._processing_queue:
            return
        if self.paused:
            yield self._saveToDb()
            return

        self._processing_queue = True
        while True:
            msg = yield self._getNextMsg()
            if msg is None:
                break
            try:
                yield self.consumer.write(msg)
            except Exception, e:
                self._send_failed(e, msg)
        self._processing_queue = False


    def _send_failed(self, e, msg):
        """errback: remet le message en base"""
        errmsg = _('Requeuing message (%(reason)s).')
        LOGGER.info(errmsg % {
            "reason": get_error_message(e),
        })
        self.queue.append(msg)


    def _saveToDb(self):
        """Sauvegarde tous les messages de la file dans la base de backup."""
        def eb(f):
            LOGGER.error(_("Error trying to save a message to the backup "
                           "database: %s"), get_error_message(f.value))
        saved = []
        while len(self.queue) > 0:
            msg = self.queue.popleft()
            d = self.retry.put(json.dumps(msg))
            d.addErrback(eb)
            saved.append(d)
        return defer.gatherResults(saved)

    def _getNextMsg(self):
        """
        Récupère le prochain message à traiter, en commençant par essayer dans
        la base de backup (L{retry}).
        """
        d = self.retry.pop()
        def get_from_queue(msg):
            if msg is not None:
                return json.loads(msg) # le backup est prioritaire
            # on dépile la file principale
            try:
                msg = self.queue.popleft()
            except IndexError:
                # plus de messages
                return None
            return msg
        d.addCallback(get_from_queue)
        return d


# Factories


def buspublisher_factory(settings, client=None):
    """Instanciation d'un L{BusPublisher}.

    @param settings: fichier de configuration
    @type  settings: C{vigilo.common.conf.settings}
    @param client: client du bus
    @type  client: L{vigilo.connector.client.VigiloClient}
    """
    publications = settings.get('publications', {}).copy()
    batch_send_perf = int(settings["bus"].get("batch_send_perf", 1))
    publisher = BusPublisher(publications, batch_send_perf)
    if client is not None:
        publisher.setClient(client)
    return publisher


def backupprovider_factory(settings, producer=None):
    """Instanciation d'un L{BackupProvider}.

    @param settings: fichier de configuration
    @type  settings: C{vigilo.common.conf.settings}
    @param producer: producteur de données
    """
    # Max queue size
    try:
        max_queue_size = int(settings["connector"]["max_queue_size"])
    except KeyError:
        max_queue_size = 0
    except ValueError:
        LOGGER.warning(_("Can't understand the max_queue_size option, it "
                         "should be an integer (or 0 for no limit). "
                         "Current value: %s"), max_queue_size)
        max_queue_size = 0
    if max_queue_size <= 0:
        max_queue_size = None
    if (max_queue_size is not None and
                tuple(python_version_tuple()) < ('2', '6')):
        LOGGER.warning(_("The max_queue_size option is only available "
                         "on Python >= 2.6. Ignoring."))
        max_queue_size = None

    # Base de backup
    bkpfile = settings['connector'].get('backup_file', ":memory:")
    if bkpfile != ':memory:':
        if not os.path.exists(os.path.dirname(bkpfile)):
            msg = _("Directory not found: '%(dir)s'") % \
                    {'dir': os.path.dirname(bkpfile)}
            LOGGER.error(msg)
            raise OSError(msg)
        if not os.access(os.path.dirname(bkpfile), os.R_OK | os.W_OK | os.X_OK):
            msg = _("Wrong permissions on directory: '%(dir)s'") % \
                    {'dir': os.path.dirname(bkpfile)}
            LOGGER.error(msg)
            raise OSError(msg)
    bkptable = settings['connector'].get('backup_table_to_bus', "tobus")

    backup = BackupProvider(bkpfile, bkptable, max_queue_size)

    if producer is not None:
        backup.registerProducer(producer, True)

    return backup
