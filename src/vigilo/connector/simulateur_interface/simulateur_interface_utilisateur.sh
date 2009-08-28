#!/bin/bash
if [[ "$1" == "--help" || "$1" == "-h" ]] ; then
    exit 0
fi

socket=$1
if [ ! -n "$socket" ] ; then
    socket="/var/lib/vigilo/recv.sock"
fi

if [ -S "$socket" ] ; then
    killall -9 socat  &> /dev/null
    rm -f $socket
fi
socat -u UNIX-LISTEN:$socket,fork  STDOUT 

