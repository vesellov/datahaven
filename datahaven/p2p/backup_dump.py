#!/usr/bin/python
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
# This uses the Linux "dump" and "restore" commands.
#
# These need to be run as root since they access the filesystem via the raw device.
# Tried setting the sticky bit, but even then dump will not open the raw device.
# Can test as user with:
#       /sbin/dump -0 -f - /usr/share/man > /tmp/dump.1
#
# At the moment root does not seem to have the right path for twisted.

import datetime
import popen2
import os

#
#  We want a pipe output or input so we don't need to store intermediate data.
#
#  The popen starts another process.  That process can block but we don't.
#  blockmaker.py only takes data from this pipe when it is ready.

# Returns file descriptor for process that makes tar archive
def backup(directorypath):
    fdout,fdin = popen2.popen2("/sbin/dump -0 -f - %s" % (directorypath))

    print "dump pipe is open"
    return(fdout)
