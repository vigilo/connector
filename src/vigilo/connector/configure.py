# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2018 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

from __future__ import absolute_import

import os
import logging
import argparse

from configobj import ConfigObj
from zope.interface import implements

from twisted.internet import defer

from vigilo.connector.client import OneShotClient
from vigilo.connector.interfaces import IBusHandler

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate, translate_narrow
_ = translate(__name__)
N_ = translate_narrow(__name__)



class BusManager(object):
    """
    Classe contenant toutes les méthodes de gestion du bus
    """

    implements(IBusHandler)


    def __init__(self):
        self.client = None

    def run(self, client, args):
        self.client = client
        #args = self._preprocess(args)
        func = getattr(self, args.func)
        return func(args)

    def _preprocess(self, args):
        """ajoute le préfixe "vigilo" aux exchanges et au queues"""
        if (hasattr(args, "queue") and
                not args.queue.startswith("vigilo.")):
            args.queue = "vigilo.%s" % args.queue
        if (hasattr(args, "exchange") and
                not args.exchange.startswith("vigilo.")):
            args.exchange = "vigilo.%s" % args.exchange
        return args


    def create_queue(self, args):
        LOGGER.info(_("Creating queue %s"), args.queue)
        d = self.client.channel.queue_declare(queue=args.queue,
                durable=True, exclusive=False, auto_delete=False)
        return d

    def delete_queue(self, args):
        LOGGER.info(_("Deleting queue %s"), args.queue)
        d = self.client.channel.queue_delete(queue=args.queue)
        return d

    def create_exchange(self, args):
        LOGGER.info(_("Creating exchange %(exchange)s of type %(type)s"),
                    {"exchange": args.exchange, "type": args.type})
        d = self.client.channel.exchange_declare(exchange=args.exchange,
                type=args.type, durable=True)
        return d

    def delete_exchange(self, args):
        LOGGER.info(_("Deleting exchange %s"), args.exchange)
        d = self.client.channel.exchange_delete(exchange=args.exchange)
        return d

    def subscribe(self, args):
        key = args.key
        if not key:
            key = args.queue
        LOGGER.info(_("Subscribing queue %(queue)s to exchange %(exchange)s "
                      "(key: %(key)s)"),
                    {"queue": args.queue, "exchange": args.exchange, "key": key})
        d = self.client.channel.queue_bind(queue=args.queue,
                exchange=args.exchange, routing_key=key)
        return d

    def unsubscribe(self, args):
        key = args.key
        if not key:
            key = args.queue
        LOGGER.info(_("Unsubscribing queue %(queue)s from exchange "
                      "%(exchange)s (key: %(key)s)"),
                    {"queue": args.queue, "exchange": args.exchange, "key": key})
        d = self.client.channel.queue_unbind(queue=args.queue,
                exchange=args.exchange, routing_key=key)
        return d


    @defer.inlineCallbacks
    def read_file(self, args):
        filename = args.filename
        if not filename or not os.path.exists(filename):
            LOGGER.error(_("Can't find file '%s'"), filename)
            raise Exception(_("Can't find file '%s'") % filename)
        conf = ConfigObj(filename)
        yield defer.succeed(None) # au cas où il n'y aurait rien à faire

        for exchange in conf.sections:
            if not exchange.startswith("exchange:"):
                continue
            ename = exchange[len("exchange:"):]
            etype = conf[exchange].get("type", "fanout")
            LOGGER.info(_("Exchange %(name)s (%(type)s)"),
                        {"name": ename, "type": etype})
            yield self.client.channel.exchange_declare(
                    exchange=ename, type=etype, durable=True)

        for binding in conf.sections:
            if not binding.startswith("binding:"):
                continue
            exchange = conf[binding].get("exchange")
            queue = conf[binding].get("queue")
            key = conf[binding].get("key")
            LOGGER.info(_("Queue %s"), queue)
            yield self.client.channel.queue_declare(queue=queue,
                        durable=True, exclusive=False, auto_delete=False)
            LOGGER.info(_("Queue %(queue)s subscribed to exchange "
                          "%(exchange)s (key: %(key)s)"),
                        {"queue": queue, "exchange": exchange, "key": key})
            yield self.client.channel.queue_bind(queue=queue,
                        exchange=exchange, routing_key=key)



def parse_args():
    """
    Gestion des options de la ligne de commande et lancement du programme
    avec l'action demandée
    """
    common_args_parser = argparse.ArgumentParser()
    common_args_parser.add_argument("-s", "--server", default="localhost",
                                    help=N_("Server address"))
    common_args_parser.add_argument("-u", "--user", default="guest",
                                    help=N_("Bus user"))
    common_args_parser.add_argument("-p", "--password", default="guest",
                                    help=N_("Bus password"))
    common_args_parser.add_argument("-d", "--debug", action="store_true",
                                    help=N_('Show debugging information.'))

    parser = argparse.ArgumentParser(
                            add_help=False,
                            parents=[common_args_parser],
                            description=N_("Vigilo bus configurator"))
    subparsers = parser.add_subparsers(dest='action', title=N_("Subcommands"))

    # create-queue
    parser_cq = subparsers.add_parser("create-queue",
                    add_help=False,
                    parents=[common_args_parser],
                    help=N_("Create an AMQP queue on the server."))
    parser_cq.set_defaults(func="create_queue")
    parser_cq.add_argument('queue', help=N_("Queue name"))

    # delete-queue
    parser_dq = subparsers.add_parser("delete-queue",
                    add_help=False,
                    parents=[common_args_parser],
                    help=N_("Delete an AMQP queue on the server."))
    parser_dq.set_defaults(func="delete_queue")
    parser_dq.add_argument('queue', help=N_("Queue name"))

    # create-exchange
    parser_ce = subparsers.add_parser("create-exchange",
                    add_help=False,
                    parents=[common_args_parser],
                    help=N_("Create an AMQP exchange on the server."))
    parser_ce.set_defaults(func="create_exchange")
    parser_ce.add_argument('-t', '--type', default="fanout",
                    help=N_("Exchange type"))
    parser_ce.add_argument('exchange', help=N_("Exchange name"))

    # delete-exchange
    parser_de = subparsers.add_parser("delete-exchange",
                    add_help=False,
                    parents=[common_args_parser],
                    help=N_("Delete an AMQP exchange on the server."))
    parser_de.set_defaults(func="delete_exchange")
    parser_de.add_argument('exchange', help=N_("Exchange name"))

    # subscribe
    parser_sq = subparsers.add_parser("subscribe",
                    add_help=False,
                    parents=[common_args_parser],
                    help=N_("Subscribe a queue to an exchange."))
    parser_sq.set_defaults(func="subscribe")
    parser_sq.add_argument('queue', help=N_("Queue name"))
    parser_sq.add_argument('exchange', help=N_("Exchange name"))
    parser_sq.add_argument('-k', '--key', help=N_("Routing key"))

    # unsubscribe
    parser_uq = subparsers.add_parser("unsubscribe",
                    add_help=False,
                    parents=[common_args_parser],
                    help=N_("Unsubscribe a queue from an exchange."))
    parser_uq.set_defaults(func="unsubscribe")
    parser_uq.add_argument('queue', help=N_("Queue name"))
    parser_uq.add_argument('exchange', help=N_("Exchange name"))
    parser_uq.add_argument('-k', '--key', help=N_("Routing key"))

    # read-config
    parser_rc = subparsers.add_parser("read-config",
                    add_help=False,
                    parents=[common_args_parser],
                    help=N_("Reads the configuration from an INI file."))
    parser_rc.set_defaults(func="read_file")
    parser_rc.add_argument('filename', help=N_("Configuration file"))

    return parser.parse_args()



def main():
    args = parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        log_traffic = True
    else:
        logging.basicConfig(level=logging.INFO)
        log_traffic = False

    manager = BusManager()
    client = OneShotClient(hosts=args.server, user=args.user,
                           password=args.password, use_ssl=False)

    client.setHandler(manager.run, args)
    return client.run(log_traffic=log_traffic)

