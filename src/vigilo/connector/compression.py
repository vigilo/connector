# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Gestion de compression zlib dans la connexion au bus XMPP (XEP-0138)

Très lourdement inspiré de l'initialisation TLS dans twisted. Proposé pour
évaluation sur la liste twisted-jabber:
U{http://www.mail-archive.com/twisted-jabber@ik.nu/msg00330.html}
(et re-modifié depuis).
"""

import zlib
import socket

from twisted.internet import defer, main
from twisted.internet.tcp import Connection, EWOULDBLOCK
from twisted.words.protocols.jabber.xmlstream import BaseFeatureInitiatingInitializer, Reset
from twisted.words.xish import domish

from twisted.python import log
from twisted.words.protocols.jabber import xmlstream


NS_XMPP_FEATURE_COMPRESS = "http://jabber.org/features/compress"
NS_XMPP_COMPRESS = "http://jabber.org/protocol/compress"


def _getCompressClass(klass, _existing={}):
    if klass not in _existing:
        class CompressedConnection(_CompressedMixin, klass):
            pass
        _existing[klass] = CompressedConnection
    return _existing[klass]

class _CompressedMixin(object):
    """
    Surchargement des méthodes de lecture et d'écriture pour introduire la
    compression zlib. Pour l'utilisation de la biblio zlib, inspiré de
    U{http://www.doughellmann.com/PyMOTW/zlib/}.
    """

    _compressor = None
    _decompressor = None

    def write(self, data):
        if not data:
            return
        if self._compressor is None:
            self._compressor = zlib.compressobj()
        compressed = self._compressor.compress(data)
        syncdata = self._compressor.flush(zlib.Z_SYNC_FLUSH)
        compressed += syncdata
        try:
            Connection.write(self, compressed)
        except zlib.error, e:
            print e
            raise

    def doRead(self):
        if self._decompressor is None:
            self._decompressor = zlib.decompressobj()
        try:
            data = self.socket.recv(self.bufferSize)
        except socket.error, se:
            if se.args[0] == EWOULDBLOCK:
                return
            else:
                return main.CONNECTION_LOST
        if not data:
            remainder = self._decompressor.flush()
            if remainder:
                return self.protocol.dataReceived(remainder)
            return main.CONNECTION_DONE
        to_decompress = self._decompressor.unconsumed_tail + data
        decompressed = self._decompressor.decompress(to_decompress)
        return self.protocol.dataReceived(decompressed)


class CompressError(Exception):
    """Compress base exception."""
class CompressFailed(CompressError):
    """Exception indicating failed Compress negotiation"""


class CompressInitiatingInitializer(BaseFeatureInitiatingInitializer):
    """
    Détecte la fonctionnalité quand elle est proposée par le bus, et active la
    compression en conséquence
    """

    feature = (NS_XMPP_FEATURE_COMPRESS, 'compression')
    wanted = True
    _deferred = None

    def onProceed(self, obj):
        self.xmlstream.removeObserver('/failure', self.onFailure)
        self.xmlstream.transport.__class__ = \
                _getCompressClass(self.xmlstream.transport.__class__)
        self.xmlstream.reset()
        self.xmlstream.sendHeader()
        self._deferred.callback(Reset)

    def onFailure(self, obj):
        self.xmlstream.removeObserver('/compressed', self.onProceed)
        self._deferred.errback(CompressFailed())

    def start(self):
        if not self.wanted:
            return defer.succeed(None)
        allowed_methods = [ str(m) for m in
                            self.xmlstream.features[self.feature].elements() ]
        if "zlib" not in allowed_methods:
            return defer.succeed(None)
        self._deferred = defer.Deferred()
        self.xmlstream.addOnetimeObserver("/compressed", self.onProceed)
        self.xmlstream.addOnetimeObserver("/failure", self.onFailure)
        element = domish.Element((NS_XMPP_COMPRESS, "compress"))
        element.addElement("method", None, content="zlib")
        self.xmlstream.send(element)
        return self._deferred

