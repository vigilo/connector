# -*- coding: utf-8 -*-
# pylint: disable-msg=W0212,R0903,R0904,C0111,W0613
# Copyright (C) 2006-2021 CS GROUP - France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

from __future__ import with_statement
import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
#from nose.twistedtools import reactor, deferred

import mock
#from twisted.internet import protocol, tcp, defer

from txamqp.message import Message
from twisted.python.failure import Failure
from vigilo.connector.amqp import getErrorMessage



class GetErrorMessageTestCase(unittest.TestCase):


    @mock.patch('vigilo.connector.amqp.get_error_message')
    def test_exception(self, mock_get_error_message):
        """getErrorMessage avec une Exception"""
        getErrorMessage(Exception("message ascii basique"))
        self.assertTrue(mock_get_error_message.called, "la fonction "
                "vigilo.common.logging.get_error_message() "
                "n'a pas ete appelee")


    @mock.patch('vigilo.connector.amqp.get_error_message')
    def _check(self, build_error, mock_get_error_message):
        """
        @param build_error: fonction à appliquer à un message pour retourner
            l'erreur à tester
        @type  build_error: {callable}
        """
        # liste des messages à tester, avec la fonction à appliquer pour
        # pouvoir les comparer au résultat de getErrorMessage (c'est à dire les
        # convertir en unicode)
        messages = [
                ("message ascii", unicode),
                ("message non-ascii : é è à ç", lambda x: x.decode("utf-8")),
                (u"message non-ascii unicode : é è à ç", lambda x: x),
                ]
        for message, to_unicode in messages:
            r = getErrorMessage(build_error(message))
            self.assertEqual(r, to_unicode(message))
            self.assertFalse(mock_get_error_message.called,
                    "la fonction vigilo.common.logging.get_error_message() "
                    "a ete appelee")
        getErrorMessage(build_error(
                u"message non-ascii en iso8859-1: é è à ç".encode('iso-8859-1')
                ))
        self.assertTrue(mock_get_error_message.called, "la fonction "
                "vigilo.common.logging.get_error_message() "
                "n'a pas ete appelee")


    def test_message(self):
        """getErrorMessage avec un Message"""
        self._check(lambda m: Message("close", ("404", m, 60, 40)))

    def test_failure_message(self):
        """getErrorMessage avec un Message dans une Failure"""
        def failure_message(m):
            amqp_msg = Message("close", ("404", m, 60, 40))
            return Failure(amqp_msg)
        self._check(failure_message)

    def test_failure_exception_message(self):
        """
        getErrorMessage avec un Message dans une Exception dans une Failure
        """
        def failure_exception_message(m):
            amqp_msg = Message("close", ("404", m, 60, 40))
            return Failure(Exception(amqp_msg))
        self._check(failure_exception_message)
