Connector
=========

Connector est une bibliothèque de Vigilo_ proposant des classes pour
construire des connecteurs branchés sur le bus de messages.

Pour les détails du fonctionnement de la bibliothèque Connector, se reporter à
la `documentation officielle`_.


Dépendances
-----------
Vigilo nécessite une version de Python supérieure ou égale à 2.5. Le chemin de
l'exécutable python peut être passé en paramètre du ``make install`` de la
façon suivante::

    make install PYTHON=/usr/bin/python2.6

La bibliothèque Connector a besoin des modules python suivants :

- setuptools (ou distribute)
- argparse (si python < 2.6)
- vigilo-common
- zope.interface
- Twisted
- txAMQP


Installation
------------
L'installation se fait par la commande ``make install`` (à exécuter en
``root``).


License
-------
Connector est sous licence `GPL v2`_.


.. _documentation officielle: Vigilo_
.. _Vigilo: http://www.projet-vigilo.org
.. _GPL v2: http://www.gnu.org/licenses/gpl-2.0.html

.. vim: set syntax=rst fileencoding=utf-8 tw=78 :
