# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :

from twisted.internet import reactor
from wokkel import pubsub
from wokkel.generic import parseXml

import Queue as queue
import os

from vigilo.common.logging import get_logger
from vigilo.connector.store import DbRetry

LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate
_ = translate(__name__)

class QueueToNodeForwarder(pubsub.PubSubClient):
    """
    Publishes pubsub items from a queue.

    Consumes serialized L{Pubsub.Item}s from a L{Queue.Queue}
    and publishes to a pubsub topic node.
    """

    def __init__(self, queue, subscription, dbfilename, dbtable):
        self.__queue = queue
        self.__subscription = subscription
        self.__backuptoempty = os.path.exists(dbfilename)
        # Défini comme public pour faciliter les tests.
        self.retry = DbRetry(dbfilename, dbtable)
        self.__stop = False

    def consumeQueue(self):
        def eb(e, xml):
            """error callback"""
            LOGGER.error(_("error callback consumeQueue %s") % e.__str__())
            self.retry.store(xml)
            self.__backuptoempty = True                                      

        # Isn't there a callInThread / callFromThread decorator?
        while not self.__stop and self.parent is not None:
            LOGGER.debug(_('consumeQueue'))

            xml = None
            if self.__backuptoempty:
                xml = self.retry.unstore()

            if xml == True:
                self.__backuptoempty = False
                self.retry.vacuum()

            if xml is None or xml == True:
                try:
                    # Use a timeout so that we notice when __stop flips.
                    xml = self.__queue.get(block=True, timeout=1.)
                except queue.Empty:
                    continue

            # Parsing is thread safe I expect
            item = parseXml(xml)
            if not (item.uri == pubsub.NS_PUBSUB
                    and item.name == u'item'):
                raise TypeError(item, pubsub.Item)

            # XXX Connection loss might be problematic
            try:
                result = self.publish(
                    self.__subscription.service,
                    self.__subscription.node,
                    [item])
                result.addErrback(eb, xml)
            except AttributeError, e:
                LOGGER.error('attr error: %s' % e.__str__())
                LOGGER.error('Unable to forward message from queue to ' + 
                    'the XMPP bus. The message has been stored for later ' +
                    'retransmission.')
                self.retry.store(xml)
                self.__backuptoempty = True

    def connectionInitialized(self):
        super(QueueToNodeForwarder, self).connectionInitialized()
        reactor.callInThread(self.consumeQueue)

    def connectionLost(self, reason):
        self.__stop = True
        super(QueueToNodeForwarder, self).connectionLost(reason)

