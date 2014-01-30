#!/usr/bin/python
#dhnpacket.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
# These packets usually hold on the order of 1 MB.
# Something equal to a packet number so we can detect duplicates in transport
import os
import sys

from twisted.internet import threads
from twisted.internet.defer import Deferred


import types
import datetime


import dhnio
import commands
import misc
import dhncrypto
import packetid
import contacts


# Legal Commands are in commands.py
# Packet Fields are all strings (no integers, objects, etc):
class dhnpacket:
# PacketID - string of the above 4 "Number"s with "-" separator to uniquely identify a packet
# on the local machine.  Can be used for filenames, and to prevent duplicates.
    def __init__(self, Command, OwnerID, CreatorID, PacketID, Payload, RemoteID,):
        self.Command = Command               
        # who owns this data and pays bills - http://cate.com/id1.xml
        self.OwnerID = OwnerID                
        # signer - http://cate.com/id1.xml - might be an authorized scrubber
        self.CreatorID = CreatorID            
        # functions for making and reading parts of this
        self.PacketID = PacketID              
        self.Date = datetime.datetime.now().strftime("%Y/%m/%d %I:%M:%S %p")
        # main body of binary data
        self.Payload = Payload                
        # want full IDURL for other party so troublemaker could not
        # use his packets to mess up other nodes by sending it to them
        self.RemoteID = RemoteID             
        # signature on Hash is always by CreatorID
        self.Signature = None
        self.Sign()

    def __repr__(self):
        return 'dhnpacket (command=%s id=%s)' % (str(self.Command), str(self.PacketID))

    def Sign(self):
        self.Signature = self.GenerateSignature()  # usually just done at packet creation
        return self

    def GenerateHashBase(self):
        sep = "-"
        stufftosum = self.Command + sep + self.OwnerID + sep + self.CreatorID + sep + self.PacketID + sep + self.Date + sep + self.Payload + sep + self.RemoteID
        return stufftosum

    def GenerateHash(self):
        return dhncrypto.Hash(self.GenerateHashBase())

    def GenerateSignature(self):
        return dhncrypto.Sign(self.GenerateHash())

    def SignatureChecksOut(self):
        ConIdentity = contacts.getContact(self.CreatorID)
        if ConIdentity is None:
            dhnio.Dprint(1, "dhnpacket.SignatureChecksOut ERROR could not get Identity for " + self.CreatorID + " so returning False")
            return False
        Result = dhncrypto.Verify(ConIdentity, self.GenerateHash(), self.Signature)
        return Result

    def Ready(self):
        return self.Signature is not None

    def Valid(self):
        # Valid should check every one of packet hearder fields:
        #         1) that command is one of the legal commands
        #         2) signature is good (which means the hashcode is good)
        # Rest PREPRO:
        #         2) all the number fields are just numbers
        #         5) length is within legal limits
        #         6) check that URL is a good URL
        #         7) that DataOrParity is either "data" or "parity"
        #         8) that creator is equal to owner or a scrubber for owner
        #         etc
        if not self.Ready():
            dhnio.Dprint(4, "dhnpacket.Valid WARNING packet is not ready yet " + str(self))
            return False
        if not commands.IsCommand(self.Command):
            dhnio.Dprint(1, "dhnpacket.Valid bad Command " + str(self.Command))
            return False
        if not self.SignatureChecksOut():
            dhnio.Dprint(1, "dhnpacket.Valid failed Signature")
            return False
        return True

    def BackupID(self):
        return packetid.BackupID(self.PacketID)

    def BlockNumber(self):
        return packetid.BlockNumber(self.PacketID)

    def DataOrParity(self):
        return packetid.DataOrParity(self.PacketID)

    def SupplierNumber(self):
        return packetid.SupplierNumber(self.PacketID)

    def Serialize(self):
        return misc.ObjectToString(self)

    def __len__(self):
        return len(self.Serialize())


class dhnpacket_0signed(dhnpacket):
    
    def GenerateSignature(self):
        return '0'


def Unserialize(data):
    if data is None:
        return None
    newobject = misc.StringToObject(data)
    if newobject is None:
        dhnio.Dprint(6, "dhnpacket.Unserialize WARNING result is None")
        return None
#        x,y,data = data.partition(' ')
#        try:
#            int(x)
#        except:
#            dhnio.Dprint(6, "dhnpacket.Unserialize WARNING incorrect data input")
#            return None
#        newobject = misc.StringToObject(data)
#        if newobject is None:
#            dhnio.Dprint(6, "dhnpacket.Unserialize WARNING result is None")
#            return None
    if type(newobject) != types.InstanceType:
        dhnio.Dprint(6, "dhnpacket.Unserialize WARNING not an instance: " + str(newobject))
        return None
    # if newobject.__class__ != dhnpacket or str(newobject.__class__).count('dhnpacket') == 0:
    if not str(newobject.__class__).count('dhnpacket.dhnpacket'):
        dhnio.Dprint(6, "dhnpacket.Unserialize WARNING not a dhnpacket: " + str(newobject.__class__))
        return None
    return newobject

def MakePacket(Command, OwnerID, CreatorID, PacketID, Payload, RemoteID):
    result = dhnpacket(Command, OwnerID, CreatorID, PacketID, Payload, RemoteID)
    return result

def MakePacketInThread(CallBackFunc, Command, OwnerID, CreatorID, PacketID, Payload, RemoteID):
    d = threads.deferToThread(MakePacket, Command, OwnerID, CreatorID, PacketID, Payload, RemoteID)
    d.addCallback(CallBackFunc)

def MakePacketDeferred(Command, OwnerID, CreatorID, PacketID, Payload, RemoteID):
    return threads.deferToThread(MakePacket, Command, OwnerID, CreatorID, PacketID, Payload, RemoteID)

#------------------------------------------------------------------------------ 

if __name__ == '__main__':
    dhnio.init()
    dhnio.SetDebug(18)
    import settings
    settings.init()
    dhncrypto.InitMyKey()
    p = Unserialize(dhnio.ReadBinaryFile(sys.argv[1]))
    print p
    
    
    