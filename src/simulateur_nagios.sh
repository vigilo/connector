for file in error.txt event_incomplet.txt event.txt perf.txt ; do 
    cat  $file | socat - UNIX-CONNECT:/tmp/testR
done
