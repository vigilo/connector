# -*- coding: utf-8 -*-
"""
function to convert text to XML
"""
from wokkel.generic import parseXml
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate

_ = translate(__name__)

def text2xml(text):
    """ 
    Called to return the XML from text message read from socket
    @param text: The text to convert
    @type  text: C{str}
    """
    elements = text.strip().split('|')
    if elements:
        try:
            if elements == ['']:
                LOGGER.debug(_("empty line"))
            if elements[0] == "event":
                return parseXml(event2xml(elements)).toXml()
            elif elements[0] == "perf":
                return parseXml(perf2xml(elements)).toXml()
            elif elements[0] == "state":
                return parseXml(state2xml(elements)).toXml()
        except (TypeError, AttributeError) :
            LOGGER.warning(_("unknown message type: %s") % elements[0])
            return None

    LOGGER.warning(_("unknown message type"))
    return None


def event2xml(event_list):
    """ Called to return the XML from event message list """

    # to avoid error from message length
    if len(event_list) != 7:
        return None

    message = """<event xmlns="http://www.projet-vigilo.org/messages">
    <timestamp>%(timestamp)s</timestamp>
    <host>%(host)s</host>
    <ip>%(ip)s</ip>
    <service>%(service)s</service>
    <state>%(state)s</state>
    <message>%(message)s</message>
</event>
"""

    dico = { "timestamp": event_list[1], # MUST
             "host": event_list[2],      # MUST
             "ip": event_list[3],        # MAY
             "service": event_list[4],   # MAY
             "state": event_list[5],     # MUST
             "message": event_list[6]    # SHOULD
           }

    return message % dico


def perf2xml(perf_list):
    """ Called to return the XML from perf message list """

    # to avoid error from message length
    if len(perf_list) != 5:
        return None

    message = """<perf xmlns="http://www.projet-vigilo.org/messages">
    <timestamp>%(timestamp)s</timestamp>
    <host>%(host)s</host>
    <datasource>%(datasource)s</datasource>
    <value>%(value)s</value>
</perf>
"""


    dico = { "timestamp": perf_list[1],  # MUST
             "host": perf_list[2],       # MUST
             "datasource": perf_list[3], # MUST
             "value": perf_list[4],      # MUST
            }

    return message % dico

def state2xml(state_list):
    """ Called to return the XML from state message list """
    
    
    # to avoid error from message length
    if len(state_list) != 9:
        return None
    
    message = """<state xmlns="http://www.projet-vigilo.org/messages">
    <timestamp>%(timestamp)s</timestamp>
    <host>%(host)s</host>
    <ip>%(ip)s</ip>
    <service>%(service)s</service>
    <statename>%(statename)s</statename>
    <type>%(type)s</type>
    <attempt>%(attempt)s</attempt>
    <message>%(message)s</message>
</state>
"""

    dico = {"timestamp": state_list[1], # MUST
            "host": state_list[2],      # MUST
            "ip": state_list[3],        # MAY
            "service": state_list[4],   # MUST
            "statename": state_list[5], # MUST
            "type": state_list[6],      # MAY
            "attempt": state_list[7],   # MAY
            "message": state_list[8]    # MUST
            }
    return message % dico
         
