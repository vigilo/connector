# -*- coding: utf-8 -*-
from twisted.python import usage

class Options(usage.Options):
    def opt_version(self):
        print 'Vigilo 2.0.0 (svn%s)' % ('$Rev: 5998 $'[6:-2])
        sys.exit()
