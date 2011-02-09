# -*- coding: utf-8 -*-
import sys
import os

from twisted.python import usage

from vigilo.common.gettext import translate
_ = translate("vigilo.connector")

class Options(usage.Options):

    optParameters = [
            ["name", "n", None, _("Choose the service name")],
            ["config", "c", None, _("Load this settings.ini file")],
        ]

    def opt_version(self):
        """Display the version and exit"""
        print 'Vigilo 2.0.0 (svn%s)' % ('$Rev: 5998 $'[6:-2])
        sys.exit()

    def postOptions(self):
        if (self["config"] is not None and
                not os.path.exists(self["config"])):
            raise usage.UsageError(_("The configuration file does not exist"))
