#!/usr/bin/python
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#
# SUPPLIERPATROL.PY
#
# We patrol the suppliers we have and make sure they are all working well, or we work
# out the problems.  Working out problems may be fixing one missing packet, or
# replacing a supplier and rebuilding all the data he had (or not).
#
# We keep on disk the most recent "ListFiles" from each supplier.
# We can look for any missing packets in the list (maybe deleted from bitrot or never got through).
#
# Different tests we can do to check that remote nodes are working the way we want them to.
#
#   1)  We ask them to "listfiles" and see that they all give the same answers (unless in middle of backup)
#   2)  We can read random remote dhnpackets and check digital signatures.
#       This is very simple, and probably all we really need to do.
#   3)  We can use one parity and the data packets for it and check that parity works.
#          If parity does not work, we have at least one bad node.
#          Should really have shown up in signature test already (done as part of reading packets).
#
#          There is a chance that a header was corrupted.  Could use other parities to check which
#          packet is causing problem.
#   4)  We can just ask them to send their identity and see that they do (sort of ping)
#
# We also keep track of bandwidth we got from different sites.
# Information we collect helps "fire_hire" decide if some supplier needs to be fired.
#
# We need to know BackupIDs and max BlockNumber so we can fetch in right range.

import os
import time


#from twisted.internet.defer import Deferred


import lib.dhnio as dhnio
import lib.misc as misc
import lib.settings as settings
import lib.contacts as contacts
import lib.transport_control as transport_control

import lib.commands as commands
import lib.dhnpacket as dhnpacket


#-------------------------------------------------------------------------------


def fileAgeInSeconds(filename):
    now=time.time()
    filemtime = os.path.getmtime(filename)
    age = now - filemtime
    if (age<0):
        age=0
    return(age)


NumRequestsOutstanding=0
TestDeferred=""

def ListResult(packet):
    dhnio.Dprint(7, "supplierpatrol.ListResult got result from " + packet.OwnerID)
    supnum=contacts.numberForSupplier(packet.OwnerID)
    filename= os.path.join(settings.FileListDir(), str(supnum))
    dhnio.WriteFile(filename, packet.Data)
    global NumRequestsOutstanding
    NumRequestsOutstanding -= 1
    dhnio.Dprint(7, "supplierpatrol.ListResult  NumRequestsOutstanding = " + str(NumRequestsOutstanding))
    CheckCallback()

def CheckCallback():
    global TestDeferred
    global DataResultsOutstanding
    if (NumRequestsOutstanding == 0 and len(DataResultsOutstanding)==0 and TestDeferred != ""):
        TestDeferred.callback(1)

# We refetch any ListFiles result that is too old, or maybe fire a supplier.
def UpdateListFiles():
    if (not os.path.exists(settings.FileListDir())):
        os.mkdir(settings.FileListDir())
    for supnum in range(0, contacts.numSuppliers()):
        filename= os.path.join(settings.FileListDir(), str(supnum))
        dhnio.Dprint(7, "supplierpatrol.UpdateListFiles  looking at = " + filename)
        if (not os.path.exists(filename) or (fileAgeInSeconds(filename) > 3600*24)):
            dhnio.Dprint(7, "supplierpatrol.UpdateListFiles  found one to update " + filename)
            command=commands.ListFiles()
            OwnerID=misc.getLocalID()
            CreatorID=misc.getLocalID()
            PacketID="ListFiles" + str(supnum)
            Payload=""
            RemoteID= contacts.getSupplierID(supnum)
            request=dhnpacket.dhnpacket(command, OwnerID, CreatorID, PacketID, Payload, RemoteID)
            transport_control.RegisterInterest(ListResult, RemoteID, PacketID)
            transport_control.outboxAck(request)
            global NumRequestsOutstanding
            NumRequestsOutstanding += 1
            dhnio.Dprint(7, "supplierpatrol.UpdateListFiles  sent request - now outstanding=" + str(NumRequestsOutstanding))


DataResultsOutstanding=[]

def DataResult(packet):
    dhnio.Dprint(7, "supplierpatrol.DataResult  got" + packet.PacketID)
    global DataResultsOutstanding
    DataResultsOutstanding.remove(packet.PacketID)
    CheckCallback()

#
def OneFromList(filename):
    WholeFile=dhnio.ReadBinaryFile(filename)
    FileList=WholeFile.split("\n")
    num=len(FileList)
    dhnio.Dprint(7, "supplierpatrol.OneFromList  number of items is " + str(num))
    rnd=random.randint(0,num-1)
    item=FileList[rnd]
    command=commands.Data()
    OwnerID=misc.getLocalID()
    CreatorID=misc.getLocalID()
    PacketID=item
    Payload=""
    supnum=packetid.SupplierNumber(item)
    RemoteID=contacts.getSupplierID(supnum)
    request=dhnpacket.dhnpacket(command, OwnerID, CreatorID, PacketID, Payload, RemoteID)
    global DataResultsOutstanding
    DataResultsOutstanding.append(item)
    transport_control.RegisterInterest(DataResult, RemoteID, PacketID)
    transport_control.outboxAck(request)

# Randomly test read a file.  Need to see that we really get it and
# that it has a good checksum.  For now we ask for 1 from each supplier.
# We just work off the files they say they have.
def RandomSample():
    for supnum in range(0, contacts.numSuppliers()):
        filename= os.path.join(settings.FileListDir(), str(supnum))
        if (os.path.exists(filename)):
            OneFromList(filename)



# REBUILDRANGE - range of packets for a node (probably only 1 or all for node)
#  Most common case will probably be after we replace a node, but sometimes
#  this will be used to repair bitrot damage.
#
# To rebuild we will read several data and one parity packet.  We first
# find minimal size parity to rebuild and do the rebuild.  We might have some
# cache of packets, but probably we need to fetch all data and parity we will use.
# So we probably want a parity with the smallest number of components that
# includes the one we are trying to fix.
#
# There may be times when there are several broken nodes and we would like
# to find the set of parities with the most nodes in common to reduce the
# total number of reads.
#
# Note also that the plan may need to change partway through as some
# new node failure may occure.
#
# Danger is that failures come in faster than we can fix them.  If this is
# happening, we need a plan-B, which is to call a Professional Scrubber.
# those guys have plenty of bandwidth and can get your data cleaned up fast.
#
# PREPRO

##class supplierpatroltest(unittest.TestCase):
##    def test_supplierpatrol(self):
##        dhninit.init()
##        UpdateListFiles()
##        global TestDeferred
##        TestDeferred=Deferred()
##        return(TestDeferred)

