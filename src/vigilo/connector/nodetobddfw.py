# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Extends pubsub clients to compute Node message.
"""

from __future__ import absolute_import

import twisted.internet.protocol

from vigilo.common.logging import get_logger
from vigilo.pubsub import  NodeSubscriber
from vigilo.models.session import DBSession
from vigilo.models import State, Events

from sqlalchemy import not_ , and_, desc
from datetime import datetime
import transaction

LOGGER = get_logger(__name__)

# Because XML and Database don't use same names
ELM_TO_BDD = { 'host' : 'hostname',
       'service' : 'servicename',
       'state' : 'rawstate',
       'message' : 'output',
       'severity' : 'severity',
       'occurence' : 'occurence',
       }

def insertState(xml):
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
            except ValueError:
                setattr(state, elm.name, datetime.now())
        else:
            if elm.name in ELM_TO_BDD:
                setattr(state, ELM_TO_BDD[elm.name], elm.children[0])
            else:
                setattr(state, elm.name, elm.children[0])

    DBSession.add(state)
    DBSession.flush()
    transaction.commit()

def insertCorrEvent(xml):
    
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
        updateCorrEvent(xml)
        return
    event = Events('','')
    for elm in xml.elements():
        if elm.name == 'timestamp':
            # if the timestamp is not a real integer
            try:
                event.timestamp = datetime.fromtimestamp(int(elm.children[0]))
            except ValueError:
                event.timestamp = datetime.now()
        elif elm.name == 'impact':
            event.impact = elm.getAttribute('count')
        elif elm.name == 'highlevel' or elm.name == 'ip':
            pass
        else:
            setattr(event, ELM_TO_BDD[elm.name], elm.children[0])
    DBSession.add(event)
    DBSession.flush()
    transaction.commit()

def updateCorrEvent(xml):
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
        LOGGER.debug( "Update query but not events in database with this " + \
                "couple host, service. We create it." , event.count())
        insertCorrEvent(xml)
        return
    event = event[0]
    for elm in xml.elements():
        if elm.name == 'timestamp':
            # if the timestamp is not a real integer
            try:        
                setattr(event, elm.name,
                        datetime.fromtimestamp(int(elm.children[0])))
            except ValueError:
                setattr(event, elm.name, datetime.now())
        elif elm.name == 'impact':
            event.impact = elm.getAttribute('count')
        elif elm.name == 'highlevel' or elm.name == 'ip':
            pass

        else:
            setattr(event, ELM_TO_BDD[elm.name], elm.children[0])
    DBSession.flush()
    transaction.commit()


class NodeToBDDForwarder(NodeSubscriber, twisted.internet.protocol.Protocol):
    """
    Receives messages on the xmpp bus, and passes them to the socket.
    Forward Node to socket.
    """

    def __init__(self, subscription):
        self.__subscription = subscription
        NodeSubscriber.__init__(self, [subscription])

    def itemsReceived(self, event):
        """
        Manage items from the BUS
        """
        if event.nodeIdentifier != self.__subscription.node:
            return
        
        for item in event.items:
            
            if item.name != 'item':
                continue
            
            it = [ it for it in item.elements() if item.name == "item" ]
            for i in it:
                LOGGER.debug('Message from BUS to forward: %s',
                        i.toXml().encode('utf8'))
                # Sélectionne la bonne fonction suivant le type de message
                if i.name == 'correvent' and \
                        i.getAttribute('change') is not None:
                    updateCorrEvent(i)
                elif i.name == 'correvent':
                    insertCorrEvent(i)
                elif i.name == 'state':
                    insertState(i)
                else:
                    LOGGER.debug('Unknown XML')
