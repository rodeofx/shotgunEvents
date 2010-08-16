#!/bin/sh -e
### BEGIN INIT INFO
# Provides:          shotgunEventDaemon
# Required-Start:    $local_fs $remote_fs $network $syslog
# Required-Stop:     $local_fs $remote_fs $network $syslog
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# X-Interactive:     true
# Short-Description: Start/stop shotgunEventDaemon
### END INIT INFO

. /lib/lsb/init-functions

case $1 in
	start)
		export PYTHONPATH=$PYTHONPATH$; $EXECUTABLE$
	;;
	stop)
		rm /var/log/shotgunEventDaemon.pid
	;;
	*)
		log_success_msg "Usage: /etc/init.d/shotgunEventDaemon {start|stop}"
		exit 1
	;;
esac
