# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2011-2020 CS GROUP – France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

# les méthodes de ces classes n'ont pas "self" comme premier argument
# pylint: disable-msg=E0213

from zope.interface import Interface, Attribute
from twisted.internet.interfaces import IPullProducer



class InterfaceNotProvided(Exception):
    pass



class IBusHandler(Interface):
    """
    Un gestionnaire d'évènements du bus, tels que la connexion et la
    déconnexion.
    """

    client = Attribute(
        "Une référence à l'instance de C{VigiloClient} connectée au bus"
        )

    def setClient(client):
        """
        Enregistre le handler auprès du client. Il sera notifié des évènements
        survenant sur celui-ci.
        """


class IBusProducer(IPullProducer):

    ready = Attribute(
        "Un Deferred qui se déclenche quand la connexion au bus est établie "
        "et qu'on peut donc commencer à demander des messages"
        )
