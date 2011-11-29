# -*- coding: utf-8 -*-
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
function to convert text to XML
"""

try:
    import json
except ImportError:
    from simplejson as json

#from twisted.words.xish import domish
from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate

#from vigilo.pubsub.xml import NS_AGGR, NS_EVENT, NS_PERF, NS_STATE, \
#                              NS_DOWNTIME, NS_COMMAND
#from vigilo.connector import MESSAGEONETOONE

_ = translate(__name__)

def serialize(text):
    """
    Sérialise un texte séparé par des I{pipes} en message Vigilo (JSON)
    @param text: Texte séparé par des I{pipes}
    @type  text: C{str}
    @return: Texte au format JSON
    @rtype:  C{str}
    """
    text = text.strip()
    try:
        text = unicode(text, 'utf8', errors='strict')
    except UnicodeDecodeError:
        text = unicode(text, 'iso-8859-15', errors='replace')

    if not elements:
        LOGGER.debug("Got empty line")
        return

    elements = text.split('|')
    if not elements:
        LOGGER.warning(_("Got malformed message: %s"))
        return

    try:
        msg_dict = msg2dict(elements)
        if msg_dict is None:
            return None
        #LOGGER.debug("Converted %s to %s", str(elements), msg.toXml())
        return json.dumps(msg_dict)

    except (TypeError, AttributeError):
        LOGGER.warning(_("Unknown/malformed message type: '%s'") %
                       elements[0])
        return None


def msg2dict(elements, type):
    msg_type = elements[0]
    d = {
        "type": msg_type,
        "timestamp": elements[1],
    }

    if msg_type == "event" and len(elements) == 6:
        d["host"] = elements[2],
        if elements[3] and elements[3].lower() != "host":
            d["service"] = elements[3]
        d["state"] = elements[4],
        d["message"] = elements[5],

    elif msg_type == "perf" and len(elements) == 5:
        d["host"] = elements[2],
        d["datasource"] = elements[3],
        d["value"] = elements[4],

    elif msg_type == "command" and len(elements) >= 3:
        d["cmdname"] = elements[2],
        d["value"] = "|".join(elements[3:]),

    elif msg_type == "state" and len(elements) == 9:
        d["host"] = elements[2],
        d["ip"] = elements[3],
        d["service"] = elements[4]
        d["code"] = elements[5],
        d["type"] = elements[6],
        d["attempt"] = elements[7],
        d["message"] = elements[8],

    else:
        LOGGER.warning(_("Unknown/malformed message type: '%s'") %
                       msg_type)
        return None

    return d

