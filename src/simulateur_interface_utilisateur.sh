killall -9 socat  &> /dev/null
rm -f /tmp/testW
rm -f /tmp/test2W
socat -u  UNIX-LISTEN:/tmp/testW,fork  STDOUT &
socat -u  UNIX-LISTEN:/tmp/test2W,fork  STDOUT &

