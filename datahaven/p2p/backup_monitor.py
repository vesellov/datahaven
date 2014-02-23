#!/usr/bin/python
#backup_monitor.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#This does a bunch of things.  
#1)  monitor the lists of file sent back from suppliers,
#    if there is a gap we need to try to fix it
#    * main class is _BackupMonitor,
#      it saves the lists of files in _BackupListFiles,
#      breaks down the lists of files into info on a single backup in _SupplierBackupInfo
#    * _BlockRebuilder takes care of a single broken block,
#      request what we have available, builds whatever we can
#      and stops either when we have fixed everything
#      or there is nothing more we can do
#    * _BlockRebuilder requests files through io_throttle and sends out the fixed files
#      also through io_throttle
#
#2)  if a backup is unfixable, not enough information, we delete it CleanupBackups in _BackupMonitor
#
#3)  every hour it requests a list of files from each supplier - _hourlyRequestListFiles
#
#4)  every hour it tests a file from each supplier,
#    seeing if they have the data they claim,
#    and that it is correct
#    * data is stored in _SuppliersSet and _SupplierRemoteTestResults,
#    was data good, bad, being rebuilt, or they weren't online 
#    and we got no data on the result
#    * if a supplier hasn't been seen in settings.FireInactiveSupplierIntervalHours()
#    we replace them
#
#
# Strategy for automatic backups
#
# 1) Full backup to alternating set of nodes every 2 weeks.
#
# 2) Full monthly, then incremental weekly and daily
#
# 3) One time full and then incremental monthly, weekly
#
# 4) Break alphabetical list of files into N parts and do full
#    backup on one of those and incrementals on the rest.
#    So we no longer need part of the incremental history
#      every time, and after N times older stuff can toss.
#      so every day is part full and part incremental.  Cool.
#
#  Want user to be able to specify what he wants, or at least
#  select from a few reasonable choices.
#
#
# May just do (1) to start with.
#
# This code also wakes up every day and fires off localtester, remotetester
#   on some reasonable random stuff.
#
# This manages the whole thing, so after GUI, this has the highest level control functions.
#
# Some competitors let people choose what days to backup on.  Not sure this
#   is really so great though, once we have incremental.
#
# Some can handle partial file changes.  So if a 500 MB mail file only has
# a little bit appended, only the little bit is backed up.
#
# Some competitors can turn the computer off after a backup, but
# we need it to stay on for P2P stuff.
#
# need to record if zip, tar, dump, etc
#
# If we do regular full backups often, then we might not bother scrubbing older stuff.
# Could reduce the bandwidth needed (since scrubbing could use alot.l


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

_BackupMonitor = None

#------------------------------------------------------------------------------ 

def A(event=None, arg=None):
    global _BackupMonitor
    if _BackupMonitor is None:
        _BackupMonitor = BackupMonitor('backup_monitor', 'READY', 4)
    if event is not None:
        _BackupMonitor.automat(event, arg)
    return _BackupMonitor


class BackupMonitor(automat.Automat):
    timers = {'timer-1sec':   (1,       ['RESTART', 'PING']), 
              'timer-10sec':  (20,      ['PING']),
              # 'timer-10min':  (10*60,   ['READY']), 
              }
    ackCounter = 0
    pingTime = 0
    lastRequestSuppliersTime = 0

    def state_changed(self, oldstate, newstate):
        automats.set_global_state('MONITOR ' + newstate)

    def A(self, event, arg):
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
    dhnio.Dprint(4, 'backup_monitor.Restart')
    A('restart')


def shutdown():
    dhnio.Dprint(4, 'backup_monitor.shutdown')
    automat.clear_object(A().index)

        


