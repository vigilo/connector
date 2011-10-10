Connexion au serveur XMPP
-------------------------
Le connecteur utilise un bus de communication basé sur le protocole
:term:`XMPP` pour communiquer avec les autres connecteurs de Vigilo.

Ce chapitre décrit les différentes options de configuration se rapportant à la
connexion à ce bus de communication, situées dans la section ``[bus]`` du
fichier de configuration.

Trace des messages
^^^^^^^^^^^^^^^^^^
L'option « log_traffic » est un booléen permettant d'afficher tous les messages
échangés avec le bus XMPP lorsqu'il est positionné à « True ». Cette option
génère un volume d'événements de journalisation très important et n'est donc
pas conseillée en production.

Adresse du bus
^^^^^^^^^^^^^^
L'option « host » permet d'indiquer le nom ou l'adresse IP de l'hôte sur lequel
le bus XMPP fonctionne.

Service de publication
^^^^^^^^^^^^^^^^^^^^^^
Le connecteur utilise le protocole de publication de messages décrit dans le
document XEP-0060 pour échanger des informations avec les autres connecteurs de
Vigilo.

Ce protocole nécessite de spécifier le nom du service de publication utilisé
pour l'échange de messages sur le bus XMPP. Ce nom de service est généralement
de la forme ``pubsub.<hôte>`` où ``<hôte>`` correspond au nom de l'hôte sur
lequel ejabberd fonctionne (indiqué par l'option « host »).

Identifiant XMPP
^^^^^^^^^^^^^^^^
Chaque connecteur de Vigilo est associé à un compte Jabber différent et possède
donc son propre JID. L'option « jid » permet d'indiquer le JID à utiliser pour
se connecter au serveur Jabber.

Mot de passe XMPP
^^^^^^^^^^^^^^^^^
L'option « password » permet de spécifier le mot de passe associé au compte
Jabber indiqué dans l'option « jid ».

Connexions sécurisées
^^^^^^^^^^^^^^^^^^^^^
Les connecteurs ont la possibilité de spécifier la politique de sécurité à
appliquer pour les connexions avec le serveurs XMPP. Il est possible de forcer
l'utilisation d'une connexion chiffrée entre le connecteur et le bus en
positionnant l'option « require_tls » à « True ». Une erreur sera levée si le
connecteur ne parvient pas à établir une connexion chiffrée.

Lorsque cette option est positionnée à une autre valeur, le connecteur tente
malgré tout d'établir une connexion chiffrée. Si cela est impossible, le
connecteur ne déclenche pas d'erreur mais bascule automatiquement vers
l'utilisation d'une connexion en clair au bus XMPP.

Compression des données
^^^^^^^^^^^^^^^^^^^^^^^
Les connecteurs ont la possibilité de spécifier si les échanges XMPP seront
compressés. Il est possible de forcer l'utilisation de la compression entre le
connecteur et le bus en positionnant l'option « require_compression » à
« True ». Une erreur est levée si le connecteur ne parvient pas à mettre en
place la compression lors des premiers échanges.

Lorsque les deux options « require_tls » et « require_compression » sont à
« True », un message d'avertissement est inscrit dans les fichiers de log, et
le connecteur utilisera le chiffrement.

Délai maximum de reconnexion
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

En cas de déconnexion du bus XMPP, les connecteurs se reconnectent
automatiquement, selon un délai qui augmente exponentiellement (afin d'éviter
d'innonder les journaux système avec des messages annonçant la reconnexion).

L'option « max_reconnect_delay » permet d'indiquer le délai maximum (en
secondes) qui peut s'écouler entre 2 tentatives de reconnexion.
Par défaut, ce délai est fixé à 60 secondes.

Abonnements
^^^^^^^^^^^
L'option « subscriptions » contient la liste des nœuds XMPP auxquels le
connecteur est abonné (séparés par des virgules), c'est-à-dire les nœuds pour
lesquels il recevra des messages lorsqu'un autre composant de Vigilo publie des
données. La valeur proposée par défaut lors de l'installation du connecteur
convient généralement à tous les types d'usages.

La valeur spéciale « , » (une virgule seule) permet d'indiquer que le
connecteur n'est abonné à aucun nœud (par exemple, dans le cas où le connecteur
se contente d'écrire des informations sur le bus, sans jamais en recevoir).

État du connecteur
^^^^^^^^^^^^^^^^^^
Les connecteurs de Vigilo sont capables de s'auto-superviser, c'est-à-dire que
des alertes peuvent être émises par Vigilo concernant ses propres connecteurs
lorsque le fonctionnement de ceux-ci est perturbé ou en défaut.

Ce mécanisme est rendu possible grâce à des signaux de vie émis par les
connecteurs à intervalle régulier. Chaque signal de vie correspond à un message
de type « state ».

L'option « status_node » permet de choisir le nœud XMPP vers lequel les
messages de survie du connecteur sont envoyés. Dans le cas où cette option ne
serait pas renseignée, les nœuds de publication sont utilisés pour déterminer
le nœud de destination des messages. Si aucun nœud de publication n'est trouvé
pour l'envoi des messages de vie, un message d'erreur est enregistré dans les
journaux d'événements.


Associations de publication
---------------------------
Le connecteur envoie des messages au bus XMPP contenant des informations sur
l'état des éléments du parc, ainsi que des données de métrologie permettant
d'évaluer la performance des équipements. Chaque message transmis par le
connecteur possède un type.

La section ``[publications]`` permet d'associer le type des messages à un nœud
de publication. Ainsi, chaque fois qu'un message XML doit être transmis au bus,
le connecteur consulte cette liste d'associations afin de connaître le nom du
nœud XMPP sur lequel il doit publier son message.

Les types de messages supportés par un connecteur sont :

* ``perf`` : messages de performances
* ``state`` : messages d'état
* ``event`` : messages d'événements
* ``command`` : commandes Nagios

La configuration proposée par défaut lors de l'installation du
connecteur associe chacun de ces types avec un nœud descendant de « /vigilo/ »
portant le même que le type.

Exemple de configuration possible, correspondant à une installation standard::

    [publications]
    perf    = /vigilo/perf
    state   = /vigilo/state
    event   = /vigilo/event
    command = /vigilo/command


.. _logging:

Journaux
--------
Le connecteur est capable de transmettre un certain nombre d'informations au
cours de son fonctionnement à un mécanisme de journalisation des événements
(par exemple, des journaux systèmes, une trace dans un fichier, un
enregistrement des événements en base de données, etc.).

Le document Vigilo - Journaux d'événements décrit spécifiquement la
configuration de la journalisation des événements au sein de toutes les
applications de Vigilo, y compris les connecteurs.


