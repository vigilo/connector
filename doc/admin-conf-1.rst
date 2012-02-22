Création du compte sur le bus
-----------------------------
Le connecteur FTP nécessite qu'un compte soit créé sur la machine hébergeant
le bus. Les comptes doivent être créés sur la machine qui héberge le serveur
rabbitmq, à l'aide de la commande::

    # rabbitmqctl add_user nom_d_utilisateur mot_de_passe


Configuration
=============

Le module |name| est fourni avec un fichier de configuration situé
par défaut dans « /etc/vigilo/|name|/settings.ini ».

Ce fichier est composé de différentes sections permettant de paramétrer des
aspects divers du module, chacune de ces sections peut contenir un ensemble de
valeurs sous la forme ``clé = valeur``. Les lignes commençant par « ; » ou
« # » sont des commentaires et sont par conséquent ignorées.

Le format de ce fichier peut donc être résumé dans l'extrait suivant:

.. sourcecode:: ini

    # Ceci est un commentaire
    ; Ceci est également un commentaire
    [section1]
    option1=valeur1
    option2=valeur2
    ; ...

    [section2]
    option1=val1
    ; ...

Les sections utilisées par le connecteur et leur rôle sont détaillées
ci-dessous:

bus
    Contient les options relatives à la configuration de l'accès au bus de
    messages.

connector
    Contient les options de configuration génériques d'un connecteur de Vigilo.

publications
    Contient une liste d'associations entre les types de messages envoyés
    et les nœuds de publication (:term:`exchange`) vers lesquels ces
    messages sont transmis.

loggers, handlers, formatters, logger_*, handler_*, formatter_*
    Contient la configuration du mécanisme de journalisation des événements
    (voir chapitre :ref:`logging`).

    « \* » correspond au nom d'un logger/handler/formatter défini dans la
    section loggers, handlers ou formatters (respectivement).
