Connexion au bus de messages
----------------------------
Le connecteur utilise un bus de communication basé sur le protocole
:term:`AMQP` pour communiquer avec les autres connecteurs de Vigilo.

Ce chapitre décrit les différentes options de configuration se rapportant à la
connexion à ce bus de communication, situées dans la section ``[bus]`` du
fichier de configuration.

Trace des messages
^^^^^^^^^^^^^^^^^^
L'option « log_traffic » est un booléen permettant d'afficher tous les messages
échangés avec le bus lorsqu'il est positionné à « True ». Cette option
génère un volume d'événements de journalisation très important et n'est donc
pas conseillée en production.

Adresse du bus
^^^^^^^^^^^^^^
L'option « host » permet d'indiquer le nom ou l'adresse IP de l'hôte sur lequel
le bus fonctionne.

Service de publication
^^^^^^^^^^^^^^^^^^^^^^
Le connecteur utilise les mécanismes de publication de messages du protocole
:term:`AMQP` pour échanger des informations avec les autres connecteurs de
Vigilo.

Ces mécanismes nécessites de spécifier le nom du service de publication utilisé
pour l'échange de messages sur le bus, appelé *exchange*. Par défaut, le nom de
ce service est le nom du type de message à envoyer.

Identifiant
^^^^^^^^^^^
Chaque connecteur de Vigilo est associé à un compte :term:`AMQP` différent.
L'option « user » permet d'indiquer le nom de ce compte.

Mot de passe
^^^^^^^^^^^^
L'option « password » permet de spécifier le mot de passe associé au compte
:term:`AMQP` indiqué dans l'option « user ».

Connexions sécurisées
^^^^^^^^^^^^^^^^^^^^^
Les connecteurs ont la possibilité de spécifier la politique de sécurité à
appliquer pour les connexions avec le bus. Il est possible de forcer
l'utilisation d'une connexion chiffrée entre le connecteur et le bus en
positionnant l'option « require_ssl » à « True ». Le port de connexion utilisé
par défaut sans SSL est le ``5672``, avec SSL il devient le ``5671``.

Délai maximum de reconnexion
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
En cas de déconnexion du bus, les connecteurs se reconnectent
automatiquement, selon un délai qui augmente exponentiellement (afin d'éviter
d'innonder les journaux système avec des messages annonçant la reconnexion).

L'option « max_reconnect_delay » permet d'indiquer le délai maximum (en
secondes) qui peut s'écouler entre 2 tentatives de reconnexion.
Par défaut, ce délai est fixé à 60 secondes.

File d'attente
^^^^^^^^^^^^^^
L'option « queue » permet de spécifier le nom de la file d'attente :term:`AMQP`
à laquelle se connecter pour recevoir les messages. Si plusieurs connecteurs
spécifient la même file d'attente, il en consommeront les messages au fur et à
mesure de leur capacité de traitement (mode « répartition de charge »).

Abonnements
^^^^^^^^^^^
L'option « subscriptions » contient la liste des nœuds de publication auxquels le
connecteur est abonné (séparés par des virgules). Plus exactement, il s'agit
des nœuds de publication auxquels la file d'attente spécifiée par l'option «
queue » est abonnée. La valeur configurée par défaut lors de l'installation du
connecteur convient généralement à tous les types d'usage.

Attention, il est possible d'ajouter des abonnements dans cette liste, mais les
abonnements existants ne seront pas supprimés automatiquement s'ils sont
supprimés de la liste (il s'agit d'une limitation actuelle du protocole). Pour
cela, il faut passer soit par l'interface de gestion du serveur, soit par la
commande ``vigilo-config-bus``.

État du connecteur
^^^^^^^^^^^^^^^^^^
Les connecteurs de Vigilo sont capables de s'auto-superviser, c'est-à-dire que
des alertes peuvent être émises par Vigilo concernant ses propres connecteurs
lorsque le fonctionnement de ceux-ci est perturbé ou en défaut.

Ce mécanisme est rendu possible grâce à des signaux de vie émis par les
connecteurs à intervalle régulier. Chaque signal de vie correspond à un message
de type « nagios ».

L'option « status_exchange » permet de choisir le nœud de publication vers
lequel les messages de survie du connecteur sont envoyés. Dans le cas où cette
option ne serait pas renseignée, les nœuds configurés dans la section
``[publication]`` sont utilisés pour déterminer la destination des messages. Si
aucun nœud n'est trouvé pour l'envoi des messages de vie, un message d'erreur
est enregistré dans les journaux d'événements.

L'option « status_service » permet de spécifier le nom du service Nagios par
lequel on supervise ce connecteur.


Destination des messages
------------------------
Le connecteur envoie des messages au bus contenant des informations sur
l'état des éléments du parc, ainsi que des données de métrologie permettant
d'évaluer la performance des équipements. Chaque message transmis par le
connecteur possède un type.

La section ``[publications]`` permet d'associer le type des messages à un nœud
de publication. Ainsi, chaque fois qu'un message doit être transmis au bus,
le connecteur consulte cette liste d'associations afin de connaître le nom du
nœud sur lequel il doit publier son message.

Les types de messages supportés par un connecteur sont :

* ``perf`` : messages de performances
* ``state`` : messages d'état
* ``event`` : messages d'événements
* ``nagios`` : commandes Nagios
* ``command`` : commandes diverses

Si une destination n'est pas renseignée, le message sera envoyé sur un nœud du même nom que le type du message.

Exemple de configuration possible, correspondant à une installation standard :

.. sourcecode:: ini

    [publications]
    perf   = perf
    state  = state
    event  = event
    nagios = nagios


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
