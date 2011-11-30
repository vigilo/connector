# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2011-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>


from zope.interface import Interface, Attribute
from twisted.internet.interfaces import IPullProducer, IConsumer



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



class IBusProducer(IPullProducer):

    ready = Attribute(
        "Un Deferred qui se déclenche quand la connexion au bus est établie "
        "et qu'on peut donc commencer à demander des messages"
        )



#class IConsumer(Interface):
#    """
#    A consumer consumes data from a producer.
#    """
#
#    def registerProducer(producer, streaming):
#        """
#        Register to receive data from a producer.
#
#        This sets self to be a consumer for a producer.  When this object runs
#        out of data (as when a send(2) call on a socket succeeds in moving the
#        last data from a userspace buffer into a kernelspace buffer), it will
#        ask the producer to resumeProducing().
#
#        For L{IPullProducer} providers, C{resumeProducing} will be called once
#        each time data is required.
#
#        For L{IPushProducer} providers, C{pauseProducing} will be called
#        whenever the write buffer fills up and C{resumeProducing} will only be
#        called when it empties.
#
#        @type producer: L{IProducer} provider
#
#        @type streaming: C{bool}
#        @param streaming: C{True} if C{producer} provides L{IPushProducer},
#        C{False} if C{producer} provides L{IPullProducer}.
#
#        @return: C{None}
#        """
#
#    def unregisterProducer():
#        """
#        Stop consuming data from a producer, without disconnecting.
#        """
#
#    def write(data):
#        """
#        The producer will write data by calling this method.
#        """
#
#class IProducer(Interface):
#    """
#    A producer produces data for a consumer.
#
#    Typically producing is done by calling the write method of an class
#    implementing L{IConsumer}.
#    """
#
#    def stopProducing():
#        """
#        Stop producing data.
#
#        This tells a producer that its consumer has died, so it must stop
#        producing data for good.
#        """
#
#
#class IPushProducer(IProducer):
#    """
#    A push producer, also known as a streaming producer is expected to
#    produce (write to this consumer) data on a continous basis, unless
#    it has been paused. A paused push producer will resume producing
#    after its resumeProducing() method is called.   For a push producer
#    which is not pauseable, these functions may be noops.
#    """
#
#    def pauseProducing():
#        """
#        Pause producing data.
#
#        Tells a producer that it has produced too much data to process for
#        the time being, and to stop until resumeProducing() is called.
#        """
#    def resumeProducing():
#        """
#        Resume producing data.
#
#        This tells a producer to re-add itself to the main loop and produce
#        more data for its consumer.
#        """
#
#class IPullProducer(IProducer):
#    """
#    A pull producer, also known as a non-streaming producer, is
#    expected to produce data each time resumeProducing() is called.
#    """
#
#    def resumeProducing():
#        """
#        Produce data for the consumer a single time.
#
#        This tells a producer to produce data for the consumer once
#        (not repeatedly, once only). Typically this will be done
#        by calling the consumer's write() method a single time with
#        produced data.
#        """

