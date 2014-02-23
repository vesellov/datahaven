#!/usr/bin/python
#backup_control.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#


import os
import sys
import time
import locale
import xml.dom.minidom
import cStringIO
import zlib

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor backup_db.py')

from twisted.internet.defer import Deferred, fail


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

import lib.misc as misc
import lib.tmpfile as tmpfile
import lib.settings as settings
import lib.contacts as contacts
import lib.dhncrypto as dhncrypto
import lib.eccmap as eccmap
import lib.packetid as packetid
import lib.nameurl as nameurl
import lib.transport_control as transport_control
import lib.dirsize as dirsize

import dhnblock
import backup
import backup_tar
import backup_fs
import backup_matrix
import backup_rebuilder
import backup_monitor
import backup_db_keeper
import list_files_orator
import io_throttle
import p2p_service

#------------------------------------------------------------------------------ 

MAXIMUM_JOBS_STARTED = 1 # let's do only one backup at once for now

_Jobs = {}   # here are already started backups ( by backupID )
_Tasks = []  # here are tasks to start backups in the future 
_LastTaskNumber = 0   
_RevisionNumber = 0
_LoadingFlag = False  
_TaskStartedCallbacks = {}
_TaskFinishedCallbacks = {}

#------------------------------------------------------------------------------ 

def jobs():
    global _Jobs
    return _Jobs

def tasks():
    global _Tasks
    return _Tasks

def revision():
    global _RevisionNumber
    return _RevisionNumber

def commit(new_revision_number=None):
    global _RevisionNumber
    if new_revision_number:
        _RevisionNumber = new_revision_number
    else:
        _RevisionNumber += 1

#------------------------------------------------------------------------------ 

def init():
    dhnio.Dprint(4, 'backup_control.init')
    Load()

def shutdown():
    dhnio.Dprint(4, 'backup_control.shutdown')
    
#------------------------------------------------------------------------------ 

def WriteIndex(filepath=None):
    global _LoadingFlag
    if _LoadingFlag:
        return
    if filepath is None:
        filepath = settings.BackupIndexFilePath()
    src = '%d\n' % revision()
    src += backup_fs.Serialize()
    return dhnio.AtomicWriteFile(filepath, src)

def ReadIndex(input):
    global _LoadingFlag
    if _LoadingFlag:
        return False
    _LoadingFlag = True
    try:
        new_revision = int(input.readline().rstrip('\n'))
    except:
        _LoadingFlag = False
        dhnio.DprintException()
        return False
    backup_fs.Clear()
    count = backup_fs.Unserialize(input)
    commit(new_revision)
    _LoadingFlag = False
    return True

def Load(filepath=None):
    global _LoadingFlag
    if _LoadingFlag:
        return False
    if filepath is None:
        filepath = settings.BackupIndexFilePath()
    if not os.path.isfile(filepath):
        dhnio.Dprint(2, 'backup_control.Load ERROR file %s not exist' % filepath)
        return False
    src = dhnio.ReadTextFile(filepath)
    if not src:
        dhnio.Dprint(2, 'backup_control.Load ERROR reading file %s' % filepath)
        return False
    input = cStringIO.StringIO(src)
    ret = ReadIndex(input)
    input.close()
    backup_fs.Scan()
    backup_fs.Calculate()
    return ret

def Save(filepath=None):
    global _LoadingFlag
    if _LoadingFlag:
        return False
    commit()
    WriteIndex(filepath)
    backup_db_keeper.A('restart')

#------------------------------------------------------------------------------ 

def IncomingSupplierListFiles(packet):
    supplier_idurl = packet.OwnerID
    num = contacts.numberForSupplier(supplier_idurl)
    if num < -1:
        dhnio.Dprint(2, 'backup_control.IncomingSupplierListFiles ERROR unknown supplier: %s' % supplier_idurl)
        return
    src = p2p_service.UnpackListFiles(packet.Payload, settings.ListFilesFormat())
    backups2remove, paths2remove = backup_matrix.ReadRawListFiles(num, src)
    list_files_orator.IncommingListFiles(packet)
    backup_matrix.SaveLatestRawListFiles(supplier_idurl, src)
    if len(backups2remove) > 0:
        p2p_service.RequestDeleteListBackups(backups2remove)
    if len(paths2remove) > 0:
        p2p_service.RequestDeleteListPaths(paths2remove)
    del backups2remove
    del paths2remove
    dhnio.Dprint(8, 'backup_control.IncomingSupplierListFiles from [%s] %s bytes long' % (nameurl.GetName(supplier_idurl), len(packet.Payload)))

def IncomingSupplierBackupIndex(packet):
    block = dhnblock.Unserialize(packet.Payload)
    if block is None:
        dhnio.Dprint(2, 'backup_control.IncomingSupplierBackupIndex ERROR reading data from %s' % packet.RemoteID)
        return
    try:
        session_key = dhncrypto.DecryptLocalPK(block.EncryptedSessionKey)
        padded_data = dhncrypto.DecryptWithSessionKey(session_key, block.EncryptedData)
        input = cStringIO.StringIO(padded_data[:int(block.Length)])
        supplier_revision = int(input.readline().rstrip('\n'))
        input.seek(0)
    except:
        dhnio.Dprint(2, 'backup_control.IncomingSupplierBackupIndex ERROR reading data from %s' % packet.RemoteID)
        dhnio.Dprint(2, '\n' + padded_data)
        dhnio.DprintException()
        try:
            input.close()
        except:
            pass
        return
    if revision() < supplier_revision:
        ReadIndex(input)
        backup_fs.Scan()
        backup_fs.Calculate()
        WriteIndex()
        # TODO repaint a GUI
        dhnio.Dprint(2, 'backup_control.IncomingSupplierBackupIndex updated to revision %d from %s' % (revision(), packet.RemoteID))
    input.close()
    backup_db_keeper.A('incoming-db-info', packet)
        
#------------------------------------------------------------------------------ 

def SetSupplierList(supplierList):
    # going from 2 to 4 suppliers (or whatever) invalidates all backups
    # all suppliers was changed because its number was changed
    # so we lost everything!
    if len(supplierList) != backup_matrix.suppliers_set().supplierCount:
        dhnio.Dprint(2, "backup_control.SetSupplierList got list of %d suppliers, but we have %d now!" % (len(supplierList), backup_matrix.suppliers_set().supplierCount))
        # cancel all tasks and jobs
        DeleteAllTasks()
        AbortAllRunningBackups()
        # remove all local files and all backups
        DeleteAllBackups()
        # erase all remote info
        backup_matrix.ClearRemoteInfo()
        # also erase local info
        backup_matrix.ClearLocalInfo()
        # restart backup_monitor
        backup_monitor.Restart()
        # restart db keeper to save the index on new machines
        backup_db_keeper.A('restart')
    # only single suppliers changed
    # need to erase info only for them 
    elif backup_matrix.suppliers_set().SuppliersChanged(supplierList):
        # take a list of suppliers positions that was changed
        changedSupplierNums = backup_matrix.suppliers_set().SuppliersChangedNumbers(supplierList)
        # notify io_throttle that we do not neeed already this suppliers
        for supplierNum in changedSupplierNums:
            dhnio.Dprint(2, "backup_control.SetSupplierList supplier %d changed: [%s]->[%s]" % (
                supplierNum, nameurl.GetName(backup_matrix.suppliers_set().suppliers[supplierNum]), nameurl.GetName(supplierList[supplierNum])))
            io_throttle.DeleteSuppliers([backup_matrix.suppliers_set().suppliers[supplierNum],])
        # erase (set to 0) remote info for this guys
        backup_matrix.ClearSupplierRemoteInfo(supplierNum)
        # restart backup_monitor
        backup_monitor.Restart()
        # restart db keeper to save the index on all machines including a new one
        backup_db_keeper.A('restart')
    # finally save the list of current suppliers and clear all stats 
    backup_matrix.suppliers_set().UpdateSuppliers(supplierList)

#------------------------------------------------------------------------------ 
          
def DeleteAllBackups():
    # prepare a list of all known backup IDs
    all = set(backup_fs.ListAllBackupIDs())
    all.update(backup_matrix.GetBackupIDs(remote=True, local=True))
    dhnio.Dprint(4, 'backup_control.DeleteAllBackups %d ID\'s to kill' % len(all))
    # delete one by one
    for backupID in all:
        DeleteBackup(backupID, saveDB=False, calculate=False)
    # scan all files
    backup_fs.Scan()
    # check and calculate used space
    backup_fs.Calculate()
    # save the index
    Save()

# if the user deletes a backup, make sure we remove any work we're doing on it
def DeleteBackup(backupID, removeLocalFilesToo=True, saveDB=True, calculate=True):
    dhnio.Dprint(8, 'backup_control.DeleteBackup ' + backupID)
    # abort backup if it just started and is running at the moment
    AbortRunningBackup(backupID)
    # if we requested for files for this backup - we do not need it anymore
    io_throttle.DeleteBackupRequests(backupID)
    # remove interests in transport_control
    transport_control.DeleteBackupInterest(backupID)
    # mark it as being deleted in the db, well... just remove it from the index now
    backup_fs.DeleteBackupID(backupID)
    # finally remove local files for this backupID
    if removeLocalFilesToo:
        backup_fs.DeleteLocalBackup(settings.getLocalBackupsDir(), backupID)
    # remove all remote info for this backup from the memory 
    backup_matrix.EraseBackupLocalInfo(backupID)
    # also remove local info
    backup_matrix.EraseBackupLocalInfo(backupID)
    # stop any rebuilding, we will restart it soon
    backup_rebuilder.RemoveAllBackupsToWork()
    backup_rebuilder.SetStoppedFlag()
    # check and calculate used space
    if calculate:
        backup_fs.Scan()
        backup_fs.Calculate()
    # in some cases we want to save the DB later 
    if saveDB:
        Save()
    
def DeletePathBackups(pathID, removeLocalFilesToo=True, saveDB=True, calculate=True):
    # get the working item
    item = backup_fs.GetByID(pathID)
    if item is None:
        return
    # this is a list of all known backups of this path 
    versions = item.list_versions()
    for version in versions:
        backupID = pathID + '/' + version
        # abort backup if it just started and is running at the moment
        AbortRunningBackup(backupID)
        # if we requested for files for this backup - we do not need it anymore
        io_throttle.DeleteBackupRequests(backupID)
        # remove interests in transport_control
        transport_control.DeleteBackupInterest(backupID)
        # remove local files for this backupID
        if removeLocalFilesToo:
            backup_fs.DeleteLocalBackup(settings.getLocalBackupsDir(), backupID)
        # remove remote info for this backup from the memory 
        backup_matrix.EraseBackupLocalInfo(backupID)
        # also remove local info
        backup_matrix.EraseBackupLocalInfo(backupID)
        # finally remove this backup from the index
        item.delete_version(version)
        dhnio.Dprint(8, 'backup_control.DeletePathBackups ' + backupID)
    # stop any rebuilding, we will restart it soon
    backup_rebuilder.RemoveAllBackupsToWork()
    backup_rebuilder.SetStoppedFlag()
    # check and calculate used space
    if calculate:
        backup_fs.Scan()
        backup_fs.Calculate()
    # save the index if needed
    if saveDB:
        Save()

#------------------------------------------------------------------------------ 

def NewTaskNumber():
    global _LastTaskNumber
    _LastTaskNumber += 1
    return _LastTaskNumber

class Task():
    def __init__(self, pathID):
        self.number = NewTaskNumber()                   # index number for the task
        self.pathID = pathID                            # source path to backup 
        self.created = time.time()
        
    def __repr__(self):
        return 'Task-%d: %s' % (self.number, self.pathID)
        
    def run(self):
        iter_and_path = backup_fs.WalkByID(self.pathID)
        if iter_and_path is None:
            dhnio.Dprint(4, 'backup_control.Task.run ERROR %s not found in the index' % self.pathID)
            # self.defer.callback('error', self.pathID)
            return
        itemInfo, sourcePath = iter_and_path
        if isinstance(itemInfo, dict):
            try:
                itemInfo = itemInfo[backup_fs.INFO_KEY]
            except:
                dhnio.DprintException()
                return
        if not backup_fs.pathExist(sourcePath):
            dhnio.Dprint(4, 'backup_control.Task.run WARNING path not exist: %s' % sourcePath)
            reactor.callLater(0, OnTaskFailed, self.pathID, 'not exist')
            return
        dataID = misc.NewBackupID()
        if itemInfo.has_version(dataID):
            # ups - we already have same version
            # let's add 1,2,3... to the end to make absolutely unique version ID
            i = 1
            while itemInfo.has_version(dataID+str(i)):
                i += 1
            dataID += str(i)
        backupID = self.pathID + '/' + dataID
        try:
            backupPath = backup_fs.MakeLocalDir(settings.getLocalBackupsDir(), backupID)
        except:
            dhnio.DprintException()
            dhnio.Dprint(4, 'backup_control.Task.run ERROR creating destination folder for %s' % self.pathID)
            # self.defer.callback('error', self.pathID)
            return 
        if backup_fs.pathIsDir(sourcePath):
            backupPipe = backup_tar.backuptar(sourcePath, compress='gz')
        else:    
            backupPipe = backup_tar.backuptarfile(sourcePath, compress='gz')
        backupPipe.make_nonblocking()
        resultDefer = Deferred()
        blockSize = settings.getBackupBlockSize()
        job = backup.backup(backupID, backupPipe, OnJobDone, OnBackupBlockReport, settings.getBackupBlockSize())
        jobs()[backupID] = job
        itemInfo.add_version(dataID)
        if itemInfo.type in [ backup_fs.PARENT, backup_fs.DIR ]:
            dirsize.ask(sourcePath, FoundFolderSize, (self.pathID, dataID))
        # self.defer.callback('started', backupID)
        reactor.callLater(0, FireTaskStartedCallbacks, self.pathID, dataID)
        dhnio.Dprint(4, 'backup_control.Task.run %s [%s], size=%d' % (self.pathID, dataID, itemInfo.size))
        
def PutTask(pathID):
    t = Task(pathID)
    tasks().append(t)
    return t.number

def HasTask(pathID):
    for task in tasks():
        if task.pathID == pathID:
            return True
    return False 

def DeleteAllTasks():
    global _Tasks
    _Tasks = []
    
def RunTasks():
    if len(tasks()) == 0:
        return
    if len(jobs()) >= MAXIMUM_JOBS_STARTED:
        return
    T = tasks().pop(0)
    T.run()

def FoundFolderSize(pth, sz, arg):
    try:
        pathID, version = arg
        item = backup_fs.GetByID(pathID)
        if item:
            item.set_size(sz)
    except:
        dhnio.DprintException()
        
#------------------------------------------------------------------------------ 

def OnJobDone(backupID, result):
    dhnio.Dprint(4, 'backup_control.OnJobDone [%s] %s, %d more tasks' % (backupID, result, len(tasks())))
    jobs().pop(backupID)
    pathID, version = packetid.SplitBackupID(backupID)
    if result == 'done':
        maxBackupsNum = settings.getGeneralBackupsToKeep()
        if maxBackupsNum:
            item = backup_fs.GetByID(pathID)
            if item: 
                versions = item.list_versions(sorted=True, reverse=True)
                if len(versions) > maxBackupsNum: 
                    for version in versions[maxBackupsNum:]:
                        item.delete_version(version)
                        backupID = pathID+'/'+version
                        backup_rebuilder.RemoveBackupToWork(backupID)
                        io_throttle.DeleteBackupRequests(backupID)
                        transport_control.DeleteBackupInterest(backupID)
                        backup_fs.DeleteLocalBackup(settings.getLocalBackupsDir(), backupID)
                        backup_matrix.EraseBackupLocalInfo(backupID)
                        backup_matrix.EraseBackupLocalInfo(backupID)
        backup_fs.ScanID(pathID)
        backup_fs.Calculate()
        Save()
        # TODO check used space, if we have over use - stop all tasks immediately
        backup_matrix.RepaintBackup(backupID)
    elif result == 'abort':
        DeleteBackup(backupID)
    if len(tasks()) == 0:   
        # do we really need to restart backup_monitor after each backup?
        # if we have a lot tasks started this will produce a lot unneeded actions
        # will be smarter to restart it once we finish all tasks
        # because user will probable leave DHN working after starting a long running operation
        backup_monitor.Restart() 
    RunTasks()
    reactor.callLater(0, FireTaskFinishedCallbacks, pathID, version, result)
    
def OnTaskFailed(pathID, result):
    dhnio.Dprint(4, 'backup_control.OnTaskFailed [%s] %s, %d more tasks' % (pathID, result, len(tasks())))
    RunTasks()
    reactor.callLater(0, FireTaskFinishedCallbacks, pathID, None, result)
    
def OnBackupBlockReport(newblock, num_suppliers):
    backup_matrix.LocalBlockReport(newblock, num_suppliers)

#------------------------------------------------------------------------------ 

def AddTaskStartedCallback(pathID, callback):
    global _TaskStartedCallbacks
    if not _TaskStartedCallbacks.has_key(pathID):
        _TaskStartedCallbacks[pathID] = []
    _TaskStartedCallbacks[pathID].append(callback)
   
def AddTaskFinishedCallback(pathID, callback):
    global _TaskFinishedCallbacks
    if not _TaskFinishedCallbacks.has_key(pathID):
        _TaskFinishedCallbacks[pathID] = []
    _TaskFinishedCallbacks[pathID].append(callback)
    
def FireTaskStartedCallbacks(pathID, version):
    global _TaskStartedCallbacks
    for cb in _TaskStartedCallbacks.get(pathID, []):
        cb(pathID, version)
    _TaskStartedCallbacks.pop(pathID, None)

def FireTaskFinishedCallbacks(pathID, version, result):
    global _TaskFinishedCallbacks
    for cb in _TaskFinishedCallbacks.get(pathID, []):
        cb(pathID, version, result)
    _TaskFinishedCallbacks.pop(pathID, None)

#------------------------------------------------------------------------------ 

def StartSingle(pathID):
    PutTask(pathID)
    reactor.callLater(0, RunTasks)
    reactor.callLater(0, backup_monitor.Restart)

def StartRecursive(pathID):
    startedtasks = set()
    def visitor(path_id, path, info):
        if info.type == backup_fs.FILE:
            if path_id.startswith(pathID):
                PutTask(path_id)
                startedtasks.add(path_id)
    backup_fs.TraverseByID(visitor)
    reactor.callLater(0, RunTasks)
    reactor.callLater(0, backup_monitor.Restart)
    dhnio.Dprint(6, 'backup_control.StartRecursive %s  :  %d tasks started' % (pathID, len(startedtasks)))
    return startedtasks

#------------------------------------------------------------------------------ 

def IsBackupInProcess(backupID):
    return jobs().has_key(backupID)

def IsPathInProcess(pathID):
    for backupID in jobs().keys():
        if backupID.startswith(pathID+'/'):
            return True
    return False 

def HasRunningBackup():
    return len(jobs()) > 0

def AbortRunningBackup(backupID):
    if IsBackupInProcess(backupID):
        jobs()[backupID].abort()
        
def AbortAllRunningBackups():
    for backupObj in jobs().values():
        backupObj.abort()
        
def ListRunningBackups():
    return jobs().keys()

def GetRunningBackupObject(backupID):
    return jobs().get(backupID, None)

#------------------------------------------------------------------------------ 
#------------------------------------------------------------------------------ 
#------------------------------------------------------------------------------ 

def test():
#    backup_fs.Calculate()
#    print backup_fs.counter()
#    print backup_fs.numberfiles()
#    print backup_fs.sizefiles()
#    print backup_fs.sizebackups()
    import pprint
    pprint.pprint(backup_fs.fsID())
    pprint.pprint(backup_fs.fs())
    print backup_fs.GetByID('0')
    # pprint.pprint(backup_fs.WalkByID('0/0/2/19/F20140106100849AM'))
    # for pathID, localPath, item in backup_fs.IterateIDs():
    #     print pathID, misc.unicode_to_str_safe(localPath)
    # backup_fs.TraverseByIDSorted(lambda x, y, z: sys.stdout.write('%s %s\n' % (x,misc.unicode_to_str_safe(y))))
    

    
    
def test2():
    # reactor.callLater(1, StartDirRecursive, 'c:/temp')
    reactor.run()
    
#------------------------------------------------------------------------------ 

if __name__ == "__main__":
    dhnio.init()
    dhnio.SetDebug(20)
    settings.init()
    tmpfile.init(settings.getTempDir())
    contacts.init()
    eccmap.init()
    dhncrypto.InitMyKey()
    init()
    test()





