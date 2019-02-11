# -*- coding: utf-8 -*-
# Copyright (C) 2011-2019 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

name = u'connector'

project = u'Vigilo %s' % name

pdf_documents = [
        ('dev', "dev-%s" % name, "Connector : Guide de développement", u'Vigilo'),
]

latex_documents = [
        ('dev', 'dev-%s.tex' % name, u"Connector : Guide de développement",
         'AA100004-2/DEV00007', 'vigilo'),
]

execfile("../buildenv/doc/conf.py")
