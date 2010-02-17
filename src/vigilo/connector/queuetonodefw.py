# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :

from twisted.internet import reactor, protocol
from twisted.words.protocols.jabber.jid import JID
from wokkel.pubsub import PubSubClient
from wokkel.generic import parseXml
from wokkel import xmppim

import Queue as queue
import errno

from vigilo.common.logging import get_logger
from vigilo.connector.store import DbRetry
from vigilo.connector.sockettonodefw import MESSAGEONETOONE, \
                                            SocketToNodeForwarder

LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate
_ = translate(__name__)

class QueueToNodeForwarder(SocketToNodeForwarder):
    """
    Publishes pubsub items from a queue.

    Consumes serialized L{Pubsub.Item}s from a L{Queue.Queue}
    and publishes to a pubsub topic node.
    """

    def __init__(self, queue, dbfilename, dbtable, nodetopublish, service):
        # On appelle directement la méthode de PubSub car le __init__
        # de SocketToNodeForwarder essaye d'utiliser un socket UNIX.
        PubSubClient.__init__(self)
        self._queue = queue
        # Défini comme public pour faciliter les tests.
        self.retry = DbRetry(dbfilename, dbtable)
        self._service = service
        self._nodetopublish = nodetopublish

    def consumeQueue(self):
        def eb(e, xml):
            """error callback"""
            LOGGER.error(_("Error callback in consumeQueue(): %s") %
                            e.__str__())
            self.retry.store(xml)

        while self.parent is not None:
            # On tente le renvoi d'un message.
            xml = self.retry.unstore()

            if xml is None:
                try:
                    # Aucun message à renvoyer ?
                    # On récupère un message de la file dans ce cas.
                    xml = self._queue.get(block=True)
                except (IOError, OSError), e:
                    if e.errno != errno.EINTR:
                        raise
                    else:
                        continue
                else:
                    if not xml:
                        LOGGER.debug(_('Received request to shutdown'))
                        break


            item = parseXml(xml)

            # Ne devrait jamais se produire, mais au cas où...
            if item is None:
                LOGGER.error(_('Item is None in consumeQueue, ' +
                                'this should never happen!'))
                continue

            if item.name == MESSAGEONETOONE:
                self.sendOneToOneXml(item)
            else:
                self.publishXml(item)

        LOGGER.debug(_('Stopping QueueToNodeForwarder.'))
        self.disownHandlerParent(None)

    def sendQueuedMessages(self):
        # XXX Faire quelque chose d'utile ici:
        # réinsérer les éléments en attente dans la file
        # ou appeler une méthode qui tente un envoi par exemple.
        pass

    def connectionInitialized(self):
        # On passe l'appel à la méthode dans SocketToNodeForwarder
        # pour éviter une boucle infinie dans sendQueuedMessages().
        PubSubClient.connectionInitialized(self)
        # There's probably a way to configure it (on_sub vs on_sub_and_presence)
        # but the spec defaults to not sending subscriptions without presence.
        self.send(xmppim.AvailablePresence())
        LOGGER.debug('connectionInitialized')
        self.sendQueuedMessages()
        reactor.callInThread(self.consumeQueue)

