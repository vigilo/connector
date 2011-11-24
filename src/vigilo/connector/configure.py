# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

from __future__ import absolute_import

import sys
import logging
import argparse

from twisted.internet import reactor, defer

from vigilo.connector.client import OneShotClient

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)

from vigilo.common.gettext import translate, translate_narrow
_ = translate(__name__)
N_ = translate_narrow(__name__)



class BusManager(object):

    def __init__(self):
        self.client = None

    def run(self, client, args):
        self.client = client
        func = getattr(self, args.func)
        return func(args)

    def create_queue(self, args):
        pass
    def delete_queue(self, args):
        pass

    def create_exchange(self, args):
        LOGGER.info(_("Creating exchange %s of type %s"),
                    args.exchange, args.type)
        d = self.client.chan.exchange_declare(
                exchange=args.exchange, type=args.type,
                durable=True, auto_delete=False)
        return d

    def delete_exchange(self, args):
        LOGGER.info(_("Deleting exchange %s"), args.exchange)
        d = self.client.chan.exchange_delete(exchange=args.exchange)
        return d

    def subscribe(self, args):
        pass
    def unsubscribe(self, args):
        pass


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
    parser_ce.add_argument('-t', '--type', default="direct",
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

    # unsubscribe
    parser_sq = subparsers.add_parser("unsubscribe",
                    add_help=False,
                    parents=[common_args_parser],
                    help=N_("Unsubscribe a queue from an exchange."))
    parser_sq.set_defaults(func="unsubscribe")
    parser_sq.add_argument('queue', help=N_("Queue name"))
    parser_sq.add_argument('exchange', help=N_("Exchange name"))

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
    client = OneShotClient(host=args.server, user=args.user,
                           password=args.password, use_ssl=False)

    client.setHandler(manager.run, args)
    return client.run(log_traffic=log_traffic)

