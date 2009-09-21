#!/usr/bin/env python
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from setuptools import setup

setup(name='vigilo-connector',
        version='0.1',
        author='Thomas BURGUIERE',
        author_email='thomas.burguiere@c-s.fr',
        url='http://www.projet-vigilo.org/',
        description='vigilo connector component',
        license='http://www.gnu.org/licenses/gpl-2.0.html',
        long_description='The vigilo connector component is a connector between:\n'
        +'   - XMPP/PubSub BUS of message\n'
        +'   - UNIX sockets\n'
        +'(there is two differents sockets, one for the message socket to BUS, one for the message BUS to socket\n',
        install_requires=[
            # dashes become underscores
            # order is important (wokkel before Twisted)
            'coverage',
            'nose',
            'pylint',

            'vigilo-common',
            'vigilo-pubsub',
            'wokkel',
            'Twisted',
            #'rrdtool',
            ],
        namespace_packages = [
            'vigilo',
            ],
        packages=[
            'vigilo',
            'vigilo.connector',
            ],
        entry_points={
            'console_scripts': [
                'connector = vigilo.connector.main:main',
                ],
            },
        package_dir={'': 'src'},
        )

