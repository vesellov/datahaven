#!/usr/bin/python
#backup_monitor.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

"""
This is a state machine to manage rebuilding process of all backups.

Do several operations periodically:
    1) ping all suppliers
    2) request ListFiles from all suppliers
    3) prepare a list of backups to put some work to rebuild
    4) run rebuilding process and wait to finish
    5) make decision to replace one unreliable supplier with fresh one
"""


import os
import sys
import time
import random
import gc


try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in backup_monitor.py')

from twisted.internet.defer import Deferred, maybeDeferred
from twisted.internet import threads

import lib.dhnio as dhnio
import lib.misc as misc
import lib.nameurl as nameurl
import lib.transport_control as transport_control
import lib.settings as settings
import lib.contacts as contacts
import lib.tmpfile as tmpfile
import lib.diskspace as diskspace
import lib.automat as automat
import lib.automats as automats

import backup_rebuilder
import fire_hire
import list_files_orator 
import contact_status

import identitypropagate
import backup_matrix
import backup_fs
import backup_control
import central_service

#------------------------------------------------------------------------------ 

_BackupMonitor = None

#------------------------------------------------------------------------------ 

def A(event=None, arg=None):
    """
    Access method to interact with the state machine.
    """
    global _BackupMonitor
    if _BackupMonitor is None:
        _BackupMonitor = BackupMonitor('backup_monitor', 'READY', 4)
    if event is not None:
        _BackupMonitor.automat(event, arg)
    return _BackupMonitor


class BackupMonitor(automat.Automat):
    """
    A class to monitor backups and manage rebuilding process.
    """
    
    timers = {'timer-1sec':   (1,       ['RESTART', 'PING']), 
              'timer-10sec':  (20,      ['PING']),
              # 'timer-10min':  (10*60,   ['READY']), 
              }
    ackCounter = 0
    pingTime = 0
    lastRequestSuppliersTime = 0

    def state_changed(self, oldstate, newstate):
        """
        This method is called every time when my state is changed. 
        """
        automats.set_global_state('MONITOR ' + newstate)

    def A(self, event, arg):
        """
        The state machine code, generated using visio2python tool.
        """
        #---READY---
        if self.state is 'READY':
            if event == 'init' :
                backup_rebuilder.A('init')
            elif event == 'restart' :
                self.state = 'RESTART'
        #---RESTART---
        elif self.state is 'RESTART':
            if event == 'timer-1sec' and not self.isAnyBackupRunning(arg) and backup_rebuilder.A().state in [ 'STOPPED', 'DONE', ] :
                self.state = 'PING'
                self.doPingAllSuppliers(arg)
        #---PING---
        elif self.state is 'PING':
            if event == 'timer-10sec' or ( event == 'timer-1sec' and self.isAllSuppliersResponded(arg) ) :
                self.state = 'LIST_FILES'
                list_files_orator.A('need-files')
            elif event == 'restart' :
                self.state = 'RESTART'
        #---LIST_FILES---
        elif self.state is 'LIST_FILES':
            if event == 'restart' :
                self.state = 'RESTART'
            elif ( event == 'list_files_orator.state' and arg is 'NO_FILES' ) :
                self.state = 'READY'
            elif ( event == 'list_files_orator.state' and arg is 'SAW_FILES' ) :
                self.state = 'LIST_BACKUPS'
                self.doPrepareListBackups(arg)
        #---LIST_BACKUPS---
        elif self.state is 'LIST_BACKUPS':
            if event == 'list-backups-done' :
                self.state = 'REBUILDING'
                backup_rebuilder.A('start')
            elif event == 'restart' :
                self.state = 'RESTART'
        #---REBUILDING---
        elif self.state is 'REBUILDING':
            if event == 'restart' :
                self.state = 'RESTART'
                backup_rebuilder.SetStoppedFlag()
            elif ( event == 'backup_rebuilder.state' and arg is 'STOPPED' ) :
                self.state = 'READY'
            elif ( event == 'backup_rebuilder.state' and arg is 'DONE' ) :
                self.state = 'FIRE_HIRE'
                fire_hire.A('start')
        #---FIRE_HIRE---
        elif self.state is 'FIRE_HIRE':
            if event == 'fire-hire-finished' :
                self.state = 'READY'
                self.doCleanUpBackups(arg)
            elif event == 'restart' or event == 'hire-new-supplier' :
                self.state = 'RESTART'

    def isAllSuppliersResponded(self, arg):
        onlines = contact_status.countOnlineAmong(contacts.getSupplierIDs())
        # dhnio.Dprint(6, 'backup_monitor.isAllSuppliersResponded ackCounter=%d onlines=%d' % (self.ackCounter, onlines))
        if self.ackCounter == contacts.numSuppliers():
            return True
        if self.ackCounter >= onlines - 1:
            return True
        return False

    def doPingAllSuppliers(self, arg):
        # check our suppliers first, if we do not have enough yet - do request
        if '' in contacts.getSupplierIDs():
            dhnio.Dprint(4, 'backup_monitor.doPingAllSuppliers found empty suppliers !!!!!!!!!!!!!!')
            self.ackCounter = contacts.numSuppliers()
            if time.time() - self.lastRequestSuppliersTime > 10 * 60:
                central_service.SendRequestSuppliers()
                self.lastRequestSuppliersTime = time.time()
            return
        # do not want to ping very often 
        if time.time() - self.pingTime < 60 * 3:
            self.ackCounter = contacts.numSuppliers()
            return
        self.pingTime = time.time()
        self.ackCounter = 0
        def increaseAckCounter(packet):
            self.ackCounter += 1
        dhnio.Dprint(6, 'backup_monitor.doPingAllSuppliers going to call suppliers')
        identitypropagate.suppliers(increaseAckCounter, True)

    def doPrepareListBackups(self, arg):
        if backup_control.HasRunningBackup():
            # if some backups are running right now no need to rebuild something - too much use of CPU
            backup_rebuilder.RemoveAllBackupsToWork()
            dhnio.Dprint(6, 'backup_monitor.doPrepareListBackups skip all rebuilds')
            self.automat('list-backups-done')
            return 
        # take remote and local backups and get union from it 
        allBackupIDs = set(backup_matrix.local_files().keys() + backup_matrix.remote_files().keys())
        # take only backups from data base
        allBackupIDs.intersection_update(backup_fs.ListAllBackupIDs())
        # remove running backups
        allBackupIDs.difference_update(backup_control.ListRunningBackups())
        # sort it in reverse order - newer backups should be repaired first
        allBackupIDs = misc.sorted_backup_ids(list(allBackupIDs), True)
        # add backups to the queue
        backup_rebuilder.AddBackupsToWork(allBackupIDs)
        dhnio.Dprint(6, 'backup_monitor.doPrepareListBackups %d items' % len(allBackupIDs))
        self.automat('list-backups-done')

    def doCleanUpBackups(self, arg):
        # here we check all backups we have and remove the old one
        # user can set how many versions of that file of folder to keep 
        # other versions (older) will be removed here  
        versionsToKeep = settings.getGeneralBackupsToKeep()
        bytesUsed = backup_fs.sizebackups()/contacts.numSuppliers()
        bytesNeeded = diskspace.GetBytesFromString(settings.getCentralMegabytesNeeded(), 0) 
        dhnio.Dprint(6, 'backup_monitor.doCleanUpBackups backupsToKeep=%d used=%d needed=%d' % (versionsToKeep, bytesUsed, bytesNeeded))
        delete_count = 0
        if versionsToKeep > 0:
            for pathID, localPath, itemInfo in backup_fs.IterateIDs():
                versions = itemInfo.list_versions()
                # TODO do we need to sort the list? it comes from a set, so must be sorted may be
                while len(versions) > versionsToKeep:
                    backupID = pathID + '/' + versions.pop(0)
                    dhnio.Dprint(6, 'backup_monitor.doCleanUpBackups %d of %d backups for %s, so remove older %s' % (len(versions), versionsToKeep, localPath, backupID))
                    backup_control.DeleteBackup(backupID, saveDB=False, calculate=False)
                    delete_count += 1
        # we need also to fit used space into needed space (given from other users)
        # they trust us - do not need to take extra space from our friends
        # so remove oldest backups, but keep at least one for every folder - at least locally!
        # still our suppliers will remove our "extra" files by their "local_tester"
        if bytesNeeded <= bytesUsed:
            sizeOk = False 
            for pathID, localPath, itemInfo in backup_fs.IterateIDs():
                if sizeOk:
                    break
                versions = itemInfo.list_versions(True, False)
                if len(versions) <= 1:
                    continue
                for version in versions[1:]:
                    backupID = pathID+'/'+version
                    versionInfo = itemInfo.get_version_info(version)
                    if versionInfo[1] > 0:
                        dhnio.Dprint(6, 'backup_monitor.doCleanUpBackups over use %d of %d, so remove %s of %s' % (
                            bytesUsed, bytesNeeded, backupID, localPath))
                        backup_control.DeleteBackup(backupID, saveDB=False, calculate=False)
                        delete_count += 1
                        bytesUsed -= versionInfo[1] 
                        if bytesNeeded > bytesUsed:
                            sizeOk = True
                            break
        if delete_count > 0:
            backup_fs.Scan()
            backup_fs.Calculate()
            backup_control.Save() 
        collected = gc.collect()
        dhnio.Dprint(6, 'backup_monitor.doCleanUpBackups collected %d objects' % collected)



    def isAnyBackupRunning(self, arg):
        return backup_control.HasRunningBackup()

def Restart():
    """
    Just sends a "restart" event to the state machine.
    """
    dhnio.Dprint(4, 'backup_monitor.Restart')
    A('restart')


def shutdown():
    """
    Called from high level modules to finish all things correctly.
    """
    dhnio.Dprint(4, 'backup_monitor.shutdown')
    automat.clear_object(A().index)

        


