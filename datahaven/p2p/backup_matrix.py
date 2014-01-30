#!/usr/bin/python
#backup_matrix.py
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
import gc
import cStringIO


try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in backup_matrix.py')

from twisted.internet.defer import Deferred, maybeDeferred
from twisted.internet import threads


import lib.dhnio as dhnio
import lib.misc as misc
import lib.nameurl as nameurl
import lib.transport_control as transport_control
import lib.settings as settings
import lib.contacts as contacts
# import lib.eccmap as eccmap
import lib.tmpfile as tmpfile
import lib.diskspace as diskspace
import lib.packetid as packetid
from lib.automat import Automat


import backup_monitor
import backup_rebuilder  
import fire_hire
import list_files_orator
import backup_db_keeper

import p2p_service
import io_throttle
import contact_status
import backup_fs
import backup_control

#------------------------------------------------------------------------------ 

_RemoteFiles = {}
_LocalFiles = {}
_RemoteMaxBlockNumbers = {}
_LocalMaxBlockNumbers = {}
_LocalBackupSize = {}
_BackupsInProcess = []
_SuppliersSet = None
_BackupStatusNotifyCallback = None
_StatusCallBackForGuiBackup = None
_LocalFilesNotifyCallback = None
_UpdatedBackupIDs = set()
_RepaintingTask = None   
_RepaintingTaskDelay = 2.0

#------------------------------------------------------------------------------ 

def init():
    dhnio.Dprint(4, 'backup_matrix.init')
    RepaintingProcess(True)
    ReadLocalFiles()
    ReadLatestRawListFiles()


def shutdown():
    dhnio.Dprint(4, 'backup_matrix.shutdown')
    RepaintingProcess(False)

#------------------------------------------------------------------------------ 

# index for all remote files (on suppliers HDD's) stored in dictionary
# values are -1, 0 or 1 - this mean file is missing, no info yet, or its existed 
# all entries are indexed by [backupID][blockNum]['D' or 'P'][supplierNum]
def remote_files():
    global _RemoteFiles
    return _RemoteFiles


# max block number for every remote backup ID
def remote_max_block_numbers():
    global _RemoteMaxBlockNumbers
    return _RemoteMaxBlockNumbers


# index for all local files (on our HDD) stored in dictionary
# values are 0 or 1 - this mean file exist or not 
# all entries are indexed by [backupID][blockNum]['D' or 'P'][supplierNum]
def local_files():
    global _LocalFiles
    return _LocalFiles


# max block number for every local backup ID
def local_max_block_numbers():
    global _LocalMaxBlockNumbers
    return _LocalMaxBlockNumbers


def local_backup_size():
    global _LocalBackupSize
    return _LocalBackupSize


# currently working backups (started from dobackup.py)
def backups_in_process():
    global _BackupsInProcess
    return _BackupsInProcess


def suppliers_set():
    global _SuppliersSet
    if _SuppliersSet is None:
        _SuppliersSet = SuppliersSet(contacts.getSupplierIDs())
    return _SuppliersSet

#------------------------------------------------------------------------------ 
# this should represent the set of suppliers for either the user or for a customer the user
# is acting as a scrubber for
class SuppliersSet:
    def __init__(self, supplierList):
        self.suppliers = [] 
        self.supplierCount = 0 
        self.UpdateSuppliers(supplierList)

    def GetActiveArray(self):
        activeArray = [0] * self.supplierCount
        for i in xrange(self.supplierCount):
            if not self.suppliers[i]:
                continue
            if contact_status.isOnline(self.suppliers[i]):
                activeArray[i] = 1
            else:
                activeArray[i] = 0
        return activeArray

    def ChangedArray(self, supplierList):
        changedArray = [0] * self.supplierCount
        changedIdentities = []
        for i in xrange(self.supplierCount):
            if not self.suppliers[i]:
                continue
            if supplierList[i] != self.suppliers[i]:
                changedArray[i] = 1
                changedIdentities.append(supplierList[i])
        return changedArray, changedIdentities

    def SuppliersChanged(self, supplierList):
        if len(supplierList) != self.supplierCount:
            return True
        for i in xrange(self.supplierCount):
            if not self.suppliers[i]:
                continue
            if supplierList[i] != self.suppliers[i]:
                return True
        return False

    # if suppliers 1 and 3 changed, return [1,3]
    def SuppliersChangedNumbers(self, supplierList):
        changedList = []
        for i in xrange(self.supplierCount):
            if not self.suppliers[i]:
                continue
            if supplierList[i] != self.suppliers[i]:
                changedList.append(i)
        return changedList

    def SupplierCountChanged(self, supplierList):
        if len(supplierList) != self.supplierCount:
            return True
        else:
            return False

    def UpdateSuppliers(self, supplierList):
        self.suppliers = supplierList
        self.supplierCount = len(self.suppliers)

#------------------------------------------------------------------------------ 

def SaveLatestRawListFiles(idurl, listFileText):
    supplierPath = settings.SupplierPath(idurl)
    if not os.path.isdir(supplierPath):
        try:
            os.makedirs(supplierPath)
        except:
            dhnio.DprintException()
            return
    dhnio.WriteFile(settings.SupplierListFilesFilename(idurl), listFileText)


def ReadRawListFiles(supplierNum, listFileText):
    # all lines are something like that
    # Findex
    # D0
    # D0/1 
    # V0/1/F20090709034221PM 3 0-1000
    # V0/1/F20090709034221PM 3 0-1000
    # D0/0/123/4567
    # V0/0/123/4567/F20090709034221PM 3 0-11 missing Data:1,3
    # V0/0/123/4/F20090709012331PM 3 0-5 missing Data:1,3 Parity:0,1,2
    backups2remove = set()
    paths2remove = set()
    oldfiles = ClearSupplierRemoteInfo(supplierNum)
    newfiles = 0
    dhnio.Dprint(8, 'backup_matrix.ReadRawListFiles %d bytes to read' % len(listFileText))
    input = cStringIO.StringIO(listFileText)
    while True:
        line = input.readline()
        if line == '':
            break
        typ = line[0]
        line = line[1:] 
        line = line.rstrip('\n')
        # comment lines in Files reports start with blank,
        if line.strip() == '':
            continue
        # also don't consider the identity a backup,
        if line.find('http://') != -1 or line.find('.xml') != -1:
            continue
        # nor backup_info.xml, nor backup_db, nor index  files 
        if line in [ settings.BackupIndexFileName(), settings.BackupInfoFileName(), settings.BackupInfoFileNameOld(), settings.BackupInfoEncryptedFileName() ]:
            continue
        if typ == 'F':
            # we don't have this path in the index
            # so we have several cases:
            #    1. this is old file and we need to remove it and all its backups
            #    2. we loose our local index and did not restore it from one of suppliers yet
            #    3. we did restore our account and did not restore the index yet
            #    4. we lost our index at all and we do not have nor local nor remote copy
            # what to do now: 
            #    - in first case we just need to remove the file from remote supplier
            #    - in other cases we must keep all remote data and believe we can restore the index 
            #         and get all file names and backed up data
            # how to recognize that? how to be sure we have the correct index?
            # because it should be empty right after we recover our account 
            # or we may loose it if the local index file were lost
            # the first idea:  check backup_db_keeper state - READY means index is fine
            # the second idea: check revision number of the local index - 0 means we have no index yet 
            if not backup_fs.IsFileID(line): # remote supplier have some file - but we don't have it in the index
                if backup_control.revision() > 0 and backup_db_keeper.A().IsSynchronized():  
                    # so we have some modifications in the index - it is not empty!
                    # backup_db_keeper did its job - so we have the correct index
                    paths2remove.add(line) # now we are sure that this file is old and must be removed
                    dhnio.Dprint(8, '        F%s - remove, not found in the index' % line)
                # what to do now? let's hope we still can restore our index and this file is our remote data
        elif typ == 'D':
            if not backup_fs.ExistsID(line):
                if backup_control.revision() > 0 and backup_db_keeper.A().IsSynchronized():
                    paths2remove.add(line)
                    dhnio.Dprint(8, '        D%s - remove, not found in the index' % line)
        elif typ == 'V':
            words = line.split(' ')
            # minimum is 3 words: "0/0/F20090709034221PM", "3", "0-1000"
            if len(words) < 3:
                dhnio.Dprint(2, 'backup_matrix.ReadRawListFiles WARNING incorrect line:[%s]' % line)
                continue
            try:
                pathID, versionName = packetid.SplitBackupID(words[0])
                backupID = pathID+'/'+versionName
                lineSupplierNum = int(words[1])
                minBlockNum, maxBlockNum = words[2].split('-')
                maxBlockNum = int(maxBlockNum)
            except:
                dhnio.Dprint(2, 'backup_matrix.ReadRawListFiles WARNING incorrect line:[%s]' % line)
                continue
            if lineSupplierNum != supplierNum:
                # this mean supplier have old files and we do not need that 
                backups2remove.add(backupID)
                dhnio.Dprint(8, '        V%s - remove, different supplier number' % backupID)
                continue
            iter_path = backup_fs.WalkByID(pathID)
            if iter_path is None:
                # this version is not found in the index
                if backup_control.revision() > 0 and backup_db_keeper.A().IsSynchronized():
                    backups2remove.add(backupID)
                    paths2remove.add(pathID)
                    dhnio.Dprint(8, '        V%s - remove, path not found in the index' % pathID)
                continue
            item, localPath = iter_path
            if isinstance(item, dict):
                try:
                    item = item[backup_fs.INFO_KEY]
                except:
                    item = None
            if not item or not item.has_version(versionName):
                if backup_control.revision() > 0 and backup_db_keeper.A().IsSynchronized():
                    backups2remove.add(backupID)
                    dhnio.Dprint(8, '        V%s - remove, version is not found in the index' % backupID)
                continue
            missingBlocksSet = {'Data': set(), 'Parity': set()}
            if len(words) > 3:
                # "0/0/123/4567/F20090709034221PM/0-Data" "3" "0-5" "missing" "Data:1,3" "Parity:0,1,2"
                if words[3].strip() != 'missing':
                    dhnio.Dprint(2, 'backup_matrix.ReadRawListFiles WARNING incorrect line:[%s]' % line)
                    continue
                for missingBlocksString in words[4:]:
                    try:
                        dp, blocks = missingBlocksString.split(':')
                        missingBlocksSet[dp] = set(blocks.split(','))
                    except:
                        dhnio.DprintException()
                        break
            if not remote_files().has_key(backupID):
                remote_files()[backupID] = {}
                # dhnio.Dprint(6, 'backup_matrix.ReadRawListFiles new remote entry for %s created in the memory' % backupID)
            # +1 because range(2) give us [0,1] but we want [0,1,2]
            for blockNum in xrange(maxBlockNum+1):
                if not remote_files()[backupID].has_key(blockNum):
                    remote_files()[backupID][blockNum] = {
                        'D': [0] * suppliers_set().supplierCount,
                        'P': [0] * suppliers_set().supplierCount,}
                for dataORparity in ['Data', 'Parity']:
                    # we set -1 if the file is missing and 1 if exist, so 0 mean "no info yet" ... smart!
                    bit = -1 if str(blockNum) in missingBlocksSet[dataORparity] else 1 
                    remote_files()[backupID][blockNum][dataORparity[0]][supplierNum] = bit
                    newfiles += int((bit + 1) / 2) # this should switch -1 or 1 to 0 or 1
            # save max block number for this backup
            if not remote_max_block_numbers().has_key(backupID):
                remote_max_block_numbers()[backupID] = -1 
            if maxBlockNum > remote_max_block_numbers()[backupID]:
                remote_max_block_numbers()[backupID] = maxBlockNum
            # mark this backup to be repainted
            RepaintBackup(backupID)
    input.close()
    dhnio.Dprint(8, 'backup_matrix.ReadRawListFiles for supplier %d, old/new files:%d/%d, backups2remove:%d, paths2remove:%d' % (
        supplierNum, oldfiles, newfiles, len(backups2remove), len(paths2remove)))
    # return list of backupID's which is too old but stored on suppliers machines 
    return backups2remove, paths2remove
            

def ReadLatestRawListFiles():
    dhnio.Dprint(4, 'backup_matrix.ReadLatestRawListFiles')
    for idurl in contacts.getSupplierIDs():
        if idurl:
            filename = os.path.join(settings.SupplierPath(idurl, 'listfiles'))
            if os.path.isfile(filename):
                listFileText = dhnio.ReadTextFile(filename)
                if listFileText.strip() != '':
                    ReadRawListFiles(contacts.numberForSupplier(idurl), listFileText)

def ReadLocalFiles():
    global _LocalFilesNotifyCallback
    local_files().clear()
    local_max_block_numbers().clear()
    local_backup_size().clear()
    _counter = [0,]
    def visit(realpath, subpath, name):
        # subpath is something like 0/0/1/0/F20131120053803PM/0-1-Data  
        if not os.path.isfile(realpath):
            return True
        if realpath.startswith('newblock-'):
            return False
        if subpath in [ settings.BackupIndexFileName(), settings.BackupInfoFileName(), settings.BackupInfoFileNameOld(), settings.BackupInfoEncryptedFileName() ]:
            return False
        try:
            version = subpath.split('/')[-2]
        except:
            return False
        if not packetid.IsCanonicalVersion(version):
            return True
        LocalFileReport(packetID=subpath)
        _counter[0] += 1
        return False
    dhnio.traverse_dir_recursive(visit, settings.getLocalBackupsDir())
    dhnio.Dprint(8, 'backup_matrix.ReadLocalFiles  %d files indexed' % _counter[0])
    if dhnio.Debug(8):
        try:
            if sys.version_info >= (2, 6):
                #localSZ = sys.getsizeof(local_files())
                #remoteSZ = sys.getsizeof(remote_files())
                import lib.getsizeof
                localSZ = lib.getsizeof.total_size(local_files())
                remoteSZ = lib.getsizeof.total_size(remote_files())
                indexByName = lib.getsizeof.total_size(backup_fs.fs())
                indexByID = lib.getsizeof.total_size(backup_fs.fsID())
                dhnio.Dprint(10, '    all local info uses %d bytes in the memory' % localSZ)
                dhnio.Dprint(10, '    all remote info uses %d bytes in the memory' % remoteSZ)
                dhnio.Dprint(10, '    index by name takes %d bytes in the memory' % indexByName)
                dhnio.Dprint(10, '    index by ID takes %d bytes in the memory' % indexByID)
        except:
            dhnio.DprintException()
    if _LocalFilesNotifyCallback is not None:
        _LocalFilesNotifyCallback()

#------------------------------------------------------------------------------ 

def RemoteFileReport(backupID, blockNum, supplierNum, dataORparity, result):
    blockNum = int(blockNum)
    supplierNum = int(supplierNum)
    if supplierNum > suppliers_set().supplierCount:
        dhnio.Dprint(4, 'backup_matrix.RemoteFileReport got too big supplier number, possible this is an old packet')
        return
    if not remote_files().has_key(backupID):
        remote_files()[backupID] = {}
        dhnio.Dprint(8, 'backup_matrix.RemoteFileReport new remote entry for %s created in the memory' % backupID)
    if not remote_files()[backupID].has_key(blockNum):
        remote_files()[backupID][blockNum] = {
            'D': [0] * suppliers_set().supplierCount,
            'P': [0] * suppliers_set().supplierCount,}
    # save backed up block info into remote info structure, synchronize on hand info
    flag = 1 if result else 0
    if dataORparity == 'Data':
        remote_files()[backupID][blockNum]['D'][supplierNum] = flag 
    elif dataORparity == 'Parity':
        remote_files()[backupID][blockNum]['P'][supplierNum] = flag
    else:
        dhnio.Dprint(4, 'backup_matrix.RemoteFileReport WARNING incorrect backup ID: %s' % backupID)
    # if we know only 5 blocks stored on remote machine
    # but we have backed up 6th block - remember this  
    remote_max_block_numbers()[backupID] = max(remote_max_block_numbers().get(backupID, -1), blockNum)
    # mark to repaint this backup in gui
    RepaintBackup(backupID)


def LocalFileReport(packetID=None, backupID=None, blockNum=None, supplierNum=None, dataORparity=None):
    if packetID is not None:
        backupID, blockNum, supplierNum, dataORparity = packetid.Split(packetID)  
        if backupID is None:
            dhnio.Dprint(8, 'backup_matrix.LocalFileReport WARNING incorrect filename: ' + packetID)
            return
    else:
        blockNum = int(blockNum)
        supplierNum = int(supplierNum)
        dataORparity = dataORparity
        packetID = packetid.MakePacketID(backupID, blockNum, supplierNum, dataORparity)
    filename = packetID
    if dataORparity not in ['Data', 'Parity']:
        dhnio.Dprint(4, 'backup_matrix.LocalFileReport WARNING Data or Parity? ' + filename)
        return
    if supplierNum >= suppliers_set().supplierCount:
        dhnio.Dprint(4, 'backup_matrix.LocalFileReport WARNING supplier number %d > %d %s' % (supplierNum, suppliers_set().supplierCount, filename))
        return
    if not local_files().has_key(backupID):
        local_files()[backupID] = {}
        # dhnio.Dprint(14, 'backup_matrix.LocalFileReport new local entry for %s created in the memory' % backupID)
    if not local_files()[backupID].has_key(blockNum):
        local_files()[backupID][blockNum] = {
            'D': [0] * suppliers_set().supplierCount,
            'P': [0] * suppliers_set().supplierCount}
    local_files()[backupID][blockNum][dataORparity[0]][supplierNum] = 1
    if not local_max_block_numbers().has_key(backupID):
        local_max_block_numbers()[backupID] = -1
    if local_max_block_numbers()[backupID] < blockNum:
        local_max_block_numbers()[backupID] = blockNum
    # dhnio.Dprint(6, 'backup_matrix.LocalFileReport %s max block num is %d' % (backupID, local_max_block_numbers()[backupID]))
    if not local_backup_size().has_key(backupID):
        local_backup_size()[backupID] = 0
    localDest = os.path.join(settings.getLocalBackupsDir(), filename)
    if os.path.isfile(localDest):
        try:
            local_backup_size()[backupID] += os.path.getsize(localDest)
        except:
            dhnio.DprintException()
    RepaintBackup(backupID)


def LocalBlockReport(newblock, num_suppliers):
    if suppliers_set().supplierCount != num_suppliers:
        dhnio.Dprint(6, 'backup_matrix.LocalBlockReport %s skipped, because number of suppliers were changed' % str(newblock))
        return
    try:
        backupID = newblock.BackupID
        blockNum = int(newblock.BlockNumber)
    except:
        dhnio.DprintException()
        return
    for supplierNum in xrange(num_suppliers):
        for dataORparity in ('Data', 'Parity'):
            packetID = packetid.MakePacketID(backupID, blockNum, supplierNum, dataORparity)
            if not local_files().has_key(backupID):
                local_files()[backupID] = {}
                # dhnio.Dprint(14, 'backup_matrix.LocalFileReport new local entry for %s created in the memory' % backupID)
            if not local_files()[backupID].has_key(blockNum):
                local_files()[backupID][blockNum] = {
                    'D': [0] * suppliers_set().supplierCount,
                    'P': [0] * suppliers_set().supplierCount}
            local_files()[backupID][blockNum][dataORparity[0]][supplierNum] = 1
            # dhnio.Dprint(6, 'backup_matrix.LocalFileReport %s max block num is %d' % (backupID, local_max_block_numbers()[backupID]))
            if not local_backup_size().has_key(backupID):
                local_backup_size()[backupID] = 0
            try:
                local_backup_size()[backupID] += os.path.getsize(os.path.join(settings.getLocalBackupsDir(), packetID))
            except:
                dhnio.DprintException()
    if not local_max_block_numbers().has_key(backupID):
        local_max_block_numbers()[backupID] = -1
    if local_max_block_numbers()[backupID] < blockNum:
        local_max_block_numbers()[backupID] = blockNum
    RepaintBackup(backupID)

#------------------------------------------------------------------------------ 

def ScanMissingBlocks(backupID):
    missingBlocks = set()
    localMaxBlockNum = local_max_block_numbers().get(backupID, -1)
    remoteMaxBlockNum = remote_max_block_numbers().get(backupID, -1)
    supplierActiveArray = suppliers_set().GetActiveArray()

    if not remote_files().has_key(backupID):
        if not local_files().has_key(backupID):
            # we have no local and no remote info for this backup
            # no chance to do some rebuilds...
            # TODO but how we get here ?! 
            dhnio.Dprint(4, 'backup_matrix.ScanMissingBlocks no local and no remote info for %s' % backupID)
        else:
            # we have no remote info, but some local files exists
            # so let's try to sent all of them
            # need to scan all block numbers 
            for blockNum in xrange(localMaxBlockNum):
                # we check for Data and Parity packets
                localData = GetLocalDataArray(backupID, blockNum)
                localParity = GetLocalParityArray(backupID, blockNum)  
                for supplierNum in xrange(len(supplierActiveArray)):
                    # if supplier is not alive we can not send to him
                    # so no need to scan for missing blocks 
                    if supplierActiveArray[supplierNum] != 1:
                        continue
                    if localData[supplierNum] == 1:
                        missingBlocks.add(blockNum)
                    if localParity[supplierNum] == 1:
                        missingBlocks.add(blockNum)
    else:
        # now we have some remote info
        # we take max block number from local and remote
        maxBlockNum = max(remoteMaxBlockNum, localMaxBlockNum)
        # dhnio.Dprint(6, 'backup_matrix.ScanMissingBlocks maxBlockNum=%d' % maxBlockNum)
        # and increase by one because range(3) give us [0, 1, 2], but we want [0, 1, 2, 3]
        for blockNum in xrange(maxBlockNum + 1):
            # if we have few remote files, but many locals - we want to send all missed 
            if not remote_files()[backupID].has_key(blockNum):
                missingBlocks.add(blockNum)
                continue
            # take remote info for this block
            remoteData = GetRemoteDataArray(backupID, blockNum)
            remoteParity = GetRemoteParityArray(backupID, blockNum)  
            # now check every our supplier for every block
            for supplierNum in xrange(len(supplierActiveArray)):
                # if supplier is not alive we can not send to him
                # so no need to scan for missing blocks 
                if supplierActiveArray[supplierNum] != 1:
                    continue
                if remoteData[supplierNum] != 1:    # -1 means missing
                    missingBlocks.add(blockNum)     # 0 - no info yet
                if remoteParity[supplierNum] != 1:  # 1 - file exist on remote supplier 
                    missingBlocks.add(blockNum)
                
    # dhnio.Dprint(6, 'backup_matrix.ScanMissingBlocks %s' % missingBlocks)
    return list(missingBlocks)

def ScanBlocksToRemove(backupID, check_all_suppliers=True):
    dhnio.Dprint(10, 'backup_matrix.ScanBlocksToRemove for %s' % backupID)
    packets = []
    localMaxBlockNum = local_max_block_numbers().get(backupID, -1)
    if not remote_files().has_key(backupID) or not local_files().has_key(backupID):
        # no info about this backup yet - skip
        return packets
    for blockNum in xrange(localMaxBlockNum + 1):
        localArray = {'Data': GetLocalDataArray(backupID, blockNum),
                      'Parity': GetLocalParityArray(backupID, blockNum)}  
        remoteArray = {'Data': GetRemoteDataArray(backupID, blockNum),
                       'Parity': GetRemoteParityArray(backupID, blockNum)}  
        if ( 0 in remoteArray['Data'] ) or ( 0 in remoteArray['Parity'] ):
            # if some supplier do not have some data for that block - do not remove any local files for that block!
            # we do remove the local files only when we sure all suppliers got the all data pieces
            continue
        if ( -1 in remoteArray['Data'] ) or ( -1 in remoteArray['Parity'] ):
            # also if we do not have any info about this block for some supplier do not remove other local pieces
            continue
        for supplierNum in xrange(suppliers_set().supplierCount):
            supplierIDURL = suppliers_set().suppliers[supplierNum]
            if not supplierIDURL:
                # supplier is unknown - skip
                continue
            for dataORparity in ['Data', 'Parity']:
                packetID = packetid.MakePacketID(backupID, blockNum, supplierNum, dataORparity)
                if io_throttle.HasPacketInSendQueue(supplierIDURL, packetID):
                    # if we do sending the packet at the moment - skip
                    continue
                if localArray[dataORparity][supplierNum] == 1:  
                    packets.append(packetID)
                    dhnio.Dprint(10, '    mark to remove %s, blockNum:%d remote:%s local:%s' % (packetID, blockNum, str(remoteArray), str(localArray)))
#                if check_all_suppliers:
#                    if localArray[dataORparity][supplierNum] == 1:  
#                        packets.append(packetID)
#                else:
#                    if remoteArray[dataORparity][supplierNum] == 1 and localArray[dataORparity][supplierNum] == 1:  
#                        packets.append(packetID)
    return packets

def ScanBlocksToSend(backupID):
    if '' in suppliers_set().suppliers:
        return {} 
    localMaxBlockNum = local_max_block_numbers().get(backupID, -1)
    supplierActiveArray = suppliers_set().GetActiveArray()
    bySupplier = {}
    for supplierNum in xrange(len(supplierActiveArray)):
        bySupplier[supplierNum] = set()
    if not remote_files().has_key(backupID):
        for blockNum in xrange(localMaxBlockNum + 1):
            localData = GetLocalDataArray(backupID, blockNum)
            localParity = GetLocalParityArray(backupID, blockNum)  
            for supplierNum in xrange(len(supplierActiveArray)):
                if supplierActiveArray[supplierNum] != 1:
                    continue
                if localData[supplierNum] == 1:
                    bySupplier[supplierNum].add(packetid.MakePacketID(backupID, blockNum, supplierNum, 'Data'))
                if localParity[supplierNum] == 1:
                    bySupplier[supplierNum].add(packetid.MakePacketID(backupID, blockNum, supplierNum, 'Parity'))
    else:
        for blockNum in xrange(localMaxBlockNum + 1):
            remoteData = GetRemoteDataArray(backupID, blockNum)
            remoteParity = GetRemoteParityArray(backupID, blockNum)  
            localData = GetLocalDataArray(backupID, blockNum)
            localParity = GetLocalParityArray(backupID, blockNum)  
            for supplierNum in xrange(len(supplierActiveArray)):
                if supplierActiveArray[supplierNum] != 1:
                    continue
                if remoteData[supplierNum] != 1 and localData[supplierNum] == 1:    
                    bySupplier[supplierNum].add(packetid.MakePacketID(backupID, blockNum, supplierNum, 'Data'))   
                if remoteParity[supplierNum] != 1 and localParity[supplierNum] == 1:   
                    bySupplier[supplierNum].add(packetid.MakePacketID(backupID, blockNum, supplierNum, 'Parity'))
    return bySupplier

#------------------------------------------------------------------------------ 

def RepaintBackup(backupID): 
    global _UpdatedBackupIDs
    _UpdatedBackupIDs.add(backupID)


def RepaintingProcess(on_off):
    global _UpdatedBackupIDs
    global _BackupStatusNotifyCallback
    global _RepaintingTask
    global _RepaintingTaskDelay
    if on_off is False:
        _RepaintingTaskDelay = 2.0
        if _RepaintingTask is not None:
            if _RepaintingTask.active():
                _RepaintingTask.cancel()
                _RepaintingTask = None
                _UpdatedBackupIDs.clear()
                return
    for backupID in _UpdatedBackupIDs:
        if _BackupStatusNotifyCallback is not None:
            _BackupStatusNotifyCallback(backupID)
    minDelay = 2.0
    if backup_control.HasRunningBackup():
        minDelay = 8.0
    _RepaintingTaskDelay = misc.LoopAttenuation(_RepaintingTaskDelay, len(_UpdatedBackupIDs) > 0, minDelay, 8.0)
    _UpdatedBackupIDs.clear()
    _RepaintingTask = reactor.callLater(_RepaintingTaskDelay, RepaintingProcess, True)

#------------------------------------------------------------------------------ 

def EraseBackupRemoteInfo(backupID): 
    if remote_files().has_key(backupID):
        del remote_files()[backupID] # remote_files().pop(backupID)
    if remote_max_block_numbers().has_key(backupID):
        del remote_max_block_numbers()[backupID]
        
def EraseBackupLocalInfo(backupID):
    if local_files().has_key(backupID):
        del local_files()[backupID] # local_files().pop(backupID)
    if local_max_block_numbers().has_key(backupID):
        del local_max_block_numbers()[backupID]
    if local_backup_size().has_key(backupID):
        del local_backup_size()[backupID]

#------------------------------------------------------------------------------ 

def ClearLocalInfo():
    local_files().clear()
    local_max_block_numbers().clear()
    local_backup_size().clear()

def ClearRemoteInfo():
    remote_files().clear()
    remote_max_block_numbers().clear()
    
def ClearSupplierRemoteInfo(supplierNum):
    files = 0
    for backupID in remote_files().keys():
        for blockNum in remote_files()[backupID].keys():
            if remote_files()[backupID][blockNum]['D'][supplierNum] == 1:
                files += 1 
            if remote_files()[backupID][blockNum]['P'][supplierNum] == 1:
                files += 1
            remote_files()[backupID][blockNum]['D'][supplierNum] = 0
            remote_files()[backupID][blockNum]['P'][supplierNum] = 0
    return files

#------------------------------------------------------------------------------ 

def GetBackupStats(backupID):
    if not remote_files().has_key(backupID):
        return 0, 0, [(0, 0)] * suppliers_set().supplierCount
    percentPerSupplier = 100.0 / suppliers_set().supplierCount
    # ??? maxBlockNum = remote_max_block_numbers().get(backupID, -1)
    maxBlockNum = GetKnownMaxBlockNum(backupID)
    fileNumbers = [0] * suppliers_set().supplierCount
    totalNumberOfFiles = 0
    for blockNum in remote_files()[backupID].keys():
        for supplierNum in xrange(len(fileNumbers)):
            if supplierNum < suppliers_set().supplierCount:
                if remote_files()[backupID][blockNum]['D'][supplierNum] == 1:
                    fileNumbers[supplierNum] += 1
                    totalNumberOfFiles += 1
                if remote_files()[backupID][blockNum]['P'][supplierNum] == 1:
                    fileNumbers[supplierNum] += 1
                    totalNumberOfFiles += 1
    statsArray = []
    for supplierNum in xrange(suppliers_set().supplierCount):
        if maxBlockNum > -1:
            # 0.5 because we count both Parity and Data.
            percent = percentPerSupplier * 0.5 * fileNumbers[supplierNum] / ( maxBlockNum + 1 )
        else:
            percent = 0.0
        statsArray.append(( percent, fileNumbers[supplierNum] ))
    del fileNumbers 
    return totalNumberOfFiles, maxBlockNum, statsArray


# return totalPercent, totalNumberOfFiles, totalSize, maxBlockNum, statsArray
def GetBackupLocalStats(backupID):
    # ??? maxBlockNum = local_max_block_numbers().get(backupID, -1)
    maxBlockNum = GetKnownMaxBlockNum(backupID)
    if not local_files().has_key(backupID):
        return 0, 0, 0, maxBlockNum, [(0, 0)] * suppliers_set().supplierCount
    percentPerSupplier = 100.0 / suppliers_set().supplierCount
    totalNumberOfFiles = 0
    fileNumbers = [0] * suppliers_set().supplierCount
    for blockNum in xrange(maxBlockNum + 1):
        if blockNum not in local_files()[backupID].keys():
            continue
#    for blockNum in local_files()[backupID].keys():
        for supplierNum in xrange(len(fileNumbers)):
            if supplierNum < suppliers_set().supplierCount:
                if local_files()[backupID][blockNum]['D'][supplierNum] == 1:
                    fileNumbers[supplierNum] += 1
                    totalNumberOfFiles += 1
                if local_files()[backupID][blockNum]['P'][supplierNum] == 1:
                    fileNumbers[supplierNum] += 1
                    totalNumberOfFiles += 1
    statsArray = []
    for supplierNum in xrange(suppliers_set().supplierCount):
        if maxBlockNum > -1:
            # 0.5 because we count both Parity and Data.
            percent = percentPerSupplier * 0.5 * fileNumbers[supplierNum] / ( maxBlockNum + 1 )
        else:
            percent = 0.0
        statsArray.append(( percent, fileNumbers[supplierNum] ))
    del fileNumbers 
    totalPercent = 100.0 * 0.5 * totalNumberOfFiles / ((maxBlockNum + 1) * suppliers_set().supplierCount)
    return totalPercent, totalNumberOfFiles, local_backup_size().get(backupID, 0), maxBlockNum, statsArray


def GetBackupBlocksAndPercent(backupID):
    if not remote_files().has_key(backupID):
        return 0, 0
    # get max block number
    # ??? maxBlockNum = remote_max_block_numbers().get(backupID, -1)
    maxBlockNum = GetKnownMaxBlockNum(backupID)
    if maxBlockNum == -1:
        return 0, 0
    # we count all remote files for this backup
    fileCounter = 0
    for blockNum in remote_files()[backupID].keys():
        for supplierNum in xrange(suppliers_set().supplierCount):
            if remote_files()[backupID][blockNum]['D'][supplierNum] == 1:
                fileCounter += 1
            if remote_files()[backupID][blockNum]['P'][supplierNum] == 1:
                fileCounter += 1
    # +1 since zero based and *0.5 because Data and Parity
    return maxBlockNum + 1, 100.0 * 0.5 * fileCounter / ((maxBlockNum + 1) * suppliers_set().supplierCount)

# return : blocks, percent, weak block, weak percent
def GetBackupRemoteStats(backupID, only_available_files=True):
    if not remote_files().has_key(backupID):
        return 0, 0, 0, 0
    # get max block number
    # ??? maxBlockNum = remote_max_block_numbers().get(backupID, -1)
    maxBlockNum = GetKnownMaxBlockNum(backupID)
    if maxBlockNum == -1:
        return 0, 0, 0, 0
    supplierCount = suppliers_set().supplierCount
    fileCounter = 0
    weakBlockNum = -1
    lessSuppliers = supplierCount
    activeArray = suppliers_set().GetActiveArray()
    # we count all remote files for this backup - scan all blocks
    for blockNum in xrange(maxBlockNum + 1):
        if blockNum not in remote_files()[backupID].keys():
            lessSuppliers = 0
            weakBlockNum = blockNum
            continue
        goodSuppliers = supplierCount
        for supplierNum in xrange(supplierCount):
            if activeArray[supplierNum] != 1 and only_available_files:
                goodSuppliers -= 1
                continue
            if remote_files()[backupID][blockNum]['D'][supplierNum] != 1 or remote_files()[backupID][blockNum]['P'][supplierNum] != 1:
                goodSuppliers -= 1
            if remote_files()[backupID][blockNum]['D'][supplierNum] == 1:
                fileCounter += 1
            if remote_files()[backupID][blockNum]['P'][supplierNum] == 1:
                fileCounter += 1
        if goodSuppliers < lessSuppliers:
            lessSuppliers = goodSuppliers
            weakBlockNum = blockNum
    # +1 since zero based and *0.5 because Data and Parity
    return (maxBlockNum + 1, 100.0 * 0.5 * fileCounter / ((maxBlockNum + 1) * supplierCount),
            weakBlockNum, 100.0 * float(lessSuppliers) / float(supplierCount))


def GetBackupRemoteArray(backupID):
    if not remote_files().has_key(backupID):
        return None
    maxBlockNum = GetKnownMaxBlockNum(backupID)
    if maxBlockNum == -1:
        return None
    return remote_files()[backupID]


def GetBackupLocalArray(backupID):
    if not local_files().has_key(backupID):
        return None
    maxBlockNum = GetKnownMaxBlockNum(backupID)
    if maxBlockNum == -1:
        return None
    return local_files()[backupID]
        
    
def GetBackupIDs(remote=True, local=False, sorted_ids=False):
    s = set()
    if remote:
        s.update(remote_files().keys())
    if local:
        s.update(local_files().keys())
    if sorted_ids:
        return misc.sorted_backup_ids(list(s))
    return list(s)


def GetKnownMaxBlockNum(backupID):
    return max(remote_max_block_numbers().get(backupID, -1), 
               local_max_block_numbers().get(backupID, -1))


def GetLocalDataArray(backupID, blockNum):
    if not local_files().has_key(backupID):
        return [0] * suppliers_set().supplierCount
    if not local_files()[backupID].has_key(blockNum):
        return [0] * suppliers_set().supplierCount
    return local_files()[backupID][blockNum]['D']


def GetLocalParityArray(backupID, blockNum):
    if not local_files().has_key(backupID):
        return [0] * suppliers_set().supplierCount
    if not local_files()[backupID].has_key(blockNum):
        return [0] * suppliers_set().supplierCount
    return local_files()[backupID][blockNum]['P']
    

def GetRemoteDataArray(backupID, blockNum):
    if not remote_files().has_key(backupID):
        return [0] * suppliers_set().supplierCount
    if not remote_files()[backupID].has_key(blockNum):
        return [0] * suppliers_set().supplierCount
    return remote_files()[backupID][blockNum]['D']

    
def GetRemoteParityArray(backupID, blockNum):
    if not remote_files().has_key(backupID):
        return [0] * suppliers_set().supplierCount
    if not remote_files()[backupID].has_key(blockNum):
        return [0] * suppliers_set().supplierCount
    return remote_files()[backupID][blockNum]['P']


def GetSupplierStats(supplierNum):
    result = {}
    files = total = 0
    for backupID in remote_files().keys():
        result[backupID] = [0, 0]
        for blockNum in remote_files()[backupID].keys():
            if remote_files()[backupID][blockNum]['D'][supplierNum] == 1:
                result[backupID][0] += 1
                files += 1 
            if remote_files()[backupID][blockNum]['P'][supplierNum] == 1:
                result[backupID][0] += 1
                files += 1
            result[backupID][1] += 2
            total += 2
    return files, total, result


def GetWeakLocalBlock(backupID):
    # scan all local blocks for this backup 
    # and find the worst block 
    supplierCount = suppliers_set().supplierCount
    if not local_files().has_key(backupID):
        return -1, 0, supplierCount
    maxBlockNum = GetKnownMaxBlockNum(backupID)
    weakBlockNum = -1
    lessSuppliers = supplierCount
    for blockNum in xrange(maxBlockNum+1):
        if blockNum not in local_files()[backupID].keys():
            return blockNum, 0, supplierCount
        goodSuppliers = supplierCount
        for supplierNum in xrange(supplierCount):
            if  local_files()[backupID][blockNum]['D'][supplierNum] != 1 or local_files()[backupID][blockNum]['P'][supplierNum] != 1:
                goodSuppliers -= 1
        if goodSuppliers < lessSuppliers:
            lessSuppliers = goodSuppliers
            weakBlockNum = blockNum
    return weakBlockNum, lessSuppliers, supplierCount
 
    
def GetWeakRemoteBlock(backupID):
    # scan all remote blocks for this backup 
    # and find the worst block - less suppliers keeps the data and stay online 
    supplierCount = suppliers_set().supplierCount
    if not remote_files().has_key(backupID):
        return -1, 0, supplierCount
    maxBlockNum = GetKnownMaxBlockNum(backupID)
    weakBlockNum = -1
    lessSuppliers = supplierCount
    activeArray = suppliers_set().GetActiveArray()
    for blockNum in xrange(maxBlockNum+1):
        if blockNum not in remote_files()[backupID].keys():
            return blockNum, 0, supplierCount
        goodSuppliers = supplierCount
        for supplierNum in xrange(supplierCount):
            if activeArray[supplierNum] != 1:
                goodSuppliers -= 1
                continue
            if  remote_files()[backupID][blockNum]['D'][supplierNum] != 1 or remote_files()[backupID][blockNum]['P'][supplierNum] != 1:
                goodSuppliers -= 1
        if goodSuppliers < lessSuppliers:
            lessSuppliers = goodSuppliers
            weakBlockNum = blockNum
    return weakBlockNum, lessSuppliers, supplierCount

#------------------------------------------------------------------------------ 

def SetBackupStatusNotifyCallback(callBack):
    global _BackupStatusNotifyCallback
    _BackupStatusNotifyCallback = callBack

def SetLocalFilesNotifyCallback(callback):
    global _LocalFilesNotifyCallback
    _LocalFilesNotifyCallback = callback

#------------------------------------------------------------------------------ 


if __name__ == "__main__":
    init()
    import pprint
    # pprint.pprint(GetBackupIds())











