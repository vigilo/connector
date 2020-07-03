#!/usr/bin/env python
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2020 CS GROUP - France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import os, sys
from platform import python_version_tuple
from setuptools import setup, find_packages


install_requires = [
    'setuptools',
    'zope.interface',
    'vigilo-common',
    'txAMQP',
    'Twisted',
    'pyOpenSSL',
]
if tuple(python_version_tuple()) < ('2', '6'):
    install_requires.append("simplejson")
if tuple(python_version_tuple()) < ('2', '7'):
    install_requires.append("argparse")

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
        version='5.2.0b2',
        author='Vigilo Team',
        author_email='contact.vigilo@csgroup.eu',
        url='https://www.vigilo-nms.com/',
        description="Vigilo AMQP connector library",
        license='http://www.gnu.org/licenses/gpl-2.0.html',
        long_description="This library gives an API to create an AMQP "
                         "connector for Vigilo.",
        install_requires=install_requires,
        namespace_packages = [ 'vigilo' ],
        packages=find_packages("src"),
        message_extractors={
            'src': [
                ('**.py', 'python', None),
            ],
        },
        entry_points={
            'console_scripts': [
                'vigilo-bus-config = vigilo.connector.configure:main',
                ],
        },
        extras_require={
            'tests': tests_require,
        },
        package_dir={'': 'src'},
        include_package_data=True,
        data_files=install_i18n("i18n", os.path.join(sys.prefix, 'share', 'locale'))
        )

