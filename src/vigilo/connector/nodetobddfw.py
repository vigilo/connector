# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

"""
Extends pubsub clients to compute Node message.
"""

import twisted.internet.protocol
from twisted.internet import reactor
from twisted.protocols.basic import LineReceiver

from vigilo.common.logging import get_logger
from vigilo.pubsub import  NodeSubscriber
import logging 
from vigilo.connector import converttoxml 
import os

import time

from vigilo.models.session import DBSession
from vigilo.models import State, Events, Host, Service
from sqlalchemy import not_ , and_, desc
from datetime import datetime
import transaction

LOGGER = get_logger(__name__)

# Because XML and Database don't use same names
elm_to_bdd = { 'host' : 'hostname',
       'service' : 'servicename',
       'state' : 'rawstate',
       'message' : 'output',
       'severity' : 'severity',
       'occurence' : 'occurence' }

def InsertState(xml):
    """
    Insert XML stream of state object into the database
    keep in mind that timestamp has to be converted
    """
    state = State('', '', '')
    for elm in xml.elements():
        if elm.name == 'timestamp':
            # if the timestamp is not a real integer
            try:
                setattr(state, elm.name, 
                        datetime.fromtimestamp(int(elm.children[0])))
            except:
                setattr(state, elm.name, datetime.now())
        else:
            setattr(state, elm.name, elm.children[0])
    try:
        DBSession.add(state)
        DBSession.flush()
        transaction.commit()
    except:
        LOGGER.debug("Can't push data in database")
        DBSession.rollback()

def InsertCorrEvent(xml):
    
    """
    Insert XML stream of correvent object into the database
    first, check that no other element exist with the same host/service
        else, this is an update
    The highlevel service et ip are static value and already in database
        we don't use them
    """

    hostname, servicename = None, None
    for elm in xml.elements():
        if elm.name == 'host':
            hostname = elm.children[0]
        elif elm.name == 'service':
            servicename = elm.children[0]
    if hostname == None or servicename == None:
        LOGGER.debug( "Host or Service wrong")
        DBSession.rollback()
        return
    event = DBSession.query(Events
            ).filter(Events.hostname == hostname
            ).filter(Events.servicename == servicename
            ).filter(not_(and_(Events.active == False,
                Events.status == 'AAClosed'))
            ).filter(Events.timestamp_active != None
            ).order_by(desc(Events.idevent))
    if event.count() != 0 :
        LOGGER.debug("Duplicate entry, we update it.")
        UpdateCorrEvent(xml)
        return
    event = Events('', '')
    for elm in xml.elements():
        if elm.name == 'timestamp':
            # if the timestamp is not a real integer
            try:
                event.timestamp = datetime.fromtimestamp(int(elm.children[0]))
            except:
                event.timestamp = datetime.now()
        elif elm.name == 'impact':
            event.impact = elm.getAttribute('count')
        elif elm.name == 'highlevel' or elm.name == 'ip':
            pass
        else:
            setattr(event, elm_to_bdd[elm.name], elm.children[0])
    try:
        DBSession.add(event)
        DBSession.flush()
        transaction.commit()
    except:
        LOGGER.debug("Can't push data in database")
        DBSession.rollback()

def UpdateCorrEvent(xml):
    """
    Update the database with the XML stream
    first, check that an other element exist with the same host/service
        else, this is an insert
    The highlevel service et ip are static value and already in database
        we don't use them
    """ 
    hostname, servicename = None, None
    for elm in xml.elements():
        if elm.name == 'host':
            hostname = elm.children[0]
        elif elm.name == 'service':
            servicename = elm.children[0]
    if hostname == None or servicename == None:
        LOGGER.debug( "Host or Service wrong")
        DBSession.rollback()
        return
    event = DBSession.query(Events
            ).filter(Events.hostname == hostname
            ).filter(Events.servicename == servicename
            ).filter(not_(and_(Events.active == False,
                Events.status == 'AAClosed'))
            ).filter(Events.timestamp_active != None
            ).order_by(desc(Events.idevent))
    if event.count() == 0:
        LOGGER.debug( "Update query but not events in database with this couple host, service. We create it." , event.count())
        InsertCorrEvent(xml)
        return
    event = event[0]
    for elm in xml.elements():
        if elm.name == 'timestamp':
            # if the timestamp is not a real integer
            try:        
                setattr(event, elm.name, 
                        datetime.fromtimestamp(int(elm.children[0])))
            except:
                setattr(event, elm.name, datetime.now())
        elif elm.name == 'impact':
            event.impact = elm.getAttribute('count')
        elif elm.name == 'highlevel' or elm.name == 'ip':
            pass

        else:
            setattr(event, elm_to_bdd[elm.name], elm.children[0])
    try:
        DBSession.flush()
        transaction.commit()
    except:
        LOGGER.debug("Can't push data in database")
        DBSession.rollback()


class NodeToBDDForwarder(NodeSubscriber, twisted.internet.protocol.Protocol):
    """
    Receives messages on the xmpp bus, and passes them to the socket.
    Forward Node to socket.
    """

    def __init__(self, subscription):
        self.__subscription = subscription
        NodeSubscriber.__init__(self, [subscription])


    def itemsReceived(self, event):

        if event.nodeIdentifier != self.__subscription.node:
            return
        
        for item in event.items:
            
            if item.name != 'item':
                continue
            
            it = [ it for it in item.elements() if item.name == "item" ]
            for i in it:
                LOGGER.debug('Message from BUS to forward: %s', i.toXml().encode('utf8'))
                # Sélectionne la bonne fonction suivant le type de message
                if i.name == 'correvent' and \
                   i.getAttribute('change') is not None:
                    UpdateCorrEvent(i)
                elif i.name == 'correvent':
                    InsertCorrEvent(i)
                elif i.name == 'state':
                    InsertState(i)
                else:
                    LOGGER.debug('Unknown XML')
