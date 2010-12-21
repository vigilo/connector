# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Ce module est un demi-connecteur qui assure la redirection des messages
issus d'une file d'attente (C{Queue.Queue} ou compatible) vers le bus XMPP.
"""
from twisted.internet import reactor, defer, threads
from wokkel.generic import parseXml

import errno

from vigilo.common.logging import get_logger
from vigilo.connector.forwarder import PubSubForwarder

LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate
_ = translate(__name__)

class QueueToNodeForwarder(PubSubForwarder):
    """
    Redirige les messages reçus depuis une file vers le bus XMPP.

    Consomme des messages sérialisés (C{Pubsub.Item}) depuis une file
    (C{Queue.Queue}) et les publie sur un nœud XMPP.
    """

    def __init__(self, queue, dbfilename, dbtable):
        """
        Initialisation du demi-connecteur.

        @param queue: File dont les messages seront redirigés vers
            un nœud XMPP.
        @type queue: C{Queue.Queue}
        @param dbfilename: Emplacement du fichier SQLite de sauvegarde.
            Ce fichier est utilisé pour stocker temporairement les messages
            lorsque le bus XMPP n'est plus disponible. Les messages dans cette
            base de données seront automatiquement retransférés lorsque le bus
            sera de nouveau joignable.
        @type dbfilename: C{basestring}
        @param dbtable: Nom de la table à utiliser dans le fichier de
            sauvegarde L{dbfilename}.
        @type dbtable: C{basestring}
        """
        # On appelle directement la méthode de PubSub car le __init__
        # de SocketToNodeForwarder essaye d'utiliser un socket UNIX.
        PubSubForwarder.__init__(self, dbfilename, dbtable)
        self._queue = queue

    @defer.inlineCallbacks
    def consumeQueue(self):
        """
        Consomme les messages enregistrés dans la file en vue des les
        transférer sur le bus XMPP.

        Si des messages n'avaient pas pu être transférés (et ont donc été
        stockés dans la base de données locale), alors cette méthode tente
        de les réémettre en priorité.

        Cette méthode boucle jusqu'à ce que la valeur C{None}
        soit lue depuis la file. Le demi-connecteur se déconnecte
        alors du bus XMPP.

        @note: U{http://stackoverflow.com/questions/776631/using-twisteds-twisted-web-classes-how-do-i-flush-my-outgoing-buffers}
        """
        while self.parent is not None:
            # On tente le renvoi d'un message.
            xml = threads.blockingCallFromThread(self.retry.unstore)

            if xml is None:
                try:
                    # Aucun message à renvoyer ?
                    # On récupère un message de la file dans ce cas.
                    xml = self._queue.get()
                except (IOError, OSError), e:
                    if e.errno != errno.EINTR:
                        raise
                    else:
                        continue
                else:
                    if not xml:
                        LOGGER.info(_('Received request to shutdown'))
                        break


            item = parseXml(xml)

            # Ne devrait jamais se produire, mais au cas où...
            if item is None:
                LOGGER.error(_('Item is None in consumeQueue, '
                                'this should never happen!'))
                continue

            threads.blockingCallFromThread(self.forwardMessage, item, source="queue")

        LOGGER.info(_('Stopping QueueToNodeForwarder.'))
        self.disownHandlerParent(None)

    def connectionInitialized(self):
        """
        Cette méthode est appelée lorsque la connexion avec le bus XMPP
        est prête. On se contente d'appeler la méthode L{consumeQueue}
        depuis le reactor de Twisted pour commencer le transfert.
        """

        # On passe l'appel à la méthode dans SocketToNodeForwarder
        # pour éviter une boucle infinie dans sendQueuedMessages().
        PubSubForwarder.connectionInitialized(self)
        reactor.callInThread(self.consumeQueue)

