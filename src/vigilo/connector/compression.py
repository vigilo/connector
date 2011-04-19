# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Gestion de compression zlib dans la connexion au bus XMPP (XEP-0138)

Ce code a été proposé pour inclusion dans Twisted:
http://www.mail-archive.com/twisted-jabber@ik.nu/msg00334.html
"""

import zlib

from twisted.internet import defer
from twisted.protocols.policies import ProtocolWrapper
from twisted.words.xish import domish
from twisted.words.protocols.jabber import xmlstream


NS_XMPP_FEATURE_COMPRESS = "http://jabber.org/features/compress"
NS_XMPP_COMPRESS = "http://jabber.org/protocol/compress"


class CompressedTransport(ProtocolWrapper):
    """
    Surchargement des méthodes de lecture et d'écriture pour introduire la
    compression zlib. Pour l'utilisation de la biblio zlib, inspiré de
    U{http://www.doughellmann.com/PyMOTW/zlib/}.
    """

    def __init__(self, wrappedProtocol):
        ProtocolWrapper.__init__(self, None, wrappedProtocol)
        self._compressor = zlib.compressobj()
        self._decompressor = zlib.decompressobj()

    def makeConnection(self, transport):
        ProtocolWrapper.makeConnection(self, transport)
        transport.protocol = self

    def write(self, data):
        if not data:
            return
        # Contournement de https://support.process-one.net/browse/EJAB-1397
        if len(data) % 7168 == 0:
            data = data + "<!-- -->"
        compressed = self._compressor.compress(data)
        compressed += self._compressor.flush(zlib.Z_SYNC_FLUSH)
        self.transport.write(compressed)

    def writeSequence(self, dataSequence):
        if not dataSequence:
            return
        compressed = [ self._compressor.compress(data)
                       for data in dataSequence ]
        compressed.append(self._compressor.flush(zlib.Z_SYNC_FLUSH))
        self.transport.writeSequence(compressed)

    def dataReceived(self, data):
        to_decompress = self._decompressor.unconsumed_tail + data
        decompressed = self._decompressor.decompress(to_decompress)
        self.wrappedProtocol.dataReceived(decompressed)

    def connectionMade(self):
        self.wrappedProtocol.makeConnection(self)

    def connectionLost(self, reason):
        self.dataReceived(self._decompressor.flush())
        self.wrappedProtocol.connectionLost(reason)


class CompressError(Exception):
    """Compress base exception."""

class CompressFailed(CompressError):
    """Exception indicating failed Compress negotiation"""


class CompressInitiatingInitializer(xmlstream.BaseFeatureInitiatingInitializer):
    """
    Détecte la fonctionnalité quand elle est proposée par le bus, et active la
    compression en conséquence
    """

    feature = (NS_XMPP_FEATURE_COMPRESS, 'compression')
    wanted = True
    _deferred = None

    def onProceed(self, obj):
        self.xmlstream.removeObserver('/failure', self.onFailure)
        compressedTransport = CompressedTransport(self.xmlstream)
        compressedTransport.makeConnection(self.xmlstream.transport)
        self._deferred.callback(xmlstream.Reset)

    def onFailure(self, obj):
        self.xmlstream.removeObserver('/compressed', self.onProceed)
        self._deferred.errback(CompressFailed())

    def start(self):
        if not self.wanted:
            return defer.succeed(None)
        if self.xmlstream.transport.TLS:
            # TLS and stream compression are mutually exclusive: XEP-0138 says
            # that compression may be offered if TLS failed.
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

