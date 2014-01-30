#!/usr/bin/python
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
# DHNBLOCK.PY
#
# Higher level code interfaces with dhnblock.py so that it does not have to deal
# with ECC stuff.  We write or read a large block at a time (maybe 64 MB say).
# When writing we generate all the ECC information, and when reading we will
# use ECC to recover lost information so user sees whole block still.
#
# We have to go to disk.  The normal mode is probably that there are a few machines that
# are slow and the rest move along.  We want to get the backup secure as soon as possible.
# It can be secure even if 5 to 10 suppliers are not finished yet.  But this could be
# a lot of storage, so we should be using disk.
#
# We want to generate a pool of writes to do, and put in more as it gets below some
# MB limit.  But we should not be limited by a particular nodes speed.
#
# The DHNpacket will have all the info about where it is going etc.
# We number them with our block number and the supplier numbers.
#
# Going to disk should let us do restarts after crashes without much trouble.
#
# Digital Signatures and timestamps are done on dhnblocks.  Signatures are also
# done on dhnpackets.
#
# RAIDMAKE:
#     This object can be asked to generate any/all dhnpacket(s) that would come from this
#     dhnblock.
# RAIDREAD:
#     It can also rebuild the dhnblock from packets and will
#     generate the read requests to get fetch the packets.
#
# import base64
# data64=base64.encodestring(data)    #  in case something can not handle binary remember this
# data=base64.decodestring(data64)    #  in case something can not handle binary remember this
#

import os
import sys
from twisted.internet.defer import Deferred

#if __name__ == '__main__':
#    sys.path.insert(0, os.path.abspath('..'))

import lib.misc as misc
import lib.dhnio as dhnio
import lib.dhncrypto as dhncrypto
import lib.contacts as contacts



#  The only 2 things secret in here will be the EncryptedSessionKey and EncryptedData
#  Scrubbers may combine-packets/unserialize/inspect-blocks/check-signatures
class dhnblock:
    CreatorID = ""          # http://cate.com/id1.xml  - so people can check signature - says PK type too
    BackupID = ""           # Creator's ID for the backup this packet is part of
    BlockNumber = ""        # number of this block
    EncryptedData = ""      # data may have some padding so multiple of crypto chunck size
                            # and multiple of #nodes in eccmap (usually 64) for division
                            # into dhnpackets
    Length=0                # real length of data when cleartext (encrypted may be padded)
    LastBlock = str(False)  # should now be "True" or "False" - careful in using
    SessionKeyType = ""     # which crypto is used for session key
    EncryptedSessionKey = ""# encrypted with our public key so only we can read this
    Other = ""              # could be be for professional timestamp company or other future features
    Signature = ""          # Digital signature by Creator - verifiable by public key in creator identity

    def __init__ (self, CreatorID, BackupID, BlockNumber, SessionKey, SessionKeyType, LastBlock, Data,):
        self.CreatorID = CreatorID
        self.BackupID = BackupID
        self.BlockNumber = str(BlockNumber)
        self.EncryptedSessionKey = dhncrypto.EncryptLocalPK(SessionKey)
        self.SessionKeyType = SessionKeyType
        self.Length = str(len(Data))
        self.LastBlock = str(bool(LastBlock))               
        self.EncryptedData = dhncrypto.EncryptWithSessionKey(SessionKey, Data) # DataLonger
        self.Signature = None
        self.Sign()

    def __repr__(self):
        return 'dhnblock (BackupID=%s BlockNumber=%s Length=%s LastBlock=%s)' % (str(self.BackupID), str(self.BlockNumber), str(self.Length), self.LastBlock)

    def SessionKey(self):
        return dhncrypto.DecryptLocalPK(self.EncryptedSessionKey)

    def GenerateHashBase(self):
        sep = "::::"
        # PREPRO needs to have all fields and separator
        StringToHash = self.CreatorID + sep + self.BackupID + sep + self.BlockNumber + sep + self.SessionKeyType + sep + self.EncryptedSessionKey + sep + self.Length + sep + self.LastBlock + sep + self.EncryptedData
        return StringToHash

    def GenerateHash(self):
        return dhncrypto.Hash(self.GenerateHashBase())

    def Sign(self):
        self.Signature = self.GenerateSignature()  # usually just done at packet creation
        return self

    def GenerateSignature(self):
        return dhncrypto.Sign(self.GenerateHash())

    def Ready(self):
        return self.Signature is not None

    def Valid(self):
        if not self.Ready():
            dhnio.Dprint(4, "dhnblock.Valid WARNING block is not ready yet " + str(self))
            return False
        hash = self.GenerateHash()
        ConIdentity = contacts.getContact(misc.getLocalID())
        if ConIdentity is None:
            dhnio.Dprint(2, "dhnblock.Valid WARNING could not get Identity so returning False")
            return False
        result = dhncrypto.Verify(ConIdentity, hash, self.Signature)    # At block level only work on own stuff
        return result

    def Data(self):
        SessionKey = self.SessionKey()
        ClearLongData = dhncrypto.DecryptWithSessionKey(SessionKey, self.EnctryptedData)
        return ClearLongData[0:self.Length]    # remove padding

    def Serialize(self):
        e = misc.ObjectToString(self)
        return e

def Unserialize(data):
    newobject = misc.StringToObject(data)
    return newobject





