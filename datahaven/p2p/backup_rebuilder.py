#!/usr/bin/python
#backup_rebuilder.py
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
    sys.exit('Error initializing twisted.internet.reactor in backup_rebuilder.py')

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
from lib.automat import Automat


import fire_hire
import backup_monitor
import block_rebuilder
import data_sender
import lib.automats as automats

import backup_matrix
import raidread
import io_throttle

_BackupRebuilder = None
_StoppedFlag = True
_BackupIDsQueue = []  
_BlockRebuildersQueue = []

#------------------------------------------------------------------------------ 

def A(event=None, arg=None):
    global _BackupRebuilder
    if _BackupRebuilder is None:
        _BackupRebuilder = BackupRebuilder('backup_rebuilder', 'STOPPED', 12)
    if event is not None:
        _BackupRebuilder.automat(event, arg)
    return _BackupRebuilder


class BackupRebuilder(Automat):
    timers = {
        'timer-1min':   (2*60, ['REQUEST']),
        'timer-10sec':  (10.0, ['REQUEST']),
        'timer-1sec':   (1.0, ['NEXT_BACKUP', 'REQUEST']),
        }
    
    def init(self):
        self.currentBackupID = None             # currently working on this backup
        self.currentBlockNumber = -1            # currently working on this block
        self.workingBlocksQueue = []            # list of missing blocks we work on for current backup
        self.missingPackets = 0 
        self.missingSuppliers = set()

    def state_changed(self, oldstate, newstate):
        # automats.set_global_state('REBUILD ' + newstate)
        backup_monitor.A('backup_rebuilder.state', newstate)
        
    def A(self, event, arg):
        #---REQUEST---
        if self.state is 'REQUEST':
            if event == 'timer-1sec' and self.isStopped(arg) :
                self.state = 'STOPPED'
            elif ( event == 'timer-10sec' or event == 'inbox-data-packet' or event == 'requests-sent' ) and self.isChanceToRebuild(arg) :
                self.state = 'REBUILDING'
                self.doAttemptRebuild(arg)
            elif event == 'timer-1min' or ( event == 'requests-sent' and self.isRequestQueueEmpty(arg) and not self.isMissingPackets(arg) ) :
                self.state = 'DONE'
        #---STOPPED---
        elif self.state is 'STOPPED':
            if event == 'init' :
                pass
            elif event == 'start' :
                self.state = 'NEXT_BACKUP'
                self.doClearStoppedFlag(arg)
        #---NEXT_BACKUP---
        elif self.state is 'NEXT_BACKUP':
            if event == 'timer-1sec' and not self.isStopped(arg) and self.isMoreBackups(arg) :
                self.state = 'PREPARE'
                self.doPrepareNextBackup(arg)
            elif event == 'timer-1sec' and not self.isMoreBackups(arg) and not self.isStopped(arg) :
                self.state = 'DONE'
            elif event == 'timer-1sec' and self.isStopped(arg) :
                self.state = 'STOPPED'
        #---DONE---
        elif self.state is 'DONE':
            if event == 'start' :
                self.state = 'NEXT_BACKUP'
                self.doClearStoppedFlag(arg)
        #---PREPARE---
        elif self.state is 'PREPARE':
            if event == 'backup-ready' and self.isStopped(arg) :
                self.state = 'STOPPED'
            elif event == 'backup-ready' and not self.isStopped(arg) and self.isMoreBlocks(arg) :
                self.state = 'REQUEST'
                self.doRequestAvailableBlocks(arg)
            elif event == 'backup-ready' and not self.isStopped(arg) and not self.isMoreBlocks(arg) and self.isMoreBackups(arg) :
                self.state = 'NEXT_BACKUP'
            elif event == 'backup-ready' and ( not self.isMoreBackups(arg) and not self.isMoreBlocks(arg) ) :
                self.state = 'DONE'
        #---REBUILDING---
        elif self.state is 'REBUILDING':
            if event == 'rebuilding-finished' and self.isStopped(arg) :
                self.state = 'STOPPED'
            elif event == 'rebuilding-finished' and not self.isStopped(arg) and self.isMoreBlocks(arg) :
                self.state = 'REQUEST'
                self.doRequestAvailableBlocks(arg)
            elif event == 'rebuilding-finished' and not self.isStopped(arg) and not self.isMoreBlocks(arg) :
                self.state = 'PREPARE'
                self.doPrepareNextBackup(arg)

    def isMoreBackups(self, arg):
        global _BackupIDsQueue
        return len(_BackupIDsQueue) > 0
    
    def isMoreBlocks(self, arg):
        # because started from 0,  -1 means not found
        return len(self.workingBlocksQueue) > 0 
        # return self.currentBlockNumber > -1
        
    def isMissingPackets(self, arg):
        return self.missingPackets > 0 

    def isStopped(self, arg):
        return ReadStoppedFlag() == True # :-)
    
    def isChanceToRebuild(self, arg):
#         return len(self.missingSuppliers) <= eccmap.Current().CorrectableErrors
        supplierSet = backup_matrix.suppliers_set()
        # start checking in reverse order, see below for explanation
        for blockIndex in range(len(self.workingBlocksQueue)-1, -1, -1):
            blockNumber = self.workingBlocksQueue[blockIndex]
            if eccmap.Current().CanMakeProgress(
                    backup_matrix.GetLocalDataArray(self.currentBackupID, blockNumber),
                    backup_matrix.GetLocalParityArray(self.currentBackupID, blockNumber)):
                return True
        return False
    
    def isRequestQueueEmpty(self, arg):
        supplierSet = backup_matrix.suppliers_set()
        for supplierNum in range(supplierSet.supplierCount):
            supplierID = supplierSet.suppliers[supplierNum]
            if io_throttle.HasBackupIDInSendQueue(supplierID, self.currentBackupID):
                return False
        return True

    def doPrepareNextBackup(self, arg):
        global _BackupIDsQueue
        # clear block number from previous iteration
        self.currentBlockNumber = -1
        # check it, may be we already fixed all things
        if len(_BackupIDsQueue) == 0:
            self.workingBlocksQueue = []
            self.automat('backup-ready')
            return
        # take a first backup from queue to work on it
        backupID = _BackupIDsQueue.pop(0)
        # if remote data structure is not exist for this backup - create it
        # this mean this is only local backup!
        if not backup_matrix.remote_files().has_key(backupID):
            backup_matrix.remote_files()[backupID] = {}
            # we create empty remote info for every local block
            # range(0) should return []
            for blockNum in range(backup_matrix.local_max_block_numbers().get(backupID, -1) + 1):
                backup_matrix.remote_files()[backupID][blockNum] = {
                    'D': [0] * backup_matrix.suppliers_set().supplierCount,
                    'P': [0] * backup_matrix.suppliers_set().supplierCount }
        # detect missing blocks from remote info
        self.workingBlocksQueue = backup_matrix.ScanMissingBlocks(backupID)
        dhnio.Dprint(8, 'backup_rebuilder.doPrepareNextBackup [%s] working blocks: %s' % (backupID, str(self.workingBlocksQueue)))
        # find the correct max block number for this backup
        # we can have remote and local files
        # will take biggest block number from both 
        backupMaxBlock = max(backup_matrix.remote_max_block_numbers().get(backupID, -1),
                             backup_matrix.local_max_block_numbers().get(backupID, -1))
        # now need to remember this biggest block number
        # remote info may have less blocks - need to create empty info for missing blocks
        for blockNum in range(backupMaxBlock + 1):
            if backup_matrix.remote_files()[backupID].has_key(blockNum):
                continue
            backup_matrix.remote_files()[backupID][blockNum] = {
                'D': [0] * backup_matrix.suppliers_set().supplierCount,
                'P': [0] * backup_matrix.suppliers_set().supplierCount }
        if self.currentBackupID:
            # clear requesting queue from previous task
            io_throttle.DeleteBackupRequests(self.currentBackupID)
        # really take the next backup
        self.currentBackupID = backupID
        # clear requesting queue, remove old packets for this backup, we will send them again
        io_throttle.DeleteBackupRequests(self.currentBackupID)
        # dhnio.Dprint(6, 'backup_rebuilder.doTakeNextBackup currentBackupID=%s workingBlocksQueue=%d' % (self.currentBackupID, len(self.workingBlocksQueue)))
        self.automat('backup-ready')

    def doRequestAvailableBlocks(self, arg):
        self.missingPackets = 0
        # self.missingSuppliers.clear()
        # here we want to request some packets before we start working to rebuild the missed blocks
        supplierSet = backup_matrix.suppliers_set()
        availableSuppliers = supplierSet.GetActiveArray()
        # remember how many requests we did on this iteration
        total_requests_count = 0
        # at the moment I do download everything I have available and needed
        if '' in contacts.getSupplierIDs():
            self.automat('requests-sent', total_requests_count)
            return
        for supplierNum in range(supplierSet.supplierCount):
            supplierID = supplierSet.suppliers[supplierNum]
            requests_count = 0
            # we do requests in reverse order because we start rebuilding from the last block 
            # for blockNum in range(self.currentBlockNumber, -1, -1):
            for blockIndex in range(len(self.workingBlocksQueue)-1, -1, -1):
                blockNum = self.workingBlocksQueue[blockIndex] 
                # do not keep too many requests in the queue
                if io_throttle.GetRequestQueueLength(supplierID) >= 16:
                    break
                # also don't do too many requests at once
                if requests_count > 16:
                    break
                remoteData = backup_matrix.GetRemoteDataArray(self.currentBackupID, blockNum)
                remoteParity = backup_matrix.GetRemoteParityArray(self.currentBackupID, blockNum)
                localData = backup_matrix.GetLocalDataArray(self.currentBackupID, blockNum)
                localParity = backup_matrix.GetLocalParityArray(self.currentBackupID, blockNum)
                # if the remote Data exist and is available because supplier is on line,
                # but we do not have it on hand - do request  
                if localData[supplierNum] == 0:
                    PacketID = packetid.MakePacketID(self.currentBackupID, blockNum, supplierNum, 'Data')
                    if remoteData[supplierNum] == 1:
                        if availableSuppliers[supplierNum]:
                            # if supplier is not alive - we can't request from him           
                            if not io_throttle.HasPacketInRequestQueue(supplierID, PacketID):
                                io_throttle.QueueRequestFile(
                                    self.FileReceived, 
                                    misc.getLocalID(), 
                                    PacketID, 
                                    misc.getLocalID(), 
                                    supplierID)
                                requests_count += 1
                    else:
                        # count this packet as missing
                        self.missingPackets += 1
                        # also mark this guy as one who dont have any data - nor local nor remote 
                        # self.missingSuppliers.add(supplierNum)
                # same for Parity
                if localParity[supplierNum] == 0:
                    PacketID = packetid.MakePacketID(self.currentBackupID, blockNum, supplierNum, 'Parity')
                    if remoteParity[supplierNum] == 1: 
                        if availableSuppliers[supplierNum]:
                            if not io_throttle.HasPacketInRequestQueue(supplierID, PacketID):
                                io_throttle.QueueRequestFile(
                                    self.FileReceived, 
                                    misc.getLocalID(), 
                                    PacketID, 
                                    misc.getLocalID(), 
                                    supplierID)
                                requests_count += 1
                    else:
                        self.missingPackets += 1
                        # self.missingSuppliers.add(supplierNum)
            total_requests_count += requests_count
        self.automat('requests-sent', total_requests_count)
                
    def doAttemptRebuild(self, arg):
        self.workBlock = None
        self.blocksSucceed = []
        if len(self.workingBlocksQueue) == 0:
            self.automat('rebuilding-finished', False)
            return            
        # let's rebuild the backup blocks in reverse order, take last blocks first ... 
        # in such way we can propagate how big is the whole backup as soon as possible!
        # remote machine can multiply [file size] * [block number] 
        # and calculate the whole size to be received ... smart!
        # ... remote supplier should not use last file to calculate
        self.blockIndex = len(self.workingBlocksQueue) - 1
        dhnio.Dprint(8, 'backup_rebuilder.doAttemptRebuild %d more blocks' % (self.blockIndex+1))
        def _prepare_one_block(): 
            if self.blockIndex < 0:
                # dhnio.Dprint(8, '        _prepare_one_block finish all blocks')
                reactor.callLater(0, _finish_all_blocks)
                return
            self.currentBlockNumber = self.workingBlocksQueue[self.blockIndex]
            # dhnio.Dprint(8, '        _prepare_one_block %d to rebuild' % self.currentBlockNumber)
            self.workBlock = block_rebuilder.BlockRebuilder(
                eccmap.Current(), #self.eccMap,
                self.currentBackupID,
                self.currentBlockNumber,
                backup_matrix.suppliers_set(),
                backup_matrix.GetRemoteDataArray(self.currentBackupID, self.currentBlockNumber),
                backup_matrix.GetRemoteParityArray(self.currentBackupID, self.currentBlockNumber),
                backup_matrix.GetLocalDataArray(self.currentBackupID, self.currentBlockNumber),
                backup_matrix.GetLocalParityArray(self.currentBackupID, self.currentBlockNumber),)
            reactor.callLater(0, _identify_block_packets)
        def _identify_block_packets():
            self.workBlock.IdentifyMissing()
#            if not self.workBlock.IsMissingFilesOnHand():
#                dhnio.Dprint(8, '        _identify_block_packets some missing files is not come yet')
#                reactor.callLater(0, self.automat, 'rebuilding-finished', False)
#                return
            reactor.callLater(0, _work_on_block)
        def _work_on_block():
            maybeDeferred(self.workBlock.AttemptRebuild).addCallback(_rebuild_finished)
        def _rebuild_finished(someNewData):
            # dhnio.Dprint(8, '        _rebuild_finished on block %d, result is %s' % (self.currentBlockNumber, str(someNewData)))
            if someNewData:
                self.workBlock.WorkDoneReport()
                self.blocksSucceed.append(self.currentBlockNumber)
                data_sender.A('new-data')
            self.workBlock = None
            self.blockIndex -= 1
            delay = 0
            if someNewData:
                delay = 0.5
            reactor.callLater(delay, _prepare_one_block)
        def _finish_all_blocks():
            for blockNum in self.blocksSucceed:
                self.workingBlocksQueue.remove(blockNum)
            dhnio.Dprint(8, 'backup_rebuilder.doAttemptRebuild._finish_all_blocks succeed:%s working:%s' % (str(self.blocksSucceed), str(self.workingBlocksQueue)))
            result = len(self.blocksSucceed) > 0
            self.blocksSucceed = []
            self.automat('rebuilding-finished', result)
        reactor.callLater(0, _prepare_one_block)

    def doClearStoppedFlag(self, arg):
        ClearStoppedFlag()

    def FileReceived(self, packet, state):
        if state in ['in queue', 'shutdown', 'exist']:
            return
        if state != 'received':
            dhnio.Dprint(4, "backup_rebuilder.FileReceived WARNING incorrect state [%s] for packet %s" % (str(state), str(packet)))
            return
        packetID = packet.PacketID
        filename = os.path.join(settings.getLocalBackupsDir(), packetID)
        if not packet.Valid():
            # TODO 
            # if we didn't get a valid packet ... re-request it or delete it?
            dhnio.Dprint(2, "backup_rebuilder.FileReceived WARNING " + packetID + " is not a valid packet")
            return
        if os.path.exists(filename):
            dhnio.Dprint(4, "backup_rebuilder.FileReceived WARNING rewriting existed file" + filename)
            try: 
                os.remove(filename)
            except:
                dhnio.DprintException()
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            try:
                dhnio._dirs_make(dirname)
            except:
                dhnio.Dprint(2, "backup_rebuilder.FileReceived ERROR can not create sub dir " + dirname)
                return 
        if not dhnio.WriteFile(filename, packet.Payload):
            return
        backup_matrix.LocalFileReport(packetID)
        self.automat('inbox-data-packet', packetID)
        
#------------------------------------------------------------------------------ 

def AddBackupsToWork(backupIDs):
    global _BackupIDsQueue 
    _BackupIDsQueue.extend(backupIDs)


def RemoveBackupToWork(backupID):
    global _BackupIDsQueue
    if backupID in _BackupIDsQueue:
        _BackupIDsQueue.remove(backupID)
        

def RemoveAllBackupsToWork():
    global _BackupIDsQueue
    _BackupIDsQueue = []


def SetStoppedFlag():
    global _StoppedFlag
    _StoppedFlag = True
    
    
def ClearStoppedFlag():
    global _StoppedFlag
    _StoppedFlag = False
    

def ReadStoppedFlag():
    global _StoppedFlag
    return _StoppedFlag
    
    
#def AddBlockRebuilder(obj):
#    global _BlockRebuildersQueue
#    dhnio.Dprint(10, 'backup_rebuilder.AddBlockRebuilder for %s-%s' % (obj.backupID, str(obj.blockNum)))
#    _BlockRebuildersQueue.append(obj)
    

#def RemoveBlockRebuilder(obj):
#    global _BlockRebuildersQueue
#    dhnio.Dprint(10, 'backup_rebuilder.RemoveBlockRebuilder for %s-%s' % (obj.backupID, str(obj.blockNum)))
#    _BlockRebuildersQueue.remove(obj)


    
    

    
