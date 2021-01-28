# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2021 CS GROUP - France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Bibliothèque de fonctions/classes pour faciliter le support
de SSL/TLS dans un connecteur.
"""

# pylint: disable-msg=W0611
# Unused import ...
# (ce module importe les noms issues de twisted.internet.ssl pour
# assurer la compatibilité avec ce dernier)

from __future__ import absolute_import

from OpenSSL import SSL, crypto
from OpenSSL.SSL import Error
from twisted.internet.ssl import CertificateOptions as CertOptions
from twisted.internet.ssl import PrivateCertificate as PrivateCert

# On importe les autres symboles du module ssl de Twisted,
# ce qui évite au script nous important d'avoir à importer aussi t.i.ssl.
from twisted.internet.ssl import (
    ContextFactory,
    ClientContextFactory,
    DistinguishedName,
    DN,
    Certificate,
    CertificateRequest,
    KeyPair,
)

from vigilo.common.gettext import translate
from vigilo.common.logging import get_logger

LOGGER = get_logger(__name__)
_ = translate(__name__)


__all__ = [
    "ContextFactory", "ClientContextFactory",
    'DistinguishedName', 'DN',
    'Certificate', 'CertificateRequest', 'PrivateCertificate',
    'KeyPair',
    'CertificateOptions',
    'Error',
]

class CertificateOptions(CertOptions):
    """
    Surcharge la classe C{t.i.ssl.CertificateOptions} de Twisted afin de
    permettre la validation du champ CN du certificat qui nous est présenté.
    """
    def __init__(self, *args, **kwargs):
        self._hostname = kwargs.get('hostname')
        super(CertificateOptions, self).__init__(*args, **kwargs)

    def setHostname(self, hostname):
        """
        Positionne le nom d'hôte auquel on est en train de se connecter.
        """
        self._hostname = hostname

    def getContext(self):
        """
        Retourne un contexte SSL.
        """
        if self._context is None:
            self._context = self._makeContext()
            self._context.set_verify(self._context.get_verify_mode(),
                                     self._verify)
        return self._context

    def _verify(self, conn, cert, errno, depth, preverify_ok):
        """
        Remplace la fonction de validation par défaut des certificats
        de Twisted. Cette version vérifie que le CN du certificat présenté
        correspond bien au nom de la machine à laquelle on s'est connecté.
        """
        cn = cert.get_subject().commonName
        hostname = self._hostname

        if not preverify_ok:
            return False

        if hostname is None:
            return True

        # @TODO: champs subjectAltName, pas encore supportés par pyOpenSSL.

        # Adresses IPv4.
        if hostname.lstrip('1234567890.') == "":
            return True # Pas de validation sur les IPs.

        # Wildcards.
        if cn.startswith('*.'):
            cn = cn[2:]
            hostname = hostname.partition('.')[2]

        if cn != hostname:
            LOGGER.warning(_('Machine hostname (%(hostname)s) does not match '
                             'certificate CommonName (%(cn)s)') % {
                                'hostname': self._hostname,
                                'cn': cert.get_subject().commonName,
                             })
        return True


class PrivateCertificate(PrivateCert):
    """
    Surcharge la classe C{t.i.ssl.PrivateCertificate} de Twisted afin
    d'utiliser la classe L{CertificateOptions} de Vigilo pour créer
    le contexte SSL en lieu et place de celle fournie par Twisted.
    """
    _certOptionsFactory = CertificateOptions

    def options(self, *authorities):
        """
        Retourne un objet contenant les options qui s'appliqueront
        au contexte SSL de la connexion.

        @param authorities: Une liste optionnelle de certificats
            d'autorités de confiance. Si cette liste n'est pas vide,
            alors le certificat qui nous est présenté sera validé
            pour vérifier qu'il provient bien de l'une de ces autorités.
        @type authorities: C{list}
        """
        options = dict(privateKey=self.privateKey.original,
                       certificate=self.original)
        if authorities:
            options.update(dict(verify=True,
                                requireCertificate=True,
                                caCerts=[auth.original for auth in authorities]))
        return self._certOptionsFactory(**options)


def certoptions_factory(cert_file=None, cert_key=None, cert_ca=None):
    """
    Factory pour un gestionnaire de paramètre de contextes SSL.

    @param cert_file: Emplacement du fichier du certificat client à présenter
        au serveur lors de la connexion, si souhaité.
    @type cert_file: C{str}
    @param cert_key: Emplacement de la clé privée correspondant au certificat
        spécifié par le paramètre C{cert_file} si celui-ci ne contient pas
        déjà la clé privée.
    @type cert_key: C{str}
    @param cert_ca: Liste des emplacements des certificats des autorités
        de confiance.
    @type cert_ca: C{list}
    @return: Instance contenant les réglages qui seront appliqués
        lors de la création du contexte SSL.
    @rtype: L{CertificateOptions}
    """
    # Construction des objets associés à la gestion des certificats.
    # Tout d'abord, est-ce qu'on a un certificat client ?
    if cert_file:
        if cert_key:
            # Le certificat et la clé privée sont
            # dans 2 fichiers distincts.
            cert_handle = file(cert_file, 'r')
            pkey_handle = file(cert_key, 'r')
            try:
                cert = PrivateCertificate.fromCertificateAndKeyPair(
                    Certificate.loadPEM(cert_handle.read()),
                    KeyPair.load(
                        pkey_handle.read(),
                        crypto.FILETYPE_PEM
                    )
                )
            finally:
                cert_handle.close()
                pkey_handle.close()
        else:
            # Le fichier contient à la fois
            # le certificat et sa clé privée.
            cert_handle = file(cert_file, 'r')
            try:
                cert = PrivateCertificate.loadPEM(
                            cert_handle.read())
            finally:
                cert_handle.close()

    # Construction de la liste des CA de confiance.
    cert_ca_objects = []
    if cert_ca:
        # Une ou plusieurs CA ont été données en paramètre.
        for ca in cert_ca:
            ca_handle = file(ca, 'r')
            try:
                cert_ca_objects.append(Certificate.loadPEM(
                                        ca_handle.read()))
            finally:
                ca_handle.close()

    # Application des CA au certificat client.
    if cert_file:
        return cert.options(*cert_ca_objects)

    # Ou création d'un contexte qui ne valide le certificat du serveur
    # que si des CA ont été spécifiées.
    return CertificateOptions(
        method=SSL.SSLv23_METHOD, # SSLv2, SSLv3 ou TLSv1.
        verify=bool(cert_ca_objects), # Uniquement s'il y a des CAs.
        caCerts=[auth.original for auth in cert_ca_objects],
        requireCertificate=True,
    )
