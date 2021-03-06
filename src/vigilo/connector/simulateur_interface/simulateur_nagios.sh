#!/bin/bash
# Copyright (C) 2011-2020 CS GROUP - France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

if [[ "$1" == "--help" || "$1" == "-h" ]] ; then
    exit 0
fi

socket=$1
if [  ! -e "$socket" ] ; then
    socket="/var/lib/vigilo/connector/send.sock"
fi
if [ ! -S "$socket" ] ; then
    echo "fichier $socket non présent"
    exit 1
fi

for file in error.txt event_incomplet.txt event.txt perf.txt state.txt state_incomplet.txt; do 
    cat  $file | socat - UNIX-CONNECT:$socket
done
