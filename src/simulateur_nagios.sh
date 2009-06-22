for i in `seq 1`; do
    cat fichier_texte.txt | socat - /tmp/test
done
