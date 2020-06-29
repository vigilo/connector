#!/bin/bash
# Copyright (C) 2011-2020 CS GROUP – France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

if [[ "$1" == "--help" || "$1" == "-h" ]] ; then
    exit 0
fi

socket=$1
if [ ! -n "$socket" ] ; then
    socket="/var/lib/vigilo/connector/recv.sock"
fi

if [ -S "$socket" ] ; then
    killall -9 socat  &> /dev/null
    rm -f $socket
fi
socat -u UNIX-LISTEN:$socket,fork  STDOUT 

