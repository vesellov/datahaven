#!/usr/bin/python
#packetid.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
# packetid  - we have a standard way of making the PacketID strings for many packets.

# Note we return strings and not integers

import time
import re

#------------------------------------------------------------------------------ 

_LastUniqueNumber = 0

#------------------------------------------------------------------------------ 

def UniqueID():
    global _LastUniqueNumber
    _LastUniqueNumber += 1
    # we wrap around every billion, old packets should be gone by then
    if _LastUniqueNumber > 1000000000:     
        _LastUniqueNumber = 0
    inttime = int(time.time() * 100.0)
    if _LastUniqueNumber < inttime:
        _LastUniqueNumber = inttime
    # strings for packet fields
    return str(_LastUniqueNumber) 

def MakePacketID(backupID, blockNumber, supplierNumber, dataORparity):
    return backupID + '/' + str(blockNumber) + '-' + str(supplierNumber) + '-' + dataORparity

def Valid(packetID):
    # packetID may be in different forms:
    #    + full:     0/0/1/0/F20131120053803PM/0-1-Data
    #    + backupID: 0/0/1/0/F20131120053803PM
    #    + pathID:   0/0/1/0
    # here is:
    #     pathID:        0/0/1/0
    #     versionName:   F20131120053803PM
    #     blockNum :     0
    #     supplierNum :  1
    #     dataORparity : Data
    head, x, tail = packetID.rpartition('/')
    if x == '' and head == '':
        # this seems to be a shortest pathID: 0, 1, 2, ...
        try:
            x = int(tail)
        except:
            return False
        return True
    if tail.endswith('-Data') or tail.endswith('-Parity'):
        # seems to be in the full form
        if not IsPacketNameCorrect(tail):
            return False
        pathID, x, versionName = head.rpartition('/')
        if not IsCanonicalVersion(versionName):
            return False
        if not IsPathIDCorrect(pathID):
            return False
        return True
    if IsPathIDCorrect(packetID):
        # we have only two options now, let's if this is a pathID
        return True
        # this should be a backupID - no other cases 
    if IsCanonicalVersion(tail) and IsPathIDCorrect(head):
        return True
    # something is not fine with that string
    return False

def Split(packetID):
    # packetID :     0/0/1/0/F20131120053803PM/0-1-Data
    # return:        "0/0/1/0/F20131120053803PM", "0", "1", "Data"
    try:
        backupID, x, fileName = packetID.rpartition('/')
        blockNum, supplierNum, dataORparity = fileName.split('-')
        blockNum = int(blockNum)
        supplierNum = int(supplierNum)
    except:
        return None, None, None, None
    return backupID, blockNum, supplierNum, dataORparity

def SplitFull(packetID):
    # packetID :     0/0/1/0/F20131120053803PM/0-1-Data
    # return:        "0/0/1/0", "F20131120053803PM", "0", "1", "Data"
    try:
        backupID, x, fileName = packetID.rpartition('/')
        pathID, x, versionName = backupID.rpartition('/')
        blockNum, supplierNum, dataORparity = fileName.split('-')
        blockNum = int(blockNum)
        supplierNum = int(supplierNum)
    except:
        return None, None, None, None, None
    return pathID, versionName, blockNum, supplierNum, dataORparity

def SplitVersionFilename(packetID): 
    # packetID :     0/0/1/0/F20131120053803PM/0-1-Data
    # return:        "0/0/1/0", "F20131120053803PM", "0-1-Data"
    try:
        backupID, x, fileName = packetID.rpartition('/')
        pathID, x, versionName = backupID.rpartition('/')
    except:
        return None, None, None
    return pathID, versionName, fileName

def SplitBackupID(backupID):
    # backupID :     0/0/1/0/F20131120053803PM
    # return :       "0/0/1/0", "F20131120053803PM"
    try:
        pathID, x, versionName = backupID.rpartition('/')
    except:
        return None, None
    return pathID, versionName

def IsCanonicalVersion(versionName):
    return re.match('^F\d+?(AM|PM)\d*?$', versionName) is not None

def IsPacketNameCorrect(fileName):
    return re.match('^\d+?\-\d+?\-(Data|Parity)$', fileName) is not None

def IsPathIDCorrect(pathID):
    return pathID.replace('/', '').isdigit()

def BidBnSnDp(packetID):
    return Split(packetID)

def BackupID(packetID):
    return Split(packetID)[0]

def BlockNumber(packetID):
    return Split(packetID)[1]

def SupplierNumber(packetID):
    return Split(packetID)[2]

def DataOrParity(packetID):
    return Split(packetID)[3]

def parentPathsList(ID):
    # return all parent paths of the given ID
    # ID: 0/0/1/0/F20131120053803PM/0-1-Data
    # will return: 
    # [ '0', '0/0', '0/0/1', '0/0/1/0', '0/0/1/0/F20131120053803PM', 0/0/1/0/F20131120053803PM/0-1-Data ]
    path = '' 
    for word in ID.split('/'):
        if path:
            path += '/'
        path += word
        yield path
        




