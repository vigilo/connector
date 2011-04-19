# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Ce module est un demi-connecteur qui assure la redirection des messages
issus du bus XMPP vers une file d'attente (C{Queue.Queue} ou compatible).
"""

import Queue
import errno

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate
from vigilo.connector.forwarder import PubSubListener

LOGGER = get_logger(__name__)
_ = translate(__name__)

class NodeToQueueForwarder(PubSubListener):
    """
    Cette classe redirige les messages reçus depuis le bus XMPP
    vers une file d'attente compatible avec C{Queue.Queue}.
    """

    def __init__(self, queue, dbfilename=None, dbtable=None):
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
        super(NodeToQueueForwarder, self).__init__(dbfilename, dbtable)
        self.__queue = queue

    def isConnected(self):
        return not self.__queue.full()

    def processMessage(self, xml):
        """
        Transfère un message XML (non sérialisé) vers la file.
        @param xml: message XML à transférer.
        @type xml: C{str}
        """
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

