#!/bin/bash
if [[ "$1" == "--help" || "$1" == "-h" ]] ; then
    exit 0
fi

socket=$1
if [  ! -e "$socket" ] ; then
    socket="/tmp/socketR"
fi
if [ ! -S "$socket" ] ; then
    echo "fichier $socket non présent"
    exit 1
fi

for file in error.txt event_incomplet.txt event.txt perf.txt state.txt state_incomplet.txt; do 
    cat  $file | socat - UNIX-CONNECT:$socket
done
