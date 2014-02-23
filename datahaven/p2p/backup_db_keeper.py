#!/usr/bin/python
#backup_db_keeper.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

import os
import sys
import time

#------------------------------------------------------------------------------ 

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in backup_rebuilder.py')
    
import lib.dhnio as dhnio
import lib.misc as misc
import lib.contacts as contacts
import lib.settings as settings
import lib.transport_control as transport_control
import lib.dhnpacket as dhnpacket
import lib.commands as commands
import lib.dhncrypto as dhncrypto
import lib.automats as automats
from lib.automat import Automat

import dhnblock
import p2p_connector
import contact_status


_BackupDBKeeper = None
   
#------------------------------------------------------------------------------ 

def A(event=None, arg=None):
    global _BackupDBKeeper
    if _BackupDBKeeper is None:
        _BackupDBKeeper = BackupDBKeeper('backup_db_keeper', 'AT_STARTUP', 4)
    if event is not None:
        _BackupDBKeeper.automat(event, arg)
    return _BackupDBKeeper
    
#------------------------------------------------------------------------------ 

class BackupDBKeeper(Automat):
    timers = {'timer-1sec':     (1,     ['RESTART']),
              'timer-30sec':    (30,    ['RESTART', 'REQUEST', 'SENDING']),
              'timer-1hour':    (60*60, ['READY']),}
    
    def init(self):
        self.requestedSuppliers = set()
        self.sentSuppliers = set()
        self.lastRestartTime = 0
        self.syncFlag = False

    def A(self, event, arg):
        #---AT_STARTUP---
        if self.state is 'AT_STARTUP':
            if event == 'restart' :
                self.state = 'RESTART'
            elif event == 'init' :
                self.state = 'READY'
        #---RESTART---
        elif self.state is 'RESTART':
            if event == 'timer-1sec' and self.isTimePassed(arg) and p2p_connector.A().state is 'CONNECTED' :
                self.state = 'REQUEST'
                self.doSuppliersRequestDBInfo(arg)
                self.doRememberTime(arg)
            elif event == 'timer-30sec' :
                self.state = 'READY'
        #---REQUEST---
        elif self.state is 'REQUEST':
            if event == 'restart' :
                self.state = 'RESTART'
            elif ( event == 'incoming-db-info' and self.isAllSuppliersResponded(arg) ) or event == 'timer-30sec' :
                self.state = 'SENDING'
                self.doSuppliersSendDBInfo(arg)
        #---SENDING---
        elif self.state is 'SENDING':
            if event == 'restart' :
                self.state = 'RESTART'
            elif event == 'db-info-acked' and self.isAllSuppliersAcked(arg) :
                self.state = 'READY'
                self.doSetSyncFlag(arg)
            elif event == 'timer-30sec' :
                self.state = 'READY'
            elif event == 'db-info-acked' and not self.isAllSuppliersAcked(arg) :
                self.doSetSyncFlag(arg)
        #---READY---
        elif self.state is 'READY':
            if event == 'timer-1hour' or event == 'restart' :
                self.state = 'RESTART'

    def isAllSuppliersResponded(self, arg):
        return len(self.requestedSuppliers) == 0
            
    def isAllSuppliersAcked(self, arg):
        return len(self.sentSuppliers) == 0

    def isTimePassed(self, arg):
        return time.time() - self.lastRestartTime > settings.BackupDBSynchronizeDelay()
    
    def doRememberTime(self, arg):
        self.lastRestartTime = time.time()        
    
    def doSuppliersRequestDBInfo(self, arg):
        # dhnio.Dprint(4, 'backup_db_keeper.doSuppliersRequestDBInfo')
        # packetID_ = settings.BackupInfoFileName()
        # packetID = settings.BackupInfoEncryptedFileName()
        packetID = settings.BackupIndexFileName()
        for supplierId in contacts.getSupplierIDs():
            if supplierId:
                transport_control.RemoveInterest(supplierId, packetID)
        self.requestedSuppliers.clear()
        Payload = ''
        localID = misc.getLocalID()
        for supplierId in contacts.getSupplierIDs():
            if not supplierId:
                continue
            newpacket = dhnpacket.dhnpacket(commands.Retrieve(), localID, localID, packetID, Payload, supplierId)
            transport_control.outboxAck(newpacket)
            transport_control.RegisterInterest(self.SupplierResponse, supplierId, packetID)
            self.requestedSuppliers.add(supplierId)

    def doSuppliersSendDBInfo(self, arg):
        # dhnio.Dprint(4, 'backup_db_keeper.doSuppliersSendDBInfo')
        # packetID = settings.BackupInfoEncryptedFileName()
        packetID = settings.BackupIndexFileName()
        for supplierId in contacts.getSupplierIDs():
            if supplierId:
                transport_control.RemoveInterest(supplierId, packetID)
        self.sentSuppliers.clear()
        # src = dhnio.ReadBinaryFile(settings.BackupInfoFileFullPath())
        src = dhnio.ReadBinaryFile(settings.BackupIndexFilePath())
        localID = misc.getLocalID()
        block = dhnblock.dhnblock(localID, packetID, 0, dhncrypto.NewSessionKey(), dhncrypto.SessionKeyType(), True, src)
        Payload = block.Serialize() 
        for supplierId in contacts.getSupplierIDs():
            if not supplierId:
                continue
            if not contact_status.isOnline(supplierId):
                continue
            newpacket = dhnpacket.dhnpacket(commands.Data(), localID, localID, packetID, Payload, supplierId)
            transport_control.outboxAck(newpacket)
            transport_control.RegisterInterest(self.SupplierAcked, supplierId, packetID)
            self.sentSuppliers.add(supplierId)
            # dhnio.Dprint(6, 'backup_db_keeper.doSuppliersSendDBInfo to %s' % supplierId)

    def doSetSyncFlag(self, arg):
        if not self.syncFlag:
            dhnio.Dprint(4, 'backup_db_keeper.doSetSyncFlag backup database is now SYNCHRONIZED !!!!!!!!!!!!!!!!!!!!!!')
        self.syncFlag = True

    def SupplierResponse(self, packet):
        self.requestedSuppliers.discard(packet.OwnerID)

    def SupplierAcked(self, packet):
        self.sentSuppliers.discard(packet.OwnerID)
        self.automat('db-info-acked', packet.OwnerID)
    
    def IsSynchronized(self):
        return self.syncFlag
    
    

