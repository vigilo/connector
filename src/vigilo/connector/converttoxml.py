# -*- coding: utf-8 -*-
"""
function to convert text to XML
"""
from twisted.words.xish import domish
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate

_ = translate(__name__)

NS_AGGR = 'http://www.projet-vigilo.org/xmlns/aggr1'
NS_EVENT = 'http://www.projet-vigilo.org/xmlns/event1'
NS_PERF = 'http://www.projet-vigilo.org/xmlns/perf1'
NS_STATE = 'http://www.projet-vigilo.org/xmlns/state1'
MESSAGEONETOONE = 'oneToOne'

def text2xml(text):
    """ 
    Called to return the XML from text message read from socket
    @param text: The text to convert
    @type  text: C{str}
    @return: xml object (twisted.words.xish.domish.Element) 
            representing the text given as argument
            or None in non convertible text
    """
    elements = text.strip().split('|')
    if elements:
        try:
            enveloppe = None
            msg = None
            if len(elements) > 2 and elements[0] == MESSAGEONETOONE:
                enveloppe = oneToOne2xml(elements[:2])
                elements.pop(0)
                elements.pop(0)
            if elements == ['']:
                LOGGER.debug(_("empty line"))
            elif elements[0] == "event":
                msg = event2xml(elements)
            elif elements[0] == "perf":
                msg =  perf2xml(elements)
            elif elements[0] == "state":
                msg = state2xml(elements)
            else:
                LOGGER.warning(_("unknown/malformed message " +
                    "(type: '%s')") % elements[0])
            if enveloppe:
                if msg:
                    enveloppe.addChild(msg)
                    return enveloppe
                else:
                    LOGGER.warning(_("unknown/malformed message " +
                        "(type: '%s')") % elements[0])
            return msg

        except (TypeError, AttributeError):
            LOGGER.warning(_("unknown/malformed message " +
                "(type: '%s')") % elements[0])
            return None

    LOGGER.warning(_("unknown message type"))
    return None

def oneToOne2xml(onetoone_list):
    """ 
    Called to return the XML from MESSAGEONETOONE message list 
    @param event_list: list contenning a MESSAGEONETOONE type message to convert
    @type event_list: C{list}
    @return: xml object (twisted.words.xish.domish.Element)
            representing the text given as argument
            or None in non convertible text
    """

    # to avoid error from message length
    if len(onetoone_list) != 2:
        return None
    # email regexp pattern
    # (\W+@\W+(?:\.\W+)+)
    # (<)?(\w+@\w+(?:\.\w+)+)(?(1)>)

    


    msg = domish.Element((None, MESSAGEONETOONE))
    msg['to'] = onetoone_list[1]
    return msg

def event2xml(event_list):
    """ 
    Called to return the XML from event message list 
    @param event_list: list contening a event type message to convert
    @type event_list: C{list}
    @return: C{str} representing the event in xml format
    @return: xml object (twisted.words.xish.domish.Element)
            representing the text given as argument
            or None in non convertible text
    """

    # to avoid error from message length
    if len(event_list) != 7:
        return None
    

    msg = domish.Element((NS_EVENT, 'event'))
    msg.addElement('timestamp', content=event_list[1])
    msg.addElement('host', content=event_list[2])
    msg.addElement('ip', content=event_list[3])
    msg.addElement('service', content=event_list[4])
    msg.addElement('state', content=event_list[5])
    msg.addElement('message', content=event_list[6])
    return msg


def perf2xml(perf_list):
    """ 
    Called to return the XML from perf message list 
    
    @param perf_list: list contening a perf type message to convert
    @type perf_list: C{list}
    @return: xml object (twisted.words.xish.domish.Element)
             representing the text given as argument
             or None in non convertible text
    """

    # to avoid error from message length
    if len(perf_list) != 5:
        return None


    msg = domish.Element((NS_PERF, 'perf'))
    msg.addElement('timestamp', content=perf_list[1])
    msg.addElement('host', content=perf_list[2])
    msg.addElement('datasource', content=perf_list[3])
    msg.addElement('value', content=perf_list[4])
    return msg

def state2xml(state_list):
    """ 
    Called to return the XML from state message list 
    
    @param state_list: list contening a state type message to convert
    @type state_list: C{list}
    @return: xml object (twisted.words.xish.domish.Element)
             representing the text given as argument
             or None in non convertible text
    """
    
    
    # to avoid error from message length
    if len(state_list) != 9:
        return None
    
    msg = domish.Element((NS_STATE, 'state'))
    msg.addElement('timestamp', content=state_list[1])
    msg.addElement('host', content=state_list[2])
    msg.addElement('ip', content=state_list[3])
    msg.addElement('service', content=state_list[4])
    msg.addElement('statename', content=state_list[5])
    msg.addElement('type', content=state_list[6])
    msg.addElement('attempt', content=state_list[7])
    msg.addElement('message', content=state_list[8])
    return msg
