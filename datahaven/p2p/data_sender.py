#!/usr/bin/python
#data_sender.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

import os
import sys
import time

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in data_sender.py')

import lib.dhnio as dhnio
import lib.misc as misc
import lib.packetid as packetid
import lib.contacts as contacts
import lib.settings as settings
import lib.diskspace as diskspace
import lib.nameurl as nameurl
import lib.transport_control as transport_control
import lib.automat as automat
import lib.automats as automats

import io_throttle
import backup_matrix
import fire_hire
import contact_status
import backup_monitor

_DataSender = None
_ShutdownFlag = False

#------------------------------------------------------------------------------ 

def A(event=None, arg=None):
    global _DataSender
    if _DataSender is None:
        _DataSender = DataSender('data_sender', 'READY', 6)
    if event is not None:
        _DataSender.automat(event, arg)
    return _DataSender


class DataSender(automat.Automat):
    timers = {'timer-1min':     (60,     ['READY']),
              'timer-1sec':     (1,      ['SENDING'])
              }
    statistic = {}

    def state_changed(self, oldstate, newstate):
        automats.set_global_state('DATASEND ' + newstate)

    def A(self, event, arg):
        #---READY---
        if self.state is 'READY':
            if event == 'new-data' or event == 'timer-1min' or event == 'restart' :
                self.state = 'SCAN_BLOCKS'
                self.doScanAndQueue(arg)
            elif event == 'init' :
                pass
        #---SCAN_BLOCKS---
        elif self.state is 'SCAN_BLOCKS':
            if event == 'scan-done' and self.isQueueEmpty(arg) :
                self.state = 'READY'
                self.doRemoveUnusedFiles(arg)
                backup_monitor.A('restart')
            elif event == 'scan-done' and not self.isQueueEmpty(arg) :
                self.state = 'SENDING'
        #---SENDING---
        elif self.state is 'SENDING':
            if event == 'restart' or ( ( event == 'timer-1sec' or event == 'block-acked' or event == 'block-failed' ) and self.isQueueEmpty(arg) ) :
                self.state = 'SCAN_BLOCKS'
                self.doScanAndQueue(arg)
            elif event == 'timer-1sec' :
                self.doPrintStats(arg)

    def isQueueEmpty(self, arg):
        if not arg:
            return io_throttle.IsSendingQueueEmpty()
        remoteID, packetID = arg
        return io_throttle.OkToSend(remoteID)
    
    def doScanAndQueue(self, arg):
        global _ShutdownFlag
        dhnio.Dprint(10, 'data_sender.doScanAndQueue')
        log = open(os.path.join(settings.LogsDir(), 'data_sender.log'), 'w')
        log.write('doScanAndQueue %s\n' % time.asctime())
        if _ShutdownFlag:
            log.write('doScanAndQueue _ShutdownFlag is True\n')
            self.automat('scan-done')
            log.flush()
            log.close()
            return
        if '' not in contacts.getSupplierIDs():
            for backupID in misc.sorted_backup_ids(backup_matrix.local_files().keys(), True):
                packetsBySupplier = backup_matrix.ScanBlocksToSend(backupID)
                log.write('%s\n' % packetsBySupplier)
                for supplierNum in packetsBySupplier.keys():
                    supplier_idurl = contacts.getSupplierID(supplierNum)
                    if not supplier_idurl:
                        dhnio.Dprint(2, 'data_sender.doScanAndQueue WARNING ?supplierNum? %s for %s' % (supplierNum, backupID))
                        continue
                    for packetID in packetsBySupplier[supplierNum]:
                        backupID_, blockNum, supplierNum_, dataORparity = packetid.BidBnSnDp(packetID)
                        if backupID_ != backupID:
                            dhnio.Dprint(2, 'data_sender.doScanAndQueue WARNING ?backupID? %s for %s' % (packetID, backupID))
                            continue
                        if supplierNum_ != supplierNum:
                            dhnio.Dprint(2, 'data_sender.doScanAndQueue WARNING ?supplierNum? %s for %s' % (packetID, backupID))
                            continue
                        if io_throttle.HasPacketInSendQueue(supplier_idurl, packetID):
                            log.write('%s in the send queue to %s\n' % (packetID, supplier_idurl))
                            continue
                        if not io_throttle.OkToSend(supplier_idurl):
                            log.write('ok to send %s ? - NO!\n' % supplier_idurl)
                            continue
                        tranByiID = transport_control.transfers_by_idurl(supplier_idurl)
                        if len(tranByiID) > 3:
                            log.write('transfers by %s: %d\n' % (supplier_idurl, len(tranByiID)))
                            continue
                        filename = os.path.join(settings.getLocalBackupsDir(), packetID)
                        if not os.path.isfile(filename):
                            log.write('%s is not file\n' % filename)
                            continue
                        io_throttle.QueueSendFile(
                            filename, 
                            packetID, 
                            supplier_idurl, 
                            misc.getLocalID(), 
                            self.packetAcked, 
                            self.packetFailed)
                        log.write('io_throttle.QueueSendFile %s\n' % packetID)
                        # dhnio.Dprint(6, '  %s for %s' % (packetID, backupID))
        self.automat('scan-done')
        log.flush()
        log.close()
        
    def doPrintStats(self, arg):
        if dhnio.Debug(18):
            transfers = transport_control.current_transfers()
            bytes_stats = transport_control.current_bytes_transferred()
            s = ''
            for info in transfers:
                s += '%s ' % (diskspace.MakeStringFromBytes(bytes_stats[info.transfer_id]).replace(' ', '').replace('bytes', 'b'))
            dhnio.Dprint(0, 'transfers: ' + s[:120])

    def doRemoveUnusedFiles(self, arg):
        # we want to remove files for this block 
        # because we only need them during rebuilding
        if settings.getGeneralLocalBackups() is True:
            # if user set this in settings - he want to keep the local files
            return
        # ... user do not want to keep local backups
        if settings.getGeneralWaitSuppliers() is True:
            # but he want to be sure - all suppliers are green for a long time
            if contact_status.hasOfflineSuppliers() or time.time() - fire_hire.GetLastFireTime() < 24*60*60:
                # some people are not there or we do not have stable team yet
                # do not remove the files because we need it to rebuild
                return
        count = 0 
        for backupID in misc.sorted_backup_ids(backup_matrix.local_files().keys()):
            packets = backup_matrix.ScanBlocksToRemove(backupID, settings.getGeneralWaitSuppliers())
            for packetID in packets:
                filename = os.path.join(settings.getLocalBackupsDir(), packetID)
                if os.path.isfile(filename):
                    try:
                        os.remove(filename)
                        # dhnio.Dprint(6, '    ' + os.path.basename(filename))
                    except:
                        dhnio.DprintException()
                        continue
                    count += 1
        dhnio.Dprint(8, 'data_sender.doRemoveUnusedFiles %d files were removed' % count)
        backup_matrix.ReadLocalFiles()
                         
    def packetAcked(self, packet, ownerID, packetID):
        backupID, blockNum, supplierNum, dataORparity = packetid.BidBnSnDp(packetID)
        backup_matrix.RemoteFileReport(backupID, blockNum, supplierNum, dataORparity, True)
        if not self.statistic.has_key(ownerID):
            self.statistic[ownerID] = [0, 0]
        self.statistic[ownerID][0] += 1
        self.automat('block-acked', (ownerID, packetID))
    
    def packetFailed(self, remoteID, packetID, why):
        backupID, blockNum, supplierNum, dataORparity = packetid.BidBnSnDp(packetID)
        backup_matrix.RemoteFileReport(backupID, blockNum, supplierNum, dataORparity, False)
        if not self.statistic.has_key(remoteID):
            self.statistic[remoteID] = [0, 0]
        self.statistic[remoteID][1] += 1
        self.automat('block-failed', (remoteID, packetID))


def statistic():
    global _DataSender
    if _DataSender is None:
        return {}
    return _DataSender.statistic
    
def SetShutdownFlag():
    global _ShutdownFlag
    _ShutdownFlag = True
        
        
        
        
        
        
        

