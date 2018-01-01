# -*- coding: utf-8 -*-
# Copyright (C) 2006-2018 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
function to convert text to dict
"""

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate
_ = translate(__name__)


def parseMessage(text):
    """
    Sérialise un texte séparé par des I{pipes} en message Vigilo (C{dict})
    @param text: Texte séparé par des I{pipes}
    @type  text: C{str}
    @return: Message parsé dans un dictionnaire
    @rtype:  C{str}
    """
    text = text.strip()
    if not text:
        LOGGER.debug("Got empty line")
        return

    try:
        text = unicode(text, 'utf8', errors='strict')
    except UnicodeDecodeError:
        text = unicode(text, 'iso-8859-15', errors='replace')

    elements = text.split('|')
    if not elements:
        LOGGER.warning(_("Got malformed message: %s"))
        return

    try:
        msg_dict = msg2dict(elements)
        if msg_dict is None:
            return None
        #LOGGER.debug("Converted %s to %s", str(elements), msg.toXml())
        return msg_dict

    except (TypeError, AttributeError, IndexError):
        LOGGER.warning(_("Unknown/malformed message type: '%s'") %
                       elements[0])
        return None


def msg2dict(elements):
    msg_type = elements[0]
    d = {
        "type": msg_type,
        "timestamp": elements[1],
    }

    size = len(elements)
    if msg_type == "event" and 6 <= size <= 7:
        d["host"] = elements[2]
        if elements[3] and elements[3].lower() != "host":
            d["service"] = elements[3]
        d["state"] = elements[4]
        d["message"] = elements[5]
        if size == 7 and elements[6]:
            d["routing_key"] = elements[6]

    elif msg_type == "perf" and 5 <= size <= 6:
        d["host"] = elements[2]
        d["datasource"] = elements[3]
        d["value"] = elements[4]
        if size == 6 and elements[5]:
            d["routing_key"] = elements[5]

    elif msg_type == "nagios" and size >= 3:
        d["cmdname"] = elements[2]
        d["value"] = ";".join(elements[3:])
        #d["routing_key"] = "all"
        if (d["cmdname"].startswith("PROCESS_")
                and d["cmdname"].endswith("_CHECK_RESULT")):
            d["host"] = elements[3]

    elif msg_type == "state" and 9 <= size <= 10:
        d["host"] = elements[2]
        d["ip"] = elements[3]
        d["service"] = elements[4]
        d["code"] = elements[5]
        d["statetype"] = elements[6]
        d["attempt"] = elements[7]
        d["message"] = elements[8]
        if size == 10 and elements[9]:
            d["routing_key"] = elements[9]

    else:
        LOGGER.warning(_("Unknown/malformed message type: '%s'") %
                       msg_type)
        return None

    return d

