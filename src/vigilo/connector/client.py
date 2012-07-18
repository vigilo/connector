# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import os, sys
from twisted.internet import reactor, defer, error
from twisted.application import service
from twisted.python import log, failure
from twisted.words.protocols.jabber import xmlstream
from twisted.words.protocols.jabber.sasl import SASLNoAcceptableMechanism, \
                                                SASLAuthError
from twisted.words.protocols.jabber.jid import JID
from wokkel import client
from wokkel.subprotocols import StreamManager

from vigilo.connector.compression import CompressInitiatingInitializer

from vigilo.common.gettext import translate, l_
_ = translate(__name__)



def split_host_port(hostdef):
    """
    Découpe une définition hostname:port en couple (hostname, port)
    @todo: Support IPv6
    """
    hostdef = hostdef.strip()
    if ":" in hostdef:
        host, port = hostdef.split(":")
        port = int(port)
    else:
        host = hostdef
        port = 5222
    return host, port


class VigiloXMPPClient(client.XMPPClient):
    """Client XMPP Vigilo"""

    def __init__(self, jid, password, host=None,
                 require_tls=False, require_compression=False, max_delay=60):
        """
        Initialise le client.
        @param jid: Identifiant Jabber du client.
        @type jid: C{JID}
        @param password: Mot de passe associé au compte Jabber.
        @type password: C{str}
        @param host: le serveur XMPP
        @type host: C{str}
        @param require_tls: Indique si la connexion doit être chiffrée ou non.
        @type require_tls: C{bool}
        @param require_compression: Indique si la connexion doit être
            compressée ou non. Cette option est incompatible avec l'option
            C{require_tls}. Si les deux options sont activées, la connexion
            NE SERA PAS compressée (mais elle sera chiffrée).
        @type require_compression: C{bool}
        @param max_delay: le délai maximum entre chaque tentative de
            reconnexion.
        @type max_delay: C{int}
        """
        # On court-circuite client.XMPPClient qui utilise une factory
        # qui n'a pas le comportement attendu.
        self.jid = jid
        self.domain = jid.host
        self.host = host

        # On utilise notre factory personnalisée, que l'on configure.
        if isinstance(self.host, list):
            factory = VigiloClientFactory(jid, password)
        else:
            factory = client.HybridClientFactory(jid, password)
        factory.maxDelay = max_delay
        StreamManager.__init__(self, factory)

        self.require_tls = require_tls
        self.require_compression = require_compression

    def _connected(self, xs):
        """
        On modifie dynamiquement l'attribut "required" du plugin
        d'authentification TLSInitiatingInitializer créé automatiquement
        par wokkel, pour imposer TLS si l'administrateur le souhaite, et
        insérer la compression zlib.
        """
        from vigilo.common.logging import get_logger
        LOGGER = get_logger(__name__)

        for index, initializer in enumerate(xs.initializers[:]):
            if not isinstance(initializer, xmlstream.TLSInitiatingInitializer):
                continue

            if self.require_tls:
                # Activation du chiffrement par TLS.
                if self.require_compression:
                    # zlib et TLS sont incompatibles, voir XEP-0138.
                    LOGGER.warning(
                        _("'require_compression' cannot be True when "
                        "'require_tls' is also True.")
                        )
                xs.initializers[index].required = True

            elif self.require_compression:
                # On ajoute la compression zlib et on désactive TLS.
                xs.initializers[index].wanted = False
                xs.initializers[index].required = False
                compressor = CompressInitiatingInitializer(xs)
                compressor.required = True
                xs.initializers.insert(index + 1, compressor)

            else:
                # On utilise le chiffrement TLS si disponible,
                # mais on ne force pas son utilisation.
                xs.initializers[index].wanted = True
                xs.initializers[index].required = False

            # Inutile de regarder plus loin.
            break

        client.XMPPClient._connected(self, xs)

    def _disconnected(self, xs):
        """
        Ajout de l'arrêt à la déconnexion
        @TODO: vérifier que ça ne bloque pas la reconnexion automatique.
        """
        client.XMPPClient._disconnected(self, xs)

    def initializationFailed(self, fail):
        """
        Appelé si l'initialisation échoue. Ici, on ajoute la gestion de
        l'erreur d'authentification.
        """
        from vigilo.common.logging import get_logger
        LOGGER = get_logger(__name__)

        tls_errors = {
            xmlstream.TLSFailed:
                l_("Some error occurred while negotiating TLS encryption"),
            xmlstream.TLSRequired:
                l_("The server requires TLS encryption. Use the "
                    "'require_tls' option to enable TLS encryption."),
            xmlstream.TLSNotSupported:
                l_("TLS encryption was required, but pyOpenSSL is "
                    "not installed"),
        }

        if fail.check(SASLNoAcceptableMechanism, SASLAuthError):
            LOGGER.error(_("Authentication failure: %s"),
                         fail.getErrorMessage())
            try:
                reactor.stop()
            except error.ReactorNotRunning:
                pass
            return

        if fail.check(xmlstream.FeatureNotAdvertized):
            # Le nom de la fonctionnalité non-supportée n'est pas transmis
            # avec l'erreur. On calcule le différentiel entre ce qu'on a
            # demandé et ce qu'on a obtenu pour trouver son nom.
            for initializer in self.xmlstream.initializers:
                if not isinstance(initializer, \
                    xmlstream.BaseFeatureInitiatingInitializer):
                    continue

                if initializer.required and \
                    initializer.feature not in self.xmlstream.features:
                    LOGGER.error(_("The server does not support "
                                    "the '%s' feature"),
                                    initializer.feature[1])
            # Ça peut être une erreur temporaire du serveur (ejabberd fait ça
            # des fois sous forte charge), donc on ré-essaye.
            self._connection.disconnect()
            #try:
            #    reactor.stop()
            #except error.ReactorNotRunning:
            #    pass
            return

        # S'il s'agit d'une erreur liée à TLS autre le manque de support
        # par le serveur, on affiche un message traduit pour aider à la
        # résolution du problème.
        tls_error = fail.check(*tls_errors.keys())
        if tls_error:
            LOGGER.error(_(tls_errors[tls_error]))

        client.XMPPClient.initializationFailed(self, fail)

    def stopService(self):
        client.XMPPClient.stopService(self)
        stops = []
        for e in self:
            if not hasattr(e, "stop"):
                continue
            d = e.stop()
            if d is not None:
                stops.append(d)
        return defer.DeferredList(stops)

    def _getConnection(self):
        if self.host:
            if isinstance(self.host, list):
                hosts = [ split_host_port(h) for h in self.host ]
                c = MultipleServerConnector(hosts, self.factory,
                                            reactor=reactor)
                c.connect()
                return c
            else:
                host, port = split_host_port(self.host)
                return reactor.connectTCP(host, port, self.factory)
        else:
            c = client.XMPPClientConnector(reactor, self.domain, self.factory)
            c.connect()
            return c


def client_factory(settings):
    from vigilo.pubsub.checknode import VerificationNode

    try:
        require_tls = settings['bus'].as_bool('require_tls')
    except KeyError:
        require_tls = False
    try:
        require_compression = settings['bus'].as_bool('require_compression')
    except KeyError:
        require_compression = False

    # Temps max entre 2 tentatives de connexion (par défaut 1 min)
    max_delay = int(settings["bus"].get("max_reconnect_delay", 60))

    host = settings['bus'].get('host')
    if host is not None:
        host = host.strip()
        if " " in host:
            host = [ h.strip() for h in host.split(" ") ]

    xmpp_client = VigiloXMPPClient(
            JID(settings['bus']['jid']),
            settings['bus']['password'],
            host,
            require_tls=require_tls,
            require_compression=require_compression,
            max_delay=max_delay)
    xmpp_client.setName('xmpp_client')

    try:
        xmpp_client.logTraffic = settings['bus'].as_bool('log_traffic')
    except KeyError:
        xmpp_client.logTraffic = False

    try:
        subscriptions = settings['bus'].as_list('subscriptions')
    except KeyError:
        try:
            # Pour la rétro-compatibilité.
            subscriptions = settings['bus'].as_list('watched_topics')
            import warnings
            warnings.warn(DeprecationWarning(_(
                'The "watched_topics" option has now been renamed into '
                '"subscriptions". Please update your configuration file.'
            )))
        except KeyError:
            subscriptions = []

    node_verifier = VerificationNode(subscriptions, doThings=True)
    node_verifier.setHandlerParent(xmpp_client)
    return xmpp_client


from twisted.internet import tcp
class MultipleServerConnector(tcp.Connector):
    def __init__(self, hosts, factory, timeout=30, attempts=3,
                 reactor=None):
        """
        @param hosts: Liste de tuple de la forme (nom d'hôte, port)
            contenant la liste des serveurs auxquels ce client peut se
            connecter. En cas d'indisponibilité de l'un de ces serveurs,
            le serveur suivant dans la liste est utilisé.
        @type hosts: C{list}
        @param factory: Une factory pour le connecteur Twisted.
        @type factory: L{twisted.internet.interfaces.IProtocolFactory}
        @param timeout: Le timeout de connexion.
        @type timeout: C{int}
        @param attempts: Le nombre de tentative de connexion.
        @type attempts: C{int}
        @param reactor: Une instance d'un réacteur de Twisted.
        @type reactor: L{twisted.internet.reactor}
        """
        tcp.Connector.__init__(self, None, None, factory, timeout, None,
                               reactor=reactor)
        self.hosts = hosts
        self.attempts = attempts
        self._attemptsLeft = attempts
        self._usableHosts = None

    def pickServer(self):
        if not self._usableHosts:
            self._usableHosts = self.hosts[:]
        self.host, self.port = self._usableHosts[0]
        log.msg("Connecting to %s:%s" % (self.host, self.port))

    def connectionFailed(self, reason):
        from vigilo.common.logging import get_logger
        LOGGER = get_logger(__name__)

        assert self._attemptsLeft is not None
        self._attemptsLeft -= 1
        if self._attemptsLeft == 0:
            LOGGER.warning(_("Server %(oldserver)s did not answer after "
                    "%(attempts)d attempts"),
                    {"oldserver": self.host, "attempts": self.attempts})
            self._usableHosts.remove((self.host, self.port))
            self.resetAttempts()
            if hasattr(self.factory, "resetDelay"):
                self.factory.resetDelay()
        return tcp.Connector.connectionFailed(self, reason)

    def resetAttempts(self):
        self._attemptsLeft = self.attempts

    def _makeTransport(self):
        self.pickServer()
        return tcp.Connector._makeTransport(self)


class MultipleServersXmlStreamFactory(xmlstream.XmlStreamFactory):
    """
    Sous-classée pour ré-initialiser les tentatives de connexions du connector
    lorsqu'une tentative réussit.
    """

    def buildProtocol(self, addr): # pylint: disable-msg=E0202
        """
        Ré-initialise les tentatives de connexions d'un
        L{MultipleServerConnector} lorsque l'une d'entre elles réussit.
        @param addr: an object implementing
            C{twisted.internet.interfaces.IAddress}
        """
        if (self.connector is not None
                and hasattr(self.connector, "resetAttempts")):
            self.connector.resetAttempts()
        return xmlstream.XmlStreamFactory.buildProtocol(self, addr)


from wokkel.client import HybridAuthenticator
def VigiloClientFactory(jid, password):
    """Factory pour utiliser L{MultipleServersXmlStreamFactory}"""
    a = HybridAuthenticator(jid, password)
    return MultipleServersXmlStreamFactory(a)


class DeferredMaybeTLSClientFactory(client.DeferredClientFactory):
    """
    Factory asynchrone de clients XMPP de type "one-shot",
    capable de chiffrer la connexion avec le serveur.
    """

    def __init__(self, jid, password, require_tls):
        """
        Initialiseur de la classe.

        @param jid: Identifiant Jabber du connecteur.
        @type jid: C{str}
        @param password: Mot de passe du compteur Jabber du connecteur.
        @type password: C{str}
        @param require_tls: Indique si la connexion doit être chiffrée
            (en utilisant le protocole TLS) ou non.
        @type require_tls: C{bool}
        """
        super(DeferredMaybeTLSClientFactory, self).__init__(jid, password)
        self.addBootstrap(xmlstream.STREAM_CONNECTED_EVENT, self._connected)
        self.require_tls = require_tls

    def _connected(self, xs):
        """
        On modifie dynamiquement l'attribut "required" du plugin
        d'authentification TLSInitiatingInitializer créé automatiquement
        par wokkel, pour imposer TLS si l'administrateur le souhaite.
        """
        for initializer in xs.initializers:
            if isinstance(initializer, xmlstream.TLSInitiatingInitializer):
                initializer.required = self.require_tls

class OneShotClient(object):
    def __init__(self, jid, password, host, service, lock_file, timeout,
                 require_tls, require_compression):
        """
        Prépare un client XMPP qui ne servira qu'une seule fois (one-shot).

        @param jid: Identifiant Jabber du client.
        @type  jid: C{JID}
        @param password: Mot de passe associé au compte Jabber.
        @type  password: C{str}
        @param host: le hostname du serveur XMPP (si besoin, spécifier le port
            après des deux-points)
        @type  host: C{str}
        @param service: Service de publication à utiliser.
        @type  service: C{JID}
        @param lock_file: Emplacement du fichier de verrou à créer pour
            empêcher l'exécution simultanée de plusieurs instances du
            connecteur.
        @type  lock_file: C{str}
        @param timeout: Durée maximale d'exécution du connecteur,
            afin d'éviter des connecteurs "fous".
        @type  timeout: C{int}
        @param require_tls: Indique si la connexion doit être chiffrée ou non.
        @type  require_tls: C{bool}
        @param require_compression: Indique si la connexion doit être
            compressée ou non. Cette option est incompatible avec l'option
            C{require_tls}. Si les deux options sont activées, la connexion
            NE SERA PAS compressée (mais elle sera chiffrée).
        @type  require_compression: C{bool}
        """
        from vigilo.common.logging import get_logger
        self._logger = get_logger(__name__)
        self._jid = jid
        self._password = password
        self._host = host
        self._service = service
        self._lock_file = lock_file
        self._timeout = timeout
        self._require_tls = require_tls
        self._require_compression = require_compression
        self._result = 0
        self._func = None
        self._args = ()
        self._kwargs = {}

    def _create_lockfile(self):
        """
        Cette fonction vérifie si une autre instance du connecteur est déjà
        en cours d'exécution, et arrête le connecteur si c'est le cas.
        Dans le cas contraire, elle crée un nouveau fichier de lock.

        @return: Code de retour (0 en cas de succès, une autre valeur en cas
            d'erreur).
        @rtype: C{int}
        """
        self._logger.debug(_("Creating lock file in %s"), self._lock_file)

        # Si un fichier de lock existe et qu'une autre
        # instance du connecteur est lancée, on quitte
        if os.path.isfile(self._lock_file):
            try:
                f = open(self._lock_file)
                pid = f.read()
                f.close()
            except Exception, e:
                self._logger.error(_(
                    "Found a lock file, but the following "
                    "exception was raised when trying to "
                    "open it: %s. Cowardly exiting..."),
                    e
                )
                return 1
            if os.path.exists('/proc/' + str(pid)):
                self._logger.error(_(
                    "Another instance of this connector "
                    "is already running (PID: %s). Exiting..."),
                    pid
                )
                return 1
            # Sinon, si un fichier de lock existe mais qu'aucune autre
            # instance du connecteur n'est lancée, on supprime le fichier
            self._logger.warning(_(
                "Found a lock file, but no process is "
                "running with this PID (%s). Removing it..."),
                pid
            )
            try:
                os.remove(self._lock_file)
            except:
                pass

        # Création d'un nouveau fichier de lock
        try:
            f = open(self._lock_file, 'w')
            f.write(str(os.getpid()))
            f.close()
        except Exception, e:
            self._logger.error(_(
                "The following exception was raised when "
                "trying to create the lock file: %s. "
                "Cowardly exiting..."),
                e
            )
            return 1

        self._logger.debug(
            _("Lock file successfully created in %s"),
            self._lock_file
        )
        return 0

    def _stop(self, result, code, stream=None):
        """
        Arrête proprement le connecteur, en supprimant le fichier de
        lock et en affichant un message d'erreur en cas de timeout.
        """
        try:
            self._logger.debug(_("Removing lock file (%s)"), self._lock_file)
            os.remove(self._lock_file)
        except:
            pass

        if isinstance(result, failure.Failure):
            tls_errors = {
                xmlstream.TLSFailed:
                    l_("Some error occurred while negotiating TLS encryption"),
                xmlstream.TLSRequired:
                    l_("The server requires TLS encryption. Use the "
                        "'require_tls' option to enable TLS encryption."),
                xmlstream.TLSNotSupported:
                    l_("TLS encryption was required, but pyOpenSSL is "
                        "not installed"),
            }

            if result.check(defer.TimeoutError):
                self._logger.error(_("Timeout"))

            elif result.check(SASLNoAcceptableMechanism, SASLAuthError):
                self._logger.error(_("Authentication failed: %s"),
                                result.getErrorMessage())

            elif result.check(xmlstream.FeatureNotAdvertized):
                # Le nom de la fonctionnalité non-supportée n'est pas transmis
                # avec l'erreur. On calcule le différentiel entre ce qu'on a
                # demandé et ce qu'on a obtenu pour trouver son nom.
                for initializer in stream.initializers:
                    if not isinstance(initializer, \
                        xmlstream.BaseFeatureInitiatingInitializer):
                        continue

                    if initializer.required and \
                        initializer.feature not in stream.features:
                        self._logger.error(_("The server does not support "
                                            "the '%s' feature"),
                                            initializer.feature[1])

            else:
                # S'il s'agit d'une erreur liée à TLS autre le manque de support
                # par le serveur, on affiche un message traduit pour aider à la
                # résolution du problème.
                tls_error = result.check(*tls_errors.keys())
                if tls_error:
                    self._logger.error(_(tls_errors[tls_error]))

                # Message générique pour signaler l'erreur
                else:
                    self._logger.error(
                        _("Error: %(message)s (%(type)r)"), {
                            'message': result.getErrorMessage(),
                            'type': str(result),
                        }
                    )
        else:
            self._logger.debug(_("Exiting with no error"))

        self._result = code
        reactor.stop()
        return result

    def setHandler(self, func, *args, **kwargs):
        """
        @param func: Configure la fonction à exécuter pour déclencher
            les traitements de ce connecteur.
        @type func: C{callable}
        @note: Les paramètres supplémentaires (nommés ou non) passés
            à cette méthode seront transmis à L{func} lors de son appel.
        """
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self, log_traffic=False, app_name='XMPP client'):
        """
        Fait fonctionner le connecteur (connexion, traitement, déconnexion).

        @param log_traffic: Indique si le trafic échangé avec le serveur
            XMPP doit être journalisé ou non.
        @type log_traffic: C{bool}
        @param app_name: Nom à donner au client (peut aider au débogage).
        @type app_name: C{str}
        @return: Code de retour de l'exécution du connecteur.
            La valeur 0 est renvoyée lorsque le connecteur a fini son
            exécution normalement. Toute autre valeur signale une erreur.
        @rtype: C{int}
        """
        # Importé ici car sinon on importe implicitement
        # vigilo.pubsub(.__init__) qui utilise des loggers
        # non initialisés (ce qui génère des avertissements
        # et empêche l'affichage des vrais logs).
        from vigilo.pubsub.ipv6 import ipv6_compatible_udp_port

        self._result = self._create_lockfile()

        # Si la création du fichier de verrou renvoie une erreur,
        # on propage celle-ci.
        if self._result:
            return self._result

        # Création de la factory pour le client XMPP.
        service.Application(app_name)
        factory = DeferredMaybeTLSClientFactory(
            self._jid,
            self._password,
            self._require_tls,
        )
        factory.streamManager.logTraffic = bool(log_traffic)

        # Monkey-patch la classe twisted.internet.udp.Port
        # pour utiliser une implémentation compatible IPv6.
        ipv6_compatible_udp_port()

        # Création du client XMPP et ajout de la fonction de traitement.
        if self._host:
            host, port = split_host_port(self._host)
            reactor.connectTCP(host, port, factory)
            d = factory.deferred
        else:
            d = client.clientCreator(factory)

        if self._func:
            d.addCallback(
                self._func,
                self._service,
                *self._args,
                **self._kwargs
            )
        else:
            self._logger.warning(_("No handler registered for this "
                                    "one-shot XMPP client"))

        d.addErrback(lambda fail: self._stop(
            fail,
            code=1,
            stream=factory.streamManager.xmlstream
        ))

        # Déconnecte le client du bus XMPP.
        d.addCallback(lambda _dummy: factory.streamManager.xmlstream.sendFooter())
        d.addCallback(self._stop, code=0)
        d.addErrback(lambda _dummy: None)

        # Garde-fou : on limite la durée de vie du connecteur.
        reactor.callLater(
            self._timeout,
            self._stop,
            result=failure.Failure(defer.TimeoutError()),
            code=3
        )
        reactor.run()
        return self._result

def oneshotclient_factory(settings):
    try:
        require_tls = settings['bus'].as_bool('require_tls')
    except KeyError:
        require_tls = False
    #try:
    #    require_compression = settings['bus'].as_bool('require_compression')
    #except KeyError:
    #    require_compression = False
    require_compression=False, # require_compression : pas supporté pour le moment.

    xmpp_client = OneShotClient(
            jid=JID(settings['bus']['jid']),
            password=settings['bus']['password'],
            host=settings['bus'].get('host'),
            service=JID(settings['bus'].get('service', "pubsub.localhost")),
            lock_file=settings['connector']['lock_file'],
            timeout=int(settings['connector'].get('timeout', 30)),
            require_tls=require_tls,
            require_compression=require_compression,
            )

    try:
        xmpp_client.logTraffic = settings['bus'].as_bool('log_traffic')
    except KeyError:
        xmpp_client.logTraffic = False

    return xmpp_client
