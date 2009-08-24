# -*- coding: utf-8 -*-
from wokkel.generic import parseXml
import base64
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

def logguage(text, facility=None):
    """  Call to log evenements to the syslog """
    #syslog.syslog(LEVELS['info'], text)
    #print (text)
    LOGGER.info(text.encode('utf8'))


def encode(data):
    """ Encode data using Base64. """
    return base64.b64encode(data)

def decode(data):
    """ Decode data using Base64 """
    return base64.b64decode(data)

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
                # ligne vide
                logguage("ligne vide")
                return None
            if elements[0] == "event":
                return parseXml(event2xml(elements)).toXml()
            elif elements[0] == "perf":
                return parseXml(perf2xml(elements)).toXml()
            elif elements[0] == "state":
                return parseXml(state2xml(elements)).toXml()
            else:
                logguage("type de message inconnue")
                return None
        except TypeError, AttributeError:
            logguage("type de message inconnue %s" % elements)
            return None
    else:
        logguage("type de message inconnue")
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
         
