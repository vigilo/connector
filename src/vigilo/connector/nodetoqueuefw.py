# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Ce module est un demi-connecteur qui assure la redirection des messages
issus du bus XMPP vers une file d'attente (C{Queue.Queue} ou compatible).
"""
import os.path
import Queue
import errno

from wokkel.pubsub import PubSubClient

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate
from vigilo.connector.store import DbRetry

LOGGER = get_logger(__name__)
_ = translate(__name__)

class NodeToQueueForwarder(PubSubClient, object):
    """
    Cette classe redirige les messages reçus depuis le bus XMPP
    vers une file d'attente compatible avec C{Queue.Queue}.
    """

    def __init__(self, queue, dbfilename, dbtable):
        """
        Initialisation du demi-connecteur.
        
        @param queue: File d'attente vers laquelle les messages XMPP
            reçu seront transférés.
        @type queue: C{Queue.Queue}
        @param dbfilename: Emplacement du fichier SQLite de sauvegarde.
            Ce fichier est utilisé pour stocker temporairement les messages
            lorsque la file n'est plus disponible. Les messages dans cette
            base de données seront automatiquement retransférés lorsque la
            file sera de nouveau joignable.
        @type dbfilename: C{basestring}
        @param dbtable: Nom de la table à utiliser dans le fichier de
            sauvegarde L{dbfilename}.
        @type dbtable: C{basestring}
        """
        super(NodeToQueueForwarder, self).__init__()
        self.__queue = queue
        # Défini comme public pour faciliter les tests.
        self.retry = DbRetry(dbfilename, dbtable)
        self.__backuptoempty = os.path.exists(dbfilename) 
        self.sendQueuedMessages()

    def itemsReceived(self, event):
        """
        Méthode appelée lorsque des éléments ont été reçus depuis
        le bus XMPP.
        
        @param event: Événement XMPP reçu.
        @type event: C{twisted.words.xish.domish.Element}
        """
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
        """
        Transfère un message XML sérialisé vers la file.

        @param xml: message XML à transférer.
        @type xml: C{str}
        """
        # Might overflow the queue, but I don't think we are
        # allowed to block.
        try:
            self.__queue.put_nowait(xml)
        except IOError, e:
            # Erreur "Broken pipe" lorsque le message
            # est trop long pour être stocké dans la file.
            if e.errno == errno.EPIPE:
                LOGGER.error(_('Incoming message is too big to be stored '
                    'in the queue, dropping it.'))
            else:
                raise
        except Queue.Full:
            LOGGER.error(_('The queue is full, dropping incoming '
                'XML message! (%s)') % xml)

    def sendQueuedMessages(self):
        """
        Déclenche l'envoi des messages stockées localement (retransmission
        des messages suite à une panne).
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


