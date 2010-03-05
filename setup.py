#!/usr/bin/env python
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from setuptools import setup

tests_require = [
    'coverage',
    'nose',
    'pylint',
]

setup(name='vigilo-connector',
        version='0.1',
        author='Vigilo Team',
        author_email='contact@projet-vigilo.org',
        url='http://www.projet-vigilo.org/',
        description='vigilo connector component',
        license='http://www.gnu.org/licenses/gpl-2.0.html',
        long_description='The vigilo connector component is a connector between:\n'
        +'   - XMPP/PubSub BUS of message\n'
        +'   - UNIX sockets\n'
        +'(there are two sockets, for incoming and outgoing messages)\n',
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
        packages=[
            'vigilo',
            'vigilo.connector',
            ],
        entry_points={
        },
        extras_require={
            'tests': tests_require,
        },
        package_dir={'': 'src'},
        )

