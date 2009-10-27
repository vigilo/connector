# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :

from vigilo.common.logging import get_logger
from wokkel.pubsub import PubSubClient
import os.path

LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate
from vigilo.connector.store import DbRetry
_ = translate(__name__)

class NodeToQueueForwarder(PubSubClient, object):
    """
    Receives messages on the xmpp bus, and passes them to rule processing.
    """

    def __init__(self, queue, dbfilename, dbtable):
        super(NodeToQueueForwarder, self).__init__()
        self.__queue = queue
        # Défini comme public pour faciliter les tests.
        self.retry = DbRetry(dbfilename, dbtable)
        self.__backuptoempty = os.path.exists(dbfilename) 
        self.sendQueuedMessages()

    def itemsReceived(self, event):
        for item in event.items:
            # Item is a domish.IElement and a domish.Element
            # Serialize as XML before queueing,
            # or we get harmless stderr pollution  × 5 lines:
            # Exception RuntimeError: 'maximum recursion depth exceeded in
            # __subclasscheck__' in <type 'exceptions.AttributeError'> ignored
            #
            # stderr pollution caused by http://bugs.python.org/issue5508
            # and some touchiness on domish attribute access.
            xml = item.toXml()
            LOGGER.debug('Got item: %s', xml)
            if item.name != 'item':
                # The alternative is 'retract', which we silently ignore
                # We receive retractations in FIFO order,
                # ejabberd keeps 10 items before retracting old items.
                continue
            self.messageForward(xml)

    def messageForward(self, xml):
            # Might overflow the queue, but I don't think we are
            # allowed to block.
            self.__queue.put_nowait(xml)

    def sendQueuedMessages(self):
        """
        Called to send Message previously stored
        """
        if self.__backuptoempty:
            self.__backuptoempty = False
            # XXX Ce code peut potentiellement boucler indéfiniment...
            while True:
                msg = self.retry.unstore()
                if msg is None:
                    break
                else:
                    if self.messageForward(msg) is not True:
                        # we loose the ability to send message again
                        self.__backuptoempty = True
                        break
            self.retry.vacuum()


