# -*- coding: utf-8 -*-
"""
Ce module contient la classe qui gère les options
d'un connecteur pour le bus de Vigilo.
"""

import sys
import os
import pkg_resources

from twisted.python import usage

from vigilo.common.gettext import translate
_ = translate("vigilo.connector")


class Options(usage.Options):
    """
    Une classe qui gère les options
    d'un connecteur de Vigilo.
    """
    optParameters = [
            ["config", "c", None, _("Load this settings.ini file")],
        ]

    def __init__(self, module):
        """
        Prépare les options pour le connecteur.

        @param module: Le nom du module qui contient le connecteur
            (eg. "vigilo.connector_nagios").
        @type module: C{str}
        """
        self._module = module
        super(Options, self).__init__()

    def opt_version(self):
        """Affiche la version du connecteur et quitte."""
        module_name = '-'.join(self._module.split('.')[:2]).replace('_', '-')
        dist = pkg_resources.get_distribution(module_name)
        print '%s %s' % (module_name, dist.version)
        sys.exit(0)

    def postOptions(self):
        """Vérifie la cohérences des options passées au connecteur."""
        if (self["config"] is not None and
                not os.path.exists(self["config"])):
            raise usage.UsageError(_("The configuration file does not exist"))


def make_options(module):
    """
    Factory pour les options d'un connecteur Vigilo.

    @param module: Nom du module correspondant au connecteur
        (eg. "vigilo.connector_nagios").
    @type module: C{str}
    @return: Une fonction qui génère les options pour le connecteur.
    @rtype: C{callable}
    """
    def _inner(plugin):
        """
        Vraie fonction pour générer les options du module.

        @param plugin: Le plugin twistd dont on génère les options.
        @type plugin: C{object}
        @return: Options du connecteur.
        @rtype: L{Options}
        """
        # pylint: disable-msg=W0613
        # W0613: Unused argument 'plugin'
        return Options(module)
    return _inner


def getSettings(options, module):
    from vigilo.common.conf import settings
    if options["config"] is not None:
        settings.load_file(options["config"])
    else:
        settings.load_module(module)
    return settings


def parseSubscriptions(settings):
    try:
        subs_option = settings['bus'].as_list('subscriptions')
    except KeyError:
        subs_option = []
    if subs_option == ['']:
        subs_option = []

    subscriptions = []
    for subs_value in subs_option:
        if subs_value.count(":") == 0:
            subscriptions.append( (subs_value, None) )
        elif subs_value.count(":") == 1:
            subscriptions.append( subs_value.split(":") )
        else:
            raise ValueError("Can't parse bus/subscriptions value: %r"
                             % subs_value)
    return subscriptions
