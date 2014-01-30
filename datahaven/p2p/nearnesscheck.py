#!/usr/bin/python
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#  PREPRO  - this is not our code and we need to replace or just remove
#  This is not so necessary as IP mappings to locations are getting very good.
#  But we would like to know if someone has at least 1 or 2 routers between them
#   and a supplier so there is good chance  they are not just in the same building.

#DHN can ask clients to do traceroutes to others and report the results.
#Results are probably a list of IP addresses to get there.
#With this we can get a good map of the routers/IPs for at least
#as much of the Internet as our customers cover.  This way we can make sure that
#we don't put all of a users backup sights in the same building.
#
#  ping
#  bandwidth - historical or run a test
#  latency   - historical or run a test
#
#
#On Linux, traceroute needs to be done as root.
# There is some python code out there that works on Windows and Linux.
#
#!python
#-----------------------------------------------------------------------------
# Name:        traceroute.py
# Purpose:     Trace route to host
#
# Author:      Joe Brown
#
# Created:     2003/21/03
# RCS-ID:      $Id: traceroute.py,v 1.1 2003/03/21 14:34:28 shmengie Exp $
# Copyright:   (c) 2003
# Licence:     GPL
#-----------------------------------------------------------------------------
import socket, sys, time, os.path
import lib.misc as misc; import lib.dhnio as dhnio

def traceroute(*args):
    argc = len(args[:])
    fqdn = True
    maxHops = 30
    if argc == 1:
        host=args[0]
    elif argc == 2:
        if args[0]=='-d':
            fqdn = False
            host = args[1]
        else:
            usage()
    else:
        usage()
    qport = 65500 # arbitrary port, hopefully not in use
    ttl = 1
    dest_ha = socket.gethostbyname(host)
    if dest_ha != host:
        print "Tracing route to %s (%s)" % (dest_ha, host)
    else:
        print "Tracing route to %s" % dest_ha
    while 1:
        print "%2d" % ttl,
        ha = '*'
        for i in range(3):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            if (dhnio.Windows()):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO, 300)
            s.setsockopt(socket.SOL_IP, socket.IP_TTL, ttl)

            s2 = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            s2.bind(('',qport))
            if (dhnio.Windows()):
                s2.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO, 300)
            addr = ""
            start = time.clock()
            s.sendto('', (host,qport))
            try:
                data, addr = s2.recvfrom(512)
                end = time.clock()
                wait = end - start
                ha=addr[0]
                print "%6.1f " % (wait * 1000),
            except:
                data = None
                addr = ("error", "error", "error")
                print "%8s " % '*',
            s.close()
            s2.close()
        print "%-16s" % ha,
        hname = ''
        if ha == '*':
            hname = '*'
        else:
            if fqdn:
                try:
                    hn = socket.gethostbyaddr(ha)
                    hname = hn[0]
                except:
                    pass
                if not hname or hname == ha:
                    hname = ''
        print hname
        ttl+=1
        if ttl > maxHops or ha == dest_ha :
            break

def usage():
    print >> sys.stderr, "%s [-d] target_host" % os.path.basename(sys.argv[0])
    print >> sys.stderr, " -d               No hostname resolution"
    sys.exit(1)
if __name__=='__main__':
    print "Must be run as root on Linux"
    traceroute(*sys.argv[1:])


