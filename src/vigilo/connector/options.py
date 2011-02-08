# -*- coding: utf-8 -*-
import sys

from twisted.python import usage

class Options(usage.Options):

    def opt_version(self):
        """Display the version and exit"""
        print 'Vigilo 2.0.0 (svn%s)' % ('$Rev: 5998 $'[6:-2])
        sys.exit()

    def opt_name(self, name):
        """Choose the service name"""
        self["name"] = name

