# -*- coding: utf-8 -*-
# pylint: disable-msg=W0212,R0903,R0904,C0111,W0613
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor, deferred

from mock import Mock

from twisted.words.protocols.jabber.jid import JID

from vigilo.common.conf import settings
settings.load_module(__name__)

from vigilo.connector.presence import PresenceManager
#from vigilo.pubsub.xml import NS_PERF, NS_COMMAND

from helpers import XmlStreamStub, wait, HandlerStub


class ForwarderStub(object):
    queue = []

class PresenceManagerTest(unittest.TestCase):
    """Teste la gestion de la présence"""

    def setUp(self):
        self.pm = PresenceManager()
        self.xs = XmlStreamStub()
        self.pm.xmlstream = self.xs.xmlstream
        self.pm.setHandlerParent(HandlerStub(self.xs.xmlstream))

    def tearDown(self):
        # On a touché aux settings
        settings.reset()
        settings.load_module(__name__)

    def test_choose_prio_static(self):
        """Choix d'une priorité statique"""
        self.pm.static_priority = 42
        # Envoyé à la connexion: prio 0
        self.pm.availableReceived(self.pm.parent.jid)
        self.assertEqual(len(self.xs.output), 1)
        print self.xs.output[0].toXml()
        self.assertEqual(str(self.xs.output[0].priority), "42")

    def test_choose_prio_alone(self):
        """Choix d'une priorité quand on est seul"""
        self.pm.availableReceived(self.pm.parent.jid)
        self.assertEqual(len(self.xs.output), 1)
        print self.xs.output[0].toXml()
        self.assertEqual(str(self.xs.output[0].priority), "1")

    def test_max_priority(self):
        self.pm.priority = 1
        self.pm._priorities["other1"] = 2
        self.pm._priorities["other2"] = 3
        self.assertEqual(self.pm.getMaxPriority(), 4)

    def test_become_master(self):
        self.pm.priority = 1
        self.pm._priorities["other"] = 2
        self.pm.tryToBecomeMaster()
        self.assertEqual(len(self.xs.output), 1)
        print self.xs.output[0].toXml()
        self.assertEqual(str(self.xs.output[0].priority), "3")

    def test_become_master_already_taken(self):
        self.pm.priority = 1
        self.pm._priorities["other"] = 3
        self.pm.tryToBecomeMaster()
        self.assertEqual(len(self.xs.output), 0)
        self.assertTrue(self.pm._changeTimer.active())

    def test_lower_priority(self):
        self.pm.priority = 2
        self.pm._priorities["other"] = 1
        other = JID("jid@example.com/other")
        self.pm.availableReceived(other, priority=3)
        self.assertEqual(len(self.xs.output), 1)
        print self.xs.output[0].toXml()
        self.assertEqual(str(self.xs.output[0].priority), "1")

    def test_lower_priority_already_lowest(self):
        """On ne peut pas baisser la dispo en-dessous de 1"""
        self.pm.priority = 1
        self.pm._priorities["other"] = 1
        other = JID("jid@example.com/other")
        self.pm.availableReceived(other, priority=3)
        self.assertEqual(len(self.xs.output), 0)

    def test_lower_priority_already_taken(self):
        """Baisser la prio ne fait rien si elle n'est pas dispo"""
        self.pm.priority = 2
        self.pm._priorities["other"] = 3
        other = JID("jid@example.com/other")
        self.pm.availableReceived(other, priority=1)
        self.assertEqual(len(self.xs.output), 0)

    def test_lower_priority_unavailable(self):
        """Baisser la prio ne fait rien si on est indispo"""
        self.pm.priority = -1
        self.pm._priorities["other"] = 1
        other = JID("jid@example.com/other")
        self.pm.availableReceived(other, priority=3)
        self.assertEqual(len(self.xs.output), 0)

    def test_master_for_too_long(self):
        """Protection contre un maitre permanent"""
        self.pm.priority = 3
        self.pm._priorities["other"] = 1
        self.pm._dictatorshipPrevention()
        self.assertEqual(len(self.xs.output), 1)
        print self.xs.output[0].toXml()
        self.assertEqual(str(self.xs.output[0].priority), "2")

    def test_reset(self):
        """Le reset de la prio ré-organise les priorités"""
        self.pm.parent.jid.resource = "a"
        self.pm.priority = 3
        self.pm._priorities["b"] = 2
        self.pm._priorities["c"] = 1
        self.pm.reset()
        self.assertEqual(len(self.xs.output), 1)
        print self.xs.output[0].toXml()
        self.assertEqual(str(self.xs.output[0].priority), "1")

    def test_reset_unavailable(self):
        """Le reset de la prio ne fait rien si on est unavailable"""
        self.pm.priority = -1
        self.pm.reset()
        self.assertEqual(len(self.xs.output), 0)

    def test_chosen_lowest(self):
        """Si on prend la prio 1, il faut préparer un changement de prio"""
        self.pm._priorities["other"] = 2
        self.pm.availableReceived(self.pm.parent.jid, priority=1)
        self.assertEqual(len(self.xs.output), 0)
        self.assertTrue(self.pm._changeTimer.active())

    def test_got_unavailable(self):
        """Un frère s'est déconnecté"""
        self.pm._priorities["other"] = 2
        other = JID("jid@example.com/other")
        self.pm.reset = Mock()
        self.pm.unavailableReceived(other)
        self.assertTrue("other" not in self.pm._priorities)
        self.assertTrue(self.pm.reset.called)

    def test_got_negative_priority(self):
        """Un frère s'est rendu non disponible"""
        self.pm._priorities["other"] = 2
        other = JID("jid@example.com/other")
        self.pm.reset = Mock()
        self.pm.availableReceived(other, priority=-1)
        self.assertTrue("other" not in self.pm._priorities)
        self.assertTrue(self.pm.reset.called)

    def test_got_new_brother(self):
        """Un frère s'est connecté"""
        other = JID("jid@example.com/other")
        self.pm.reset = Mock()
        self.pm.availableReceived(other)
        self.assertTrue("other" in self.pm._priorities)
        self.assertEqual(self.pm._priorities["other"], 0)
        self.assertTrue(self.pm.reset.called)

    def test_got_conflict_on_me(self):
        """Un frère a pris le même ID que moi"""
        self.pm.priority = 1
        self.pm._priorities["other"] = 2
        other = JID("jid@example.com/other")
        self.pm.reset = Mock()
        self.pm.availableReceived(other, priority=1)
        self.assertTrue(self.pm.reset.called)

    def test_got_conflict_on_others(self):
        """Un frère a pris le même ID qu'un autre frère"""
        self.pm.priority = 1
        self.pm._priorities["other"] = 3
        self.pm._priorities["other2"] = 2
        other = JID("jid@example.com/other")
        self.pm.reset = Mock()
        self.pm.availableReceived(other, priority=2)
        self.assertTrue(self.pm.reset.called)

    def test_pause_producing(self):
        self.pm.priority = 1
        self.pm.pauseProducing()
        self.assertEqual(self.pm.priority, -1)
        self.assertEqual(len(self.xs.output), 1)
        print self.xs.output[0].toXml()
        self.assertEqual(self.xs.output[0]["type"], "unavailable")

    def test_pause_producing_already_stopped(self):
        self.pm.priority = -1
        self.pm.pauseProducing()
        self.assertEqual(len(self.xs.output), 0)

    def test_resume_producing(self):
        self.pm.priority = -1
        self.pm.reset = Mock()
        self.pm.resumeProducing()
        self.assertEqual(len(self.xs.output), 1)
        print self.xs.output[0].toXml()
        self.assertEqual(self.xs.output[0].priority, None)
        self.assertTrue(self.pm.reset.called)

    def test_resume_producing_already_resumed(self):
        self.pm.priority = 1
        self.pm.reset = Mock()
        self.pm.resumeProducing()
        self.assertEqual(len(self.xs.output), 0)
        self.assertFalse(self.pm.reset.called)

