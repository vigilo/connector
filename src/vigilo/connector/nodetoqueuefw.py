# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :

from vigilo.common.logging import get_logger
from vigilo.pubsub import NodeSubscriber

LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate
_ = translate(__name__)

class NodeToQueueForwarder(NodeSubscriber):
    """
    Receives messages on the xmpp bus, and passes them to rule processing.
    """

    def __init__(self, subscription, queue):
        self.__queue = queue
        self.__subscription = subscription
        NodeSubscriber.__init__(self, [subscription])

    def itemsReceived(self, event):
        # See ItemsEvent
        #event.sender
        #event.recipient
        if event.nodeIdentifier != self.__subscription.node:
            return
        #event.headers
        for item in event.items:
            # Item is a domish.IElement and a domish.Element
            # Serialize as XML before queueing,
            # or we get harmless stderr pollution  × 5 lines:
            # Exception RuntimeError: 'maximum recursion depth exceeded in __subclasscheck__' in <type 'exceptions.AttributeError'> ignored
            # Stderr pollution caused by http://bugs.python.org/issue5508
            # and some touchiness on domish attribute access.
            xml = item.toXml()
            LOGGER.debug('Got item: %s', xml)
            if item.name != 'item':
                # The alternative is 'retract', which we silently ignore
                # We receive retractations in FIFO order,
                # ejabberd keeps 10 items before retracting old items.
                continue
            # Might overflow the queue, but I don't think we are
            # allowed to block.
            self.__queue.put_nowait(xml)

