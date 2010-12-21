# vim: set fileencoding=utf-8 sw=4 ts=4 et :

"""
Classe de base pour les composants d'un connecteur.
"""

from __future__ import absolute_import

import os
import Queue

from twisted.internet import reactor, defer, threads, task
from twisted.words.xish import domish
from twisted.words.protocols.jabber.jid import JID
from wokkel.pubsub import PubSubClient, Item
from wokkel.generic import parseXml
from wokkel import xmppim

from vigilo.connector.store import DbRetry
from vigilo.common.gettext import translate
_ = translate(__name__)
from vigilo.common.conf import settings
settings.load_module(__name__)
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)


class NotConnectedError(Exception):
    def __str__(self):
        return _('no connection')

class XMPPNotConnectedError(NotConnectedError):
    def __str__(self):
        return _('no connection to the XMPP server')

class PubSubForwarder(PubSubClient):
    """
    Traite des messages en provenance de ou à destination du bus.

    @ivar _pending_replies: file des réponses à attendre de la part du serveur.
        Pour traiter ce problème, le plus logique serait d'utiliser une
        C{DeferredList}, mais ça prend beaucoup plus de mémoire (~ 2.5x).
        Quand un message est envoyé, son Deferred est ajouté dans cette file.
        Quand elle est pleine (voir le paramètre de configuration
        C{max_send_simult}), on doit attendre les réponses du serveurs, qui
        vident la file en arrivant. Sur eJabberd, cela doit correspondre au
        paramètre C{max_fsm_queue} (par défaut à 1000)
    @type _pending_replies: C{Queue.Queue}
    @ivar _nodetopublish: dictionnaire pour la correspondance type de message
                          noeud PubSub de destination.
    @type _nodetopublish: C{dict}
    @ivar _service: Le service pubsub qui héberge le nœud de publication.
    @type _service: C{twisted.words.protocols.jabber.jid.JID}
    """

    def __init__(self, dbfilename=None, dbtable=None):
        """
        Instancie un connecteur vers le bus XMPP.

        @param dbfilename: le nom du fichier permettant la sauvegarde des
                           messages en cas de problème d'éciture sur le BUS
        @type  dbfilename: C{str}
        @param dbtable: Le nom de la table SQL pour la sauvegarde des messages.
        @type  dbtable: C{str}
        """
        PubSubClient.__init__(self)
        self.name = self.__class__.__name__
        self._service = JID(settings['bus']['service'])
        self._nodetopublish = settings.get('publications', {})
        # Base de backup
        if dbfilename is None or dbtable is None:
            self.retry = None
            self._backuptoempty = False
        else:
            self.retry = DbRetry(dbfilename, dbtable)
            self._backuptoempty = os.path.exists(dbfilename)
            self._send_backup = task.LoopingCall(self.sendQueuedMessages)
        self._sendingbackup = False
        # File d'attente des réponses
        max_send_simult = int(settings['bus'].get('max_send_simult', 1000))
        # marge de sécurité de 10%
        max_send_simult = int(max_send_simult - (0.1 * max_send_simult))
        self._pending_replies = Queue.Queue(max_send_simult)
        self._waitingforreplies = False


    def connectionInitialized(self):
        """
        Lancée à la connexion (ou re-connexion).
        Redéfinie pour pouvoir vider les messages en attente.
        """
        PubSubClient.connectionInitialized(self)
        # There's probably a way to configure it (on_sub vs on_sub_and_presence)
        # but the spec defaults to not sending subscriptions without presence.
        self.send(xmppim.AvailablePresence())
        LOGGER.info(_('Connected to the XMPP bus'))
        if self.retry is not None and not self._send_backup.running:
            self._send_backup.start(5)

    def connectionLost(self, reason):
        """
        Lancée à la perte de la connexion au bus. Permet d'arrêter d'envoyer
        les messages en attente.
        """
        PubSubClient.connectionLost(self, reason)
        LOGGER.info(_('Lost connection to the XMPP bus (reason: %s)'), reason)
        if self.retry is not None and self._send_backup.running:
            self._send_backup.stop()


    @defer.inlineCallbacks
    def sendQueuedMessages(self):
        """
        Vide la base de données des messages en attente. Prioritaire sur
        l'envoi depuis la source nominale, puisque ces messages sont plus
        anciens (et c'est important pour RRDTool).

        @note: U{http://stackoverflow.com/questions/776631/using-twisteds-twisted-web-classes-how-do-i-flush-my-outgoing-buffers}
        """
        if self.retry is None:
            return
        if not self._backuptoempty:
            return
        self._backuptoempty = False
        self._sendingbackup = True
        while self.xmlstream is not None:
            msg = yield self.retry.unstore()
            if msg is None:
                break
            #LOGGER.debug(_('Loaded message from db: %r') % msg)
            xml = parseXml(msg)
            yield self.forwardMessage(xml, source="backup")

        self.retry.vacuum()
        self._sendingbackup = False
        LOGGER.info(_('Done sending backup'))


    def _send_failed(self, e, msg):
        """errback: remet le message en base"""
        errmsg = _('Unable to forward the message (%(reason)s)')
        if self.retry is not None:
            errmsg += _('. it has been stored for later retransmission')
        LOGGER.error(errmsg % {"reason": e.getErrorMessage()})
        if self.retry is not None:
            self.storeMessage(msg)

    def storeMessage(self, xml):
        """Mise en base du message"""
        if self.retry is None:
            return
        def cb(result):
            self._backuptoempty = True
        d = self.retry.store(xml)
        d.addCallback(cb)

    def forwardMessage(self, msg, source=""):
        if source != "backup" and \
                (self._sendingbackup or self._waitingforreplies):
            self.storeMessage(msg)
            return
        raise NotImplementedError()

    def waitForReplies(self):
        """
        Attente des réponses de la part du bus. Les réponses sont dans
        L{_pending_replies}, et sont dépilées au fur et à mesure de leur
        arrivée.

        Note: l'implémentation n'utilise pas {defer.inlineDeferred} car on va
        déjà faire appel à cette méthode par un C{yield} dans
        L{sendQueuedMessages}, donc on a pas le droit de I{yielder} nous-même.

        @return: un Deferred qui se déclenche quand toutes les réponses sont
            arrivées
        @rtype:  C{Deferred}
        """
        self._waitingforreplies = True
        LOGGER.info(_('Batch sent, waiting for replies from the bus'))
        def empty_queue():
            try:
                reply = self._pending_replies.get_nowait()
            except Queue.Empty:
                return
            reply.addCallback(task_done)
        def task_done(result):
            self._pending_replies.task_done()
            reactor.callLater(0, empty_queue)
        def done_waiting(result):
            LOGGER.info(_('Replies received, resuming sending'))
            self._waitingforreplies = False
            self.sendQueuedMessages()

        empty_queue()
        d = threads.deferToThread(self._pending_replies.join)
        d.addCallback(done_waiting)
        return d

    def sendOneToOneXml(self, xml):
        """
        function to send a XML msg to a particular jabber user
        @param xml: le message a envoyé sous forme XML
        @type xml: twisted.words.xish.domish.Element
        """
        # we need to send it to a particular receiver
        # il faut l'envoyer vers un destinataire en particulier
        msg = domish.Element((None, "message"))
        msg["to"] = xml['to']
        msg["from"] = self.parent.jid.userhostJID().full()
        msg["type"] = 'chat'
        body = xml.firstChildElement()
        msg.addElement("body", content=body)
        # if not connected store the message
        if self.xmlstream is None:
            result = defer.fail(XMPPNotConnectedError())
        else:
            result = self.send(msg)
        result.addErrback(self._send_failed, msg.toXml().encode('utf8'))
        return result

    def publishXml(self, xml):
        """
        function to publish a XML msg to node
        @param xml: le message a envoyé sous forme XML
        @type xml: twisted.words.xish.domish.Element
        """
        item = Item(payload=xml)
        if xml.name not in self._nodetopublish:
            LOGGER.error(_("No destination node configured for messages "
                           "of type '%s'. Skipping.") % xml.name)
            del item
            return defer.succeed(True)
        node = self._nodetopublish[xml.name]
        try:
            result = self.publish(self._service, node, [item])
        except AttributeError:
            result = defer.fail(XMPPNotConnectedError())
        finally:
            del item
        result.addErrback(self._send_failed, xml.toXml().encode('utf8'))
        return result

