# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2011-2012 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>
"""
Contient des extensions pour les classes de Twisted
afin d'améliorer le support pour IPv6.
"""

from __future__ import absolute_import

import socket # pylint: disable-msg=W0403
# W0403: Relative import 'socket', corrigé par le __future__.absolute_import
import warnings
from twisted.internet.udp import Port
from twisted.internet import udp, error

class IPv6CapableUDPPort(Port):
    """
    Cette classe permet d'envoyer des datagrammes UDP en utilisant
    l'une des familles d'adresses suivantes :
     - IPv4
     - IPv6
     - un nom d'hôte

    Pour cela, cette classe recrée un socket utilisant la famille
    d'adresses (AF_*) appropriée lorsque cela est nécessaire.
    """
    # pylint: disable-msg=W0223
    # W0223: Method 'writeSomeData' is abstract but is not overridden

    def write(self, datagram, addr=None):
        """Write a datagram.

        @param addr: should be a tuple (ip, port), can be None in connected mode.
        """
        if self._connectedAddr:
            assert addr in (None, self._connectedAddr)
            try:
                return self.socket.send(datagram)
            except socket.error, se:
                no = se.args[0]
                if no == udp.EINTR:
                    return self.write(datagram)
                elif no == udp.EMSGSIZE:
                    raise error.MessageLengthError, "message too long"
                elif no == udp.ECONNREFUSED:
                    self.protocol.connectionRefused()
                else:
                    raise
            return

        assert addr != None

        # Pas génial, mais c'est le seul moyen de corriger le tir.
        if ':' in addr[0]:
            if self.addressFamily != socket.AF_INET6:
                self.addressFamily = socket.AF_INET6
                if self.connected:
                    self.socket.close()
                self._bindSocket()
        elif '.' in addr[0]:
            if self.addressFamily != socket.AF_INET:
                self.addressFamily = socket.AF_INET
                if self.connected:
                    self.socket.close()
                self._bindSocket()
            if not addr[0].replace(".", "").isdigit():
                warnings.warn("Please only pass IPs to write(), not hostnames",
                    DeprecationWarning, stacklevel=2)

        try:
            return self.socket.sendto(datagram, addr)
        except socket.error, se:
            no = se.args[0]
            if no == udp.EINTR:
                return self.write(datagram, addr)
            elif no == udp.EMSGSIZE:
                raise error.MessageLengthError, "message too long"
            elif no == udp.ECONNREFUSED:
                # in non-connected UDP ECONNREFUSED is platform dependent, I think
                # and the info is not necessarily useful. Nevertheless maybe we
                # should call connectionRefused? XXX
                return
            else:
                raise

def ipv6_compatible_udp_port():
    """
    Modifie la classe utilisée pour se connecter en UDP.
    La nouvelle classe gère correctement l'IPv6.

    La classe C{twisted.internet.udp.Port} est appelée implicitement
    lorsqu'un nom d'hôte est passé là où une adresse est attendue,
    afin d'effectuer automatiquement une résolution DNS.
    """
    udp.Port = IPv6CapableUDPPort
