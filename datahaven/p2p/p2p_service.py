#!/usr/bin/python
#p2p_service.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#
# This serves requests from customers.
#     Data          - save packet to a file      (a commands.Data() packet)
#     Retrieve      - read packet from a file    (a commands.Data() packet)
#     ListFiles     - list files we have for customer
#     Delete        - delete a file
#     Identity      - contact or id server sending us a current identity
#
# For listed customers we will save and retrieve data up to their specified limits.
#   DHN tells us who our customers are and limits, we get their identities.
#   If a customer does not contact us for more than 30 hours (or something) then we can process
#       requests from that customers scrubbers
#
# Security:
#
#     Transport_control has checked that it is signed by a contact, 
#       but we need to check that this is a customer.
#
#     Since we have control over suppliers, and may not change them much,
#       it feels like customers are more of a risk.
#
#     Code treats suppliers and customers differently.  Fun that stores
#       have customers come in the front door and suppliers in the back door.
#     But I don't see anything really worth doing.
#         On Unix machines we could run customers in a chrooted environment.
#         There would be a main datahaven code and any time it got a change
#         in the list of customers, it could restart the customer code.
#         The customer code could be kept very small this way.
#         Again, I doubt it.  We only have XML and binary.
#     Real risk is probably the code for SSH, Email, Vetex, etc.
#         Once it is a dhnpacket object, we are probably ok.
#
#  We will store in a file and be able to read it back when requested.
#  Request comes as a dhnpacket and we just
#
#  Resource limits - localtester checks that someone is not trying to use more than they are supposed to
#                  - we could also do it here .   PREPRO
#

import os
import sys
import time
import cStringIO
import zlib

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in p2p_service.py')

from twisted.internet.defer import Deferred

try:
    import lib.dhnio as dhnio
except:
    dirpath = os.path.dirname(os.path.abspath(sys.argv[0]))
    sys.path.insert(0, os.path.abspath('datahaven'))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..')))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..', '..')))
    try:
        import lib.dhnio as dhnio
    except:
        sys.exit()

import lib.dhnpacket as dhnpacket
import lib.contacts as contacts
import lib.commands as commands
import lib.misc as misc
import lib.eccmap as eccmap
import lib.settings as settings
import lib.transport_control as transport_control
import lib.identity as identity
import lib.identitycache as identitycache
import lib.packetid as packetid
import lib.nameurl as nameurl


import message
import local_tester
import backup_matrix
import backup_control
import central_service
#import summary


_TrafficInFunc = None
_TrafficOutFunc = None

#_InboxStatusIOThrottleFunc = None
#_OutboxStatusIOThrottleFunc = None

#------------------------------------------------------------------------------

def SetTrafficInFunc(f):
    global _TrafficInFunc
    _TrafficInFunc = f

def SetTrafficOutFunc(f):
    global _TrafficOutFunc
    _TrafficOutFunc = f

#------------------------------------------------------------------------------

def init():
    dhnio.Dprint(4, 'p2p_service.init')
    transport_control.AddInboxCallback(inbox)
    transport_control.AddInboxPacketStatusFunc(inbox_status)
    transport_control.AddOutboxPacketStatusFunc(outbox_status)
    transport_control.SetMessageFunc(message2gui)

#------------------------------------------------------------------------------

def inbox(newpacket, proto='', host=''):
    if newpacket.Command == commands.Identity():
        # contact sending us current identity we might not have
        # so we handle it before check that packet is valid
        # because we might not have his identity on hands and so can not verify the packet  
        # so we check that his Identity is valid and save it into cache
        # than we check the packet to be valid too.
        Identity(newpacket)            
        return True

    # check that signed by a contact of ours
    if not newpacket.Valid():              
        dhnio.Dprint(1, 'p2p_service.inbox ERROR new packet is not Valid')
        return False
  
    if newpacket.CreatorID != misc.getLocalID() and newpacket.RemoteID != misc.getLocalID():
        dhnio.Dprint(1, "p2p_service.inbox  ERROR packet is NOT for us")
        dhnio.Dprint(1, "p2p_service.inbox  getLocalID=" + misc.getLocalID() )
        dhnio.Dprint(1, "p2p_service.inbox  CreatorID=" + newpacket.CreatorID )
        dhnio.Dprint(1, "p2p_service.inbox  RemoteID=" + newpacket.RemoteID )
        dhnio.Dprint(1, "p2p_service.inbox  PacketID=" + newpacket.PacketID )
        return False

    handled = inboxPacket(newpacket, proto, host)
    if handled:
        dhnio.Dprint(12, "p2p_service.inbox [%s] from %s|%s (%s://%s) handled" % (
            newpacket.Command, nameurl.GetName(newpacket.CreatorID), nameurl.GetName(newpacket.OwnerID), proto, host))

    return handled


# Packet has been checked and is Valid()
def inboxPacket(newpacket, proto, host):
    commandhandled = False
    if newpacket.Command == commands.Fail():
        Fail(newpacket)
        commandhandled = True

    elif newpacket.Command == commands.Retrieve():
        # retrieve some packet customer stored with us
        Retrieve(newpacket)
        commandhandled = True

    elif newpacket.Command == commands.Ack():
        # With Ack we just need FindInterestedParty() below
        commandhandled = True

    elif newpacket.Command == commands.Data():
        # new packet to store for customer
        Data(newpacket)
        commandhandled = True

    elif newpacket.Command == commands.ListFiles():
        # customer wants list of their files
        ListFiles(newpacket)
        commandhandled = True

    elif newpacket.Command == commands.Files():
        # supplier sent us list of files
        Files(newpacket)
        commandhandled = True

    elif newpacket.Command == commands.DeleteFile():
        # will Delete a customer file for them
        DeleteFile(newpacket)
        commandhandled = True

    elif newpacket.Command == commands.DeleteBackup():
        # will Delete all files starting in a backup
        DeleteBackup(newpacket)
        commandhandled = True

    elif newpacket.Command == commands.RequestIdentity():
        # contact asking for our current identity
        RequestIdentity(newpacket)
        commandhandled = True

    elif newpacket.Command == commands.Message():
        # someone sent us a message
        message.Message(newpacket)
        commandhandled = True

    elif newpacket.Command == commands.Correspondent():
        # someone want to be our correspondent
        Correspondent(newpacket)

    return commandhandled


def outbox(outpacket):
    dhnio.Dprint(8, "p2p_service.outbox [%s] to %s" % (outpacket.Command, nameurl.GetName(outpacket.RemoteID)))
    return True


def inbox_status(newpacket, status, proto, host, error, message):
    global _TrafficInFunc
    if _TrafficInFunc is not None:
        _TrafficInFunc(newpacket, status, proto, host, error, message)


def outbox_status(workitem, proto, host, status, error, message):
    global _TrafficOutFunc
    if _TrafficOutFunc is not None:
        _TrafficOutFunc(workitem, proto, host, status, error, message)

#------------------------------------------------------------------------------ 

def constructFilename(customerID, packetID):
    customerDirName = nameurl.UrlFilename(customerID)
    customersDir = settings.getCustomersFilesDir()
    if not os.path.exists(customersDir):
        dhnio._dir_make(customersDir)
    ownerDir = os.path.join(customersDir, customerDirName)
    if not os.path.exists(ownerDir):
        dhnio._dir_make(ownerDir)
    filename = os.path.join(ownerDir, packetID)
    return filename

# Must be a customer, and then we make full path filename for where this packet is stored locally
# SECURITY
def makeFilename(customerID, packetID):
    if not packetid.Valid(packetID): # SECURITY
        if packetID not in [    settings.BackupInfoFileName(), 
                                settings.BackupInfoFileNameOld(), 
                                settings.BackupInfoEncryptedFileName(), 
                                settings.BackupIndexFileName() ]:
            # dhnio.Dprint(1, "p2p_service.makeFilename ERROR failed packetID format: " + packetID )
            return ''
    if not contacts.IsCustomer(customerID):  # SECURITY
        dhnio.Dprint(4, "p2p_service.makeFilename WARNING %s not a customer: %s" % (customerID, str(contacts.getCustomerNames())))
        return ''
    return constructFilename(customerID, packetID)

#------------------------------------------------------------------------------

def Fail(request):
    dhnio.Dprint(6, "p2p_service.Fail from [%s]: %s" % (request.CreatorID, request.Payload))
    

# this is when we 
# 1. save my requested data to restore the backup 
# or 
# 2. save the customer file on our local HDD 
def Data(request):
    # 1. this is our Data! 
    if request.OwnerID == misc.getLocalID():
        if request.PacketID in [ settings.BackupIndexFileName(), ]:
            backup_control.IncomingSupplierBackupIndex(request)
#        elif request.PacketID in [ settings.BackupInfoFileName(), settings.BackupInfoFileNameOld(), settings.BackupInfoEncryptedFileName(), ]:
#            return
        return
    # 2. this Data is not belong to us
    if not contacts.IsCustomer(request.OwnerID):  # SECURITY
        # may be we did not get the ListCustomers packet from the Central yet?
        dhnio.Dprint(6, "p2p_service.Data WARNING %s not a customer, packetID=%s" % (request.OwnerID, request.PacketID))
        central_service.SendRequestCustomers()
        return 
    filename = makeFilename(request.OwnerID, request.PacketID)
    if filename == "":
        transport_control.SendFail(request, 'empty filename, you are not a customer maybe?')
        dhnio.Dprint(6,"p2p_service.Data WARNING got empty filename, bad customer or wrong packetID? ")
        return
    dirname = os.path.dirname(filename)
    if not os.path.exists(dirname):
        try:
            dhnio._dirs_make(dirname)
        except:
            dhnio.Dprint(2, "p2p_service.Data ERROR can not create sub dir " + dirname)
            transport_control.SendFail(request, 'write error')
            return 
    data = request.Serialize()
    if not dhnio.WriteFile(filename, data):
        dhnio.Dprint(2, "p2p_service.Data ERROR can not write to " + str(filename))
        transport_control.SendFail(request, 'write error')
        return
    transport_control.SendAck(request, str(len(request.Payload)))
    reactor.callLater(3, local_tester.TestSpaceTime)
    del data
    dhnio.Dprint(8, "p2p_service.Data saved from [%s/%s], packetID is %s" % (
        nameurl.GetName(request.OwnerID), nameurl.GetName(request.CreatorID), request.PacketID,))


# Delete one ore multiple files or folders
def DeleteFile(request):
    if request.Payload == '':
        ids = [request.PacketID]
    else:
        ids = request.Payload.split('\n')
    filescount = 0
    dirscount = 0
    for pathID in ids:
        filename = makeFilename(request.OwnerID, pathID)
        if filename == "":
            filename = constructFilename(request.OwnerID, pathID)
            if not os.path.exists(filename):
                dhnio.Dprint(1, "p2p_service.DeleteFile WARNING had unknown customer: %s or pathID is not correct or not exist: %s" % (nameurl.GetName(request.OwnerID), pathID))
                return
        if os.path.isfile(filename):
            try:
                os.remove(filename)
                filescount += 1
            except:
                dhnio.DprintException()
        elif os.path.isdir(filename):
            try:
                dhnio._dir_remove(filename)
                dirscount += 1
            except:
                dhnio.DprintException()
        else:
            dhnio.Dprint(1, "p2p_service.DeleteFile WARNING path not found %s" % filename)
    dhnio.Dprint(6, "p2p_service.DeleteFile from [%s] with %d IDs, %d files and %d folders were removed" % (
        nameurl.GetName(request.OwnerID), len(ids), filescount, dirscount))
    transport_control.SendAck(request)
    

def SendDeleteFile(SupplierID, pathID):
    dhnio.Dprint(6, "p2p_service.SendDeleteFile SupplierID=%s PathID=%s " % (SupplierID, pathID))
    MyID = misc.getLocalID()
    PacketID = pathID
    RemoteID = SupplierID
    result = dhnpacket.dhnpacket(commands.DeleteFile(),  MyID, MyID, PacketID, "", RemoteID)
    transport_control.outboxAck(result)
    
    
def SendDeleteListPaths(SupplierID, ListPathIDs):
    dhnio.Dprint(6, "p2p_service.SendDeleteListPaths SupplierID=%s PathIDs number: %d" % (SupplierID, len(ListPathIDs)))
    MyID = misc.getLocalID()
    PacketID = packetid.UniqueID()
    RemoteID = SupplierID
    Payload = '\n'.join(ListPathIDs)
    result = dhnpacket.dhnpacket(commands.DeleteFile(),  MyID, MyID, PacketID, Payload, RemoteID)
    transport_control.outboxAck(result)


# Delete one or multiple backups
def DeleteBackup(request):
    if request.Payload == '':
        ids = [request.PacketID]
    else:
        ids = request.Payload.split('\n')
    count = 0
    for backupID in ids:
        filename = makeFilename(request.OwnerID, backupID)
        if filename == "":
            filename = constructFilename(request.OwnerID, backupID)
            if not os.path.exists(filename):
                dhnio.Dprint(1, "p2p_service.DeleteBackup WARNING had unknown customer " + request.OwnerID + " or backupID " + backupID)
                return
        if os.path.isdir(filename):
            try:
                dhnio._dir_remove(filename)
                count += 1
            except:
                dhnio.DprintException()
        elif os.path.isfile(filename):
            try:
                os.remove(filename)
                count += 1
            except:
                dhnio.DprintException()
        else:
            dhnio.Dprint(1, "p2p_service.DeleteBackup WARNING path not found %s" % filename)
    transport_control.SendAck(request)
    dhnio.Dprint(6, "p2p_service.DeleteBackup from [%s] with %d IDs, %d were removed" % (nameurl.GetName(request.OwnerID), len(ids), count))


def SendDeleteBackup(SupplierID, BackupID):
    dhnio.Dprint(6, "p2p_service.SendDeleteBackup SupplierID=%s  BackupID=%s " % (SupplierID, BackupID))
    MyID = misc.getLocalID()
    PacketID = BackupID
    RemoteID = SupplierID
    result = dhnpacket.dhnpacket(commands.DeleteBackup(),  MyID, MyID, PacketID, "", RemoteID)
    transport_control.outboxAck(result)

def SendDeleteListBackups(SupplierID, ListBackupIDs):
    dhnio.Dprint(6, "p2p_service.SendDeleteListBackups SupplierID=%s BackupIDs number: %d" % (SupplierID, len(ListBackupIDs)))
    MyID = misc.getLocalID()
    PacketID = packetid.UniqueID()
    RemoteID = SupplierID
    Payload = '\n'.join(ListBackupIDs)
    result = dhnpacket.dhnpacket(commands.DeleteBackup(),  MyID, MyID, PacketID, Payload, RemoteID)
    transport_control.outboxAck(result)


# Contact or identity server is sending us a new copy of an identity for a contact of ours
def Identity(newpacket):
    newxml = newpacket.Payload
    newidentity = identity.identity(xmlsrc=newxml)

    # SECURITY - check that identity is signed correctly
    if not newidentity.Valid():
        dhnio.Dprint(1,"p2p_service.Identity ERROR has non-Valid identity")
        return

    idurl = newidentity.getIDURL()

    if contacts.isKnown(idurl):
        # This checks that old public key matches new
        identitycache.UpdateAfterChecking(idurl, newxml)

    else:
        # TODO
        # may be we need to make some temporary storage
        # for identities who we did not know yet
        # just to be able to receive packets from them
        identitycache.UpdateAfterChecking(idurl, newxml)

    # Now that we have ID we can check packet
    if not newpacket.Valid():
        # If not valid do nothing
        dhnio.Dprint(6, "p2p_service.Identity WARNING not Valid packet from %s" % idurl)
        return

    if newpacket.OwnerID == idurl:
        transport_control.SendAck(newpacket)
        dhnio.Dprint(6, "p2p_service.Identity from [%s], sent Ack" % nameurl.GetName(idurl))
    else:
        dhnio.Dprint(6, "p2p_service.Identity from [%s]" % nameurl.GetName(idurl))


# Someone is requesting a copy of our current identity.
# Transport_control has verified that they are a contact.
# Can also be used as a sort of "ping" test to make sure we are alive.
def RequestIdentity(request):
    dhnio.Dprint(6, "p2p_service.RequestIdentity starting")
    MyID = misc.getLocalID()
    RemoteID = request.OwnerID
    PacketID = request.PacketID
    identitystr = misc.getLocalIdentity().serialize()
    dhnio.Dprint(12, "p2p_service.RequestIdentity returning ")
    result = dhnpacket.dhnpacket(commands.Identity(), MyID, MyID, PacketID, identitystr, RemoteID)
    transport_control.outboxNoAck(result)
    
    
#  Customer is asking us for data he previously stored with us.
#  We send with outboxNoAck because he will ask again if he does not get it
def Retrieve(request):
    filename = makeFilename(request.OwnerID, request.PacketID)
    if filename == '':
        dhnio.Dprint(4, "p2p_service.Retrieve WARNING had unknown customer " + request.OwnerID)
        transport_control.SendFail(request, 'empty filename, not a customer?')
        return
    if not os.path.exists(filename):
        dhnio.Dprint(4, "p2p_service.Retrieve WARNING did not find requested packet " + filename)
        # transport_control.outboxNoAck(dhnpacket.dhnpacket(commands.Fail(), request.OwnerID, misc.getLocalID(), request.PacketID, 'did not find requested packet', request.CreatorID))
        transport_control.SendFail(request, 'did not find requested packet')
        return
    if not os.access(filename, os.R_OK):
        dhnio.Dprint(4, "p2p_service.Retrieve WARNING no read access to requested packet " + filename)
        # transport_control.outboxNoAck(dhnpacket.dhnpacket(commands.Fail(), request.OwnerID, misc.getLocalID(), request.PacketID, 'no read access to requested packet', request.CreatorID))
        transport_control.SendFail(request, 'no read access to requested packet')
        return
    data = dhnio.ReadBinaryFile(filename)
    if not data:
        dhnio.Dprint(4, "p2p_service.Retrieve WARNING empty data on disk " + filename)
        # transport_control.outboxNoAck(dhnpacket.dhnpacket(commands.Fail(), request.OwnerID, misc.getLocalID(), request.PacketID, 'empty data on disk', request.CreatorID))
        transport_control.SendFail(request, 'empty data on disk')
        return
    packet = dhnpacket.Unserialize(data)
    del data 
    if packet is None:
        dhnio.Dprint(4, "p2p_service.Retrieve WARNING Unserialize fails, not Valid packet " + filename)
        # transport_control.outboxNoAck(dhnpacket.dhnpacket(commands.Fail(), request.OwnerID, misc.getLocalID(), request.PacketID, 'unserialize fails', request.CreatorID))
        transport_control.SendFail(request, 'unserialize fails')
        return
    if not packet.Valid():
        dhnio.Dprint(4, "p2p_service.Retrieve WARNING unserialized packet is not Valid " + filename)
        # transport_control.outboxNoAck(dhnpacket.dhnpacket(commands.Fail(), request.OwnerID, misc.getLocalID(), request.PacketID, 'unserialized packet is not Valid', request.CreatorID))
        transport_control.SendFail(request, 'unserialized packet is not Valid')
        return
    dhnio.Dprint(6, "p2p_service.Retrieve sending [%s] back to %s" % (packet.PacketID, nameurl.GetName(packet.CreatorID)))
    transport_control.outboxNoAck(packet)


# We will want to use this to see what needs to be resent, and expect normal case is very few missing.
# This is to build the Files we are holding for a customer
def ListFiles(request):
    MyID = misc.getLocalID()
    RemoteID = request.OwnerID
    PacketID = request.PacketID
    Payload = request.Payload
    dhnio.Dprint(8, "p2p_service.ListFiles from [%s], format is %s" % (nameurl.GetName(request.OwnerID), Payload))
    custdir = settings.getCustomersFilesDir()
    ownerdir = os.path.join(custdir, nameurl.UrlFilename(request.OwnerID))
    if not os.path.isdir(ownerdir):
        dhnio.Dprint(8, "p2p_service.ListFiles did not find customer dir " + ownerdir)
        src = PackListFiles('', Payload)
        result = dhnpacket.dhnpacket(commands.Files(), MyID, MyID, PacketID, src, RemoteID)
        transport_control.outboxNoAck(result)
        return
    plaintext = TreeSummary(ownerdir)
    src = PackListFiles(plaintext, Payload)
    outpacket = dhnpacket.dhnpacket(commands.Files(), MyID, MyID, PacketID, src, RemoteID)
    transport_control.outboxNoAck(outpacket)


# A directory list came in from some supplier
def Files(packet):
    dhnio.Dprint(8, "p2p_service.Files from [%s]" % nameurl.GetName(packet.OwnerID))
    backup_control.IncomingSupplierListFiles(packet)


def Correspondent(request):
    dhnio.Dprint(6, "p2p_service.Correspondent")
    MyID = misc.getLocalID()
    RemoteID = request.OwnerID
    PacketID = request.PacketID
    Msg = misc.decode64(request.Payload)
    # TODO !!!

#------------------------------------------------------------------------------ 

def ListCustomerFiles(customer_idurl):
    filename = nameurl.UrlFilename(customer_idurl)
    customer_dir = os.path.join(settings.getCustomersFilesDir(), filename)
    result = cStringIO.StringIO()
    def cb(realpath, subpath, name):
        if os.path.isdir(realpath):
            result.write('D%s\n' % subpath)
        else:
            result.write('F%s\n' % subpath)
        return True
    dhnio.traverse_dir_recursive(cb, customer_dir)
    src = result.getvalue()
    result.close()
    return src

# on the status form when clicking on a customer, find out what files we're holding for that customer
def ListCustomerFiles1(customerNumber):
    idurl = contacts.getCustomerID(customerNumber)
    filename = nameurl.UrlFilename(idurl)
    customerDir = os.path.join(settings.getCustomersFilesDir(), filename)
    if os.path.exists(customerDir) and os.path.isdir(customerDir):
        backupFilesList = os.listdir(customerDir)
        if len(backupFilesList) > 0:
            return ListSummary(backupFilesList)
    return "No files stored for this customer"


def RequestListFilesAll():
    r = []
    for supi in range(contacts.numSuppliers()):
        r.append(RequestListFiles(supi))
    return r


def RequestListFiles(supplierNumORidurl):
    if isinstance(supplierNumORidurl, str):
        RemoteID = supplierNumORidurl
    else:
        RemoteID = contacts.getSupplierID(supplierNumORidurl)
    if not RemoteID:
        dhnio.Dprint(4, "p2p_service.RequestListFiles WARNING RemoteID is empty supplierNumORidurl=%s" % str(supplierNumORidurl))
        return
    dhnio.Dprint(8, "p2p_service.RequestListFiles [%s]" % nameurl.GetName(RemoteID))
    MyID = misc.getLocalID()
    PacketID = packetid.UniqueID()
    Payload = settings.ListFilesFormat()
    result = dhnpacket.dhnpacket(commands.ListFiles(), MyID, MyID, PacketID, Payload, RemoteID)
    transport_control.outboxNoAck(result)
    return PacketID

#------------------------------------------------------------------------------ 

# Take directory listing and make summary of format:
#         BackupID-1-Data 1-1873 missing for 773,883,
#         BackupID-1-Parity 1-1873 missing for 777,982,
def ListSummary(dirlist):
    BackupMax={}
    BackupAll={}
    result=""
    for filename in dirlist:
        if not packetid.Valid(filename):       # if not type we can summarize
            result += filename + "\n"            #    then just include filename
        else:
            BackupID, BlockNum, SupNum, DataOrParity = packetid.BidBnSnDp(filename)
            LocalID = BackupID + "-" + str(SupNum) + "-" + DataOrParity
            blocknum = int(BlockNum)
            BackupAll[(LocalID,blocknum)]=True
            if LocalID in BackupMax:
                if BackupMax[LocalID] < blocknum:
                    BackupMax[LocalID] = blocknum
            else:
                BackupMax[LocalID] = blocknum
    for BackupName in sorted(BackupMax.keys()):
        missing = []
        thismax = BackupMax[BackupName]
        for blocknum in range(0, thismax):
            if not (BackupName, blocknum) in BackupAll:
                missing.append(str(blocknum))
        result += BackupName + " from 0-" + str(thismax)
        if len(missing) > 0:
            result += ' missing '
            result += ','.join(missing)
#            for m in missing:
#                result += str(m) + ","
        result += "\n"
    return result

def TreeSummary(ownerdir):
    out = cStringIO.StringIO()
    def cb(result, realpath, subpath, name):
        if not os.access(realpath, os.R_OK):
            return False
        if os.path.isfile(realpath):
            result.write('F%s\n' % subpath)
            return False
        if not packetid.IsCanonicalVersion(name):
            result.write('D%s\n' % subpath)
            return True
        maxBlock = -1
        dataBlocks = {}
        parityBlocks = {}
        dataMissing = {}
        parityMissing = {}
        for filename in os.listdir(realpath):
            packetID = subpath + '/' + filename
            pth = os.path.join(realpath, filename)
            if os.path.isdir(pth):
                result.write('D%s\n' % packetID)
                continue
            if not packetid.Valid(packetID):
                result.write('F%s\n' % packetID)
                continue
            pathID, versionName, blockNum, supplierNum, dataORparity = packetid.SplitFull(packetID)
            if None in [pathID, versionName, blockNum, supplierNum, dataORparity]:
                result.write('F%s\n' % packetID)
                continue
            if dataORparity == 'Data':
                if not dataBlocks.has_key(supplierNum):
                    dataBlocks[supplierNum] = set()
                    dataMissing[supplierNum] = []
                dataBlocks[supplierNum].add(blockNum)
            elif dataORparity == 'Parity':
                if not parityBlocks.has_key(supplierNum):
                    parityBlocks[supplierNum] = set()
                    parityMissing[supplierNum] = []
                parityBlocks[supplierNum].add(blockNum)
            else:
                result.write('F%s\n' % packetID)
                continue
            if maxBlock < blockNum:
                maxBlock = blockNum
        for blockNum in range(maxBlock+1):
            for supplierNum in dataBlocks.keys():
                if not blockNum in dataBlocks[supplierNum]:
                    dataMissing[supplierNum].append(str(blockNum))
            for supplierNum in parityBlocks.keys():
                if not blockNum in parityBlocks[supplierNum]:
                    parityMissing[supplierNum].append(str(blockNum))
        suppliers = set(dataBlocks.keys() + parityBlocks.keys())
        for supplierNum in suppliers:
            versionString = '%s %d 0-%d' % (subpath, supplierNum, maxBlock)
            dataMiss = []
            parityMiss = []
            if dataMissing.has_key(supplierNum):
                dataMiss = dataMissing[supplierNum]
            if parityMissing.has_key(supplierNum):
                parityMiss = parityMissing[supplierNum]   
            if len(dataMiss) > 0 or len(parityMiss) > 0:
                versionString += ' missing'
                if len(dataMiss) > 0:
                    versionString += ' Data:' + (','.join(dataMiss))
                if len(parityMiss) > 0:
                    versionString += ' Parity:' + (','.join(parityMiss))
            del dataMiss
            del parityMiss
            result.write('V%s\n' % versionString)
        del dataBlocks
        del parityBlocks
        del dataMissing
        del parityMissing
        return False
    dhnio.traverse_dir_recursive(lambda realpath, subpath, name: cb(out, realpath, subpath, name), ownerdir)
    src = out.getvalue()
    out.close()
    return src

def PackListFiles(plaintext, method):
    if method == "Text":
        return plaintext 
    elif method == "Compressed":
        return zlib.compress(plaintext)
    return ''

def UnpackListFiles(payload, method): 
    if method == "Text":
        return payload
    elif method == "Compressed":
        return zlib.decompress(payload)
    return payload

#------------------------------------------------------------------------------ 

# we need to send a DeleteBackup command to all suppliers
def RequestDeleteBackup(BackupID):
    dhnio.Dprint(4, "p2p_service.RequestDeleteBackup with BackupID=" + str(BackupID))
    for supplier in contacts.getSupplierIDs():
        if not supplier:
            continue
        prevItems = transport_control.SendQueueSearch(BackupID)
        found = False
        for workitem in prevItems:
            if workitem.remoteid == supplier:
                found = True
                break
        if found:
            continue
        SendDeleteBackup(supplier, BackupID)


def RequestDeleteListBackups(backupIDs):
    dhnio.Dprint(4, "p2p_service.RequestDeleteListBackups wish to delete %d backups" % len(backupIDs))
    for supplier in contacts.getSupplierIDs():
        if not supplier:
            continue
        found = False
        for workitem in transport_control.SendQueue():
            if workitem.command == commands.DeleteBackup() and workitem.remoteid == supplier:
                found = True
                break
        if found:
            continue
        SendDeleteListBackups(supplier, backupIDs)


def RequestDeleteListPaths(pathIDs):
    dhnio.Dprint(4, "p2p_service.RequestDeleteListPaths wish to delete %d paths" % len(pathIDs))
    for supplier in contacts.getSupplierIDs():
        if not supplier:
            continue
        found = False
        for workitem in transport_control.SendQueue():
            if workitem.command == commands.DeleteFile() and workitem.remoteid == supplier:
                found = True
                break
        if found:
            continue
        SendDeleteListPaths(supplier, pathIDs)


def CheckWholeBackup(BackupID):
    dhnio.Dprint(6, "p2p_service.CheckWholeBackup with BackupID=" + BackupID)

#-------------------------------------------------------------------------------

def message2gui(proto, text):
    pass
#    statusline.setp(proto, text)


def getErrorString(error):
    try:
        return error.getErrorMessage()
    except:
        if error is None:
            return ''
        return str(error)


def getHostString(host):
    try:
        return str(host.host)+':'+str(host.port)
    except:
        if host is None:
            return ''
        return str(host)

if __name__ == '__main__':
    settings.init()
    print ListCustomerFiles('http://identity.datahaven.net/eeekat4.xml')

