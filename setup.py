#!/usr/bin/env python
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import os, sys
from setuptools import setup, find_packages

tests_require = [
    'coverage',
    'nose',
    'pylint',
    'mock',
]

def install_i18n(i18ndir, destdir):
    data_files = []
    langs = []
    for f in os.listdir(i18ndir):
        if os.path.isdir(os.path.join(i18ndir, f)) and not f.startswith("."):
            langs.append(f)
    for lang in langs:
        for f in os.listdir(os.path.join(i18ndir, lang, "LC_MESSAGES")):
            if f.endswith(".mo"):
                data_files.append(
                        (os.path.join(destdir, lang, "LC_MESSAGES"),
                         [os.path.join(i18ndir, lang, "LC_MESSAGES", f)])
                )
    return data_files

setup(name='vigilo-connector',
        version='2.0.10',
        author='Vigilo Team',
        author_email='contact@projet-vigilo.org',
        url='http://www.projet-vigilo.org/',
        description="Vigilo XMPP connector library",
        license='http://www.gnu.org/licenses/gpl-2.0.html',
        long_description="This library gives an API to create an XMPP "
                         "connector for Vigilo.",
        install_requires=[
            # dashes become underscores
            # order is important (wokkel before Twisted)
            'setuptools',
            'vigilo-common',
            'vigilo-pubsub',
            'wokkel',
            'Twisted',
            ],
        namespace_packages = [
            'vigilo',
            ],
        packages=find_packages("src"),
        message_extractors={
            'src': [
                ('**.py', 'python', None),
            ],
        },
        entry_points={
        },
        extras_require={
            'tests': tests_require,
        },
        package_dir={'': 'src'},
        data_files=install_i18n("i18n", os.path.join(sys.prefix, 'share', 'locale'))
        )

