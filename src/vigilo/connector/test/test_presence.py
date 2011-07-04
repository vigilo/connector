# -*- coding: utf-8 -*-
# pylint: disable-msg=W0212,R0903,R0904,C0111,W0613
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import unittest

# ATTENTION: ne pas utiliser twisted.trial, car nose va ignorer les erreurs
# produites par ce module !!!
#from twisted.trial import unittest
from nose.twistedtools import reactor, deferred

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

    def tearDown(self):
        # On a touché aux settings
        settings.reset()
        settings.load_module(__name__)

    def test_choose_prio_static(self):
        """Choix d'une priorité statique"""
        pm = PresenceManager()
        pm.static_priority = 42
        self.assertEqual(pm.choosePriority(), 42)

    def test_choose_prio_alone(self):
        """Choix d'une priorité quand on est seul"""
        pm = PresenceManager()
        self.assertEqual(pm.choosePriority(), 1)

    def test_choose_prio_2_1(self):
        """Choix d'une priorité à deux (1)"""
        pm = PresenceManager()
        pm.priority = 1
        pm._priorities["other"] = 2
        self.assertEqual(pm.choosePriority(), 3)

    def test_choose_prio_2_2(self):
        """Choix d'une priorité à deux (2)"""
        pm = PresenceManager()
        pm.priority = 2
        pm._priorities["other"] = 1
        self.assertEqual(pm.choosePriority(), 3)

    def test_choose_prio_2_3(self):
        """Choix d'une priorité à deux (3)"""
        pm = PresenceManager()
        pm.priority = 3
        pm._priorities["other"] = 1
        self.assertEqual(pm.choosePriority(), 2)

    def test_choose_prio_3_1(self):
        """Choix d'une priorité à trois (1)"""
        pm = PresenceManager()
        pm.priority = 1
        pm._priorities["other1"] = 2
        pm._priorities["other2"] = 3
        self.assertEqual(pm.choosePriority(), 4)

    def test_choose_prio_3_2(self):
        """Choix d'une priorité à trois (2)"""
        pm = PresenceManager()
        pm.priority = 2
        pm._priorities["other1"] = 1
        pm._priorities["other2"] = 3
        self.assertEqual(pm.choosePriority(), 4)

    def test_choose_prio_3_3(self):
        """Choix d'une priorité à trois (3)"""
        pm = PresenceManager()
        pm.priority = 3
        pm._priorities["other1"] = 1
        pm._priorities["other2"] = 4
        self.assertEqual(pm.choosePriority(), 2)

    def test_overloaded(self):
        """Gestion de la surchage du Forwarder"""
        f = ForwarderStub()
        pm = PresenceManager(f)
        settings["connector"]["max_queue_size"] = 2
        f.queue = [1, 2, 3]
        self.assertTrue(pm.isOverloaded())

    def test_sendpresence_overloaded(self):
        """Envoi de présence quand le forwarder est surchargé"""
        pm = PresenceManager(ForwarderStub())
        pm.isOverloaded = lambda: True
        xs = XmlStreamStub()
        pm.xmlstream = xs.xmlstream
        pm.setHandlerParent(HandlerStub(xs.xmlstream))
        pm.priority = 1
        pm.sendPresence()
        self.assertEqual(pm.priority, -1)
        self.assertEqual(len(xs.output), 1)
        self.assertEqual(xs.output[0].toXml(),
                         "<presence type='unavailable'/>")

    def test_sendpresence_already_overloaded(self):
        """Envoi de présence quand le forwarder était déjà surchargé"""
        pm = PresenceManager(ForwarderStub())
        pm.isOverloaded = lambda: True
        xs = XmlStreamStub()
        pm.xmlstream = xs.xmlstream
        pm.setHandlerParent(HandlerStub(xs.xmlstream))
        pm.priority = -1
        pm.sendPresence()
        self.assertEqual(pm.priority, -1)
        self.assertEqual(len(xs.output), 0)

    def test_sendpresence_nochange(self):
        """Envoi de présence sans changement"""
        pm = PresenceManager()
        xs = XmlStreamStub()
        pm.xmlstream = xs.xmlstream
        pm.priority = 1
        pm.sendPresence(1)
        self.assertEqual(len(xs.output), 0)

    def test_sendpresence(self):
        """Envoi de présence"""
        pm = PresenceManager()
        xs = XmlStreamStub()
        pm.xmlstream = xs.xmlstream
        pm.setHandlerParent(HandlerStub(xs.xmlstream))
        pm.sendPresence()
        self.assertEqual(len(xs.output), 1)
        self.assertEqual(xs.output[0].toXml(),
                         "<presence><priority>1</priority></presence>")
        self.assertEqual(pm._task.interval, 10)

    def test_available_self(self):
        """Réception de notre propre présence"""
        pm = PresenceManager()
        xs = XmlStreamStub()
        pm.xmlstream = xs.xmlstream
        pm.setHandlerParent(HandlerStub(xs.xmlstream))
        pm.availableReceived(JID("jid@example.com"), priority=24)
        self.assertEqual(pm.priority, 24)
        self.assertEqual(pm._priorities, {})

    def test_available_other_account(self):
        """Réception de la présence d'un autre compte"""
        pm = PresenceManager()
        xs = XmlStreamStub()
        pm.xmlstream = xs.xmlstream
        pm.setHandlerParent(HandlerStub(xs.xmlstream))
        pm.availableReceived(JID("jid2@example.com"), priority=24)
        self.assertEqual(pm._priorities, {})

    def test_available_other(self):
        """Réception de la présence d'une autre instance"""
        pm = PresenceManager()
        xs = XmlStreamStub()
        pm.xmlstream = xs.xmlstream
        pm.setHandlerParent(HandlerStub(xs.xmlstream))
        pm.availableReceived(JID("jid@example.com/testresource"), priority=24)
        self.assertEqual(pm._priorities, {"testresource": 24})

    @deferred(timeout=30)
    def test_available_received_conflict(self):
        """Réception de présence en conflit"""
        pm = PresenceManager()
        xs = XmlStreamStub()
        pm.xmlstream = xs.xmlstream
        pm.setHandlerParent(HandlerStub(xs.xmlstream))
        pm._task.start(60)
        pm.priority = 1
        d = wait(0.2)
        def recv(r):
            self.assertEqual(pm.priority, 1)
            pm.availableReceived(JID("jid@example.com/someoneelse"),
                                 priority=1)
        d.addCallback(recv)
        d.addCallback(lambda x: wait(0.2))
        def check_task_stopped(r):
            print [ o.toXml() for o in xs.output ]
            self.assertEqual(str(xs.output[-1].priority), "2")
            self.assertFalse(pm._task.running)
        d.addCallback(check_task_stopped)
        d.addCallback(lambda x: wait(7))
        def check_task_started(r):
            self.assertTrue(pm._task.running)
        d.addCallback(check_task_started)
        return d

    def test_unavailable(self):
        """Réception d'absence"""
        pm = PresenceManager()
        xs = XmlStreamStub()
        pm.xmlstream = xs.xmlstream
        pm.setHandlerParent(HandlerStub(xs.xmlstream))
        pm._priorities["testresource"] = 42
        pm.unavailableReceived(JID("jid@example.com/testresource"))
        self.assertEqual(pm._priorities, {})

    def test_unavailable_other(self):
        """Réception d'absence pour un autre compte"""
        pm = PresenceManager()
        xs = XmlStreamStub()
        pm.xmlstream = xs.xmlstream
        pm.setHandlerParent(HandlerStub(xs.xmlstream))
        pm._priorities["testresource"] = 42
        pm.unavailableReceived(JID("jid2@example.com/testresource"))
        self.assertEqual(pm._priorities, {"testresource": 42})

    def test_available_early(self):
        """Conflit la présence avant d'avoir lancé la boucle principale"""
        pm = PresenceManager()
        xs = XmlStreamStub()
        pm.xmlstream = xs.xmlstream
        pm.setHandlerParent(HandlerStub(xs.xmlstream))
        pm.priority = 1
        # Si le LoopingCall n'est pas encore lançé, une AssertionError sera
        # levée et fera échouer ce test
        pm.availableReceived(JID("jid@example.com/someoneelse"), priority=1)



