#!/usr/bin/python
#block_rebuilder.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

import os
import sys
import time
import random


try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in block_rebuilder.py')

from twisted.internet.defer import Deferred, maybeDeferred
from twisted.internet import threads


import lib.dhnio as dhnio
import lib.misc as misc
import lib.nameurl as nameurl
import lib.transport_control as transport_control
import lib.settings as settings
import lib.contacts as contacts
import lib.eccmap as eccmap
import lib.tmpfile as tmpfile
import lib.diskspace as diskspace
import lib.packetid as packetid

import fire_hire
import backup_rebuilder
import list_files_orator 

import backup_matrix
import raidread
import p2p_service
import io_throttle
import contact_status
import data_sender

#------------------------------------------------------------------------------ 

class BlockRebuilder():
    def __init__(self,  
                 eccMap, 
                 backupID, 
                 blockNum, 
                 supplierSet, 
                 remoteData, 
                 remoteParity,
                 localData, 
                 localParity, 
                 creatorId = None, 
                 ownerId = None):
        self.eccMap = eccMap
        self.backupID = backupID
        self.blockNum = blockNum
        self.supplierSet = supplierSet
        self.supplierCount = len(self.supplierSet.suppliers)
        self.remoteData = remoteData
        self.remoteParity = remoteParity
        self.localData = localData
        self.localParity = localParity
        self.creatorId = creatorId
        self.ownerId = ownerId
        # at some point we may be dealing with when we're scrubbers
        if self.creatorId == None:
            self.creatorId = misc.getLocalID()
        if self.ownerId == None:
            self.ownerId = misc.getLocalID()
        # this files we want to rebuild
        # need to identify which files to work on
        self.missingData = [0] * self.supplierCount
        self.missingParity = [0] * self.supplierCount
        # array to remember requested files
        self.reconstructedData = [0] * self.supplierCount
        self.reconstructedParity = [0] * self.supplierCount

    def IdentifyMissing(self):
        self.availableSuppliers = self.supplierSet.GetActiveArray()
        for supplierNum in xrange(self.supplierCount):
            if self.availableSuppliers[supplierNum] == 0:
                continue
            # if remote Data file not exist and supplier is online
            # we mark it as missing and will try to rebuild this file and send to him
            if self.remoteData[supplierNum] != 1:
                # mark file as missing  
                self.missingData[supplierNum] = 1
            # same for Parity file
            if self.remoteParity[supplierNum] != 1:
                self.missingParity[supplierNum] = 1

    def IsMissingFilesOnHand(self):
        for supplierNum in xrange(self.supplierCount):
            # if supplier do not have the Data but is on line 
            if self.missingData[supplierNum] == 1:
                # ... and we also do not have the Data 
                if self.localData[supplierNum] != 1:
                    # return False - will need request the file   
                    return False
            # same for Parity                
            if self.missingParity[supplierNum] == 1:
                if self.localParity[supplierNum] != 1:
                    return False
        return True

    def BuildRaidFileName(self, supplierNumber, dataOrParity):
        return os.path.join(settings.getLocalBackupsDir(), self.BuildFileName(supplierNumber, dataOrParity))

    def BuildFileName(self, supplierNumber, dataOrParity):
        return packetid.MakePacketID(self.backupID, self.blockNum, supplierNumber, dataOrParity)

    def HaveAllData(self, parityMap):
        for segment in parityMap:
            if self.localData[segment] == 0:
                return False
        return True

    def AttemptRebuild(self):
        dhnio.Dprint(14, 'block_rebuilder.AttemptRebuild %s %d BEGIN' % (self.backupID, self.blockNum))
        newData = False
        madeProgress = True
        while madeProgress:
            madeProgress = False
            # if number of suppliers were changed - stop immediately 
            if contacts.numSuppliers() != self.supplierCount:
                dhnio.Dprint(10, 'block_rebuilder.AttemptRebuild END - number of suppliers were changed')
                return False
            # will check all data packets we have 
            for supplierNum in xrange(self.supplierCount):
                dataFileName = self.BuildRaidFileName(supplierNum, 'Data')
                # if we do not have this item on hands - we will reconstruct it from other items 
                if self.localData[supplierNum] == 0:
                    parityNum, parityMap = self.eccMap.GetDataFixPath(self.localData, self.localParity, supplierNum)
                    if parityNum != -1:
                        rebuildFileList = []
                        rebuildFileList.append(self.BuildRaidFileName(parityNum, 'Parity'))
                        for supplierParity in parityMap:
                            if supplierParity != supplierNum:
                                filename = self.BuildRaidFileName(supplierParity, 'Data')
                                if os.path.isfile(filename):
                                    rebuildFileList.append(filename)
                        dhnio.Dprint(10, '    rebuilding file %s from %d files' % (os.path.basename(dataFileName), len(rebuildFileList)))
                        raidread.RebuildOne(rebuildFileList, len(rebuildFileList), dataFileName)
                    if os.path.exists(dataFileName):
                        self.localData[supplierNum] = 1
                        madeProgress = True
                        dhnio.Dprint(10, '        Data file %s found after rebuilding for supplier %d' % (os.path.basename(dataFileName), supplierNum))
                # now we check again if we have the data on hand after rebuild at it is missing - send it
                # but also check to not duplicate sending to this man   
                # now sending is separated, see the file data_sender.py          
                if self.localData[supplierNum] == 1 and self.missingData[supplierNum] == 1: # and self.dataSent[supplierNum] == 0:
                    dhnio.Dprint(10, '            rebuilt a new Data for supplier %d' % supplierNum)
                    newData = True
                    self.reconstructedData[supplierNum] = 1
                    # self.outstandingFilesList.append((dataFileName, self.BuildFileName(supplierNum, 'Data'), supplierNum))
                    # self.dataSent[supplierNum] = 1
        # now with parities ...            
        for supplierNum in xrange(self.supplierCount):
            parityFileName = self.BuildRaidFileName(supplierNum, 'Parity')
            if self.localParity[supplierNum] == 0:
                parityMap = self.eccMap.ParityToData[supplierNum]
                if self.HaveAllData(parityMap):
                    rebuildFileList = []
                    for supplierParity in parityMap:
                        filename = self.BuildRaidFileName(supplierParity, 'Data')  # ??? why not 'Parity'
                        if os.path.isfile(filename): 
                            rebuildFileList.append(filename)
                    dhnio.Dprint(10, '    rebuilding file %s from %d files' % (os.path.basename(parityFileName), len(rebuildFileList)))
                    raidread.RebuildOne(rebuildFileList, len(rebuildFileList), parityFileName)
                    if os.path.exists(parityFileName):
                        dhnio.Dprint(10, '        Parity file %s found after rebuilding for supplier %d' % (os.path.basename(parityFileName), supplierNum))
                        self.localParity[supplierNum] = 1
            # so we have the parity on hand and it is missing - send it
            if self.localParity[supplierNum] == 1 and self.missingParity[supplierNum] == 1: # and self.paritySent[supplierNum] == 0:
                dhnio.Dprint(10, '            rebuilt a new Parity for supplier %d' % supplierNum)
                newData = True
                self.reconstructedParity[supplierNum] = 1
                # self.outstandingFilesList.append((parityFileName, self.BuildFileName(supplierNum, 'Parity'), supplierNum))
                # self.paritySent[supplierNum] = 1
        dhnio.Dprint(14, 'block_rebuilder.AttemptRebuild END')
        return newData

    def WorkDoneReport(self):
        for supplierNum in xrange(self.supplierCount):
            if self.localData[supplierNum] == 1 and self.reconstructedData[supplierNum] == 1:
                backup_matrix.LocalFileReport(None, self.backupID, self.blockNum, supplierNum, 'Data')
            if self.localParity[supplierNum] == 1 and self.reconstructedParity[supplierNum] == 1:
                backup_matrix.LocalFileReport(None, self.backupID, self.blockNum, supplierNum, 'Parity')
                    
                    