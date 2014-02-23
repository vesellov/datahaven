#!/usr/bin/env python
#central_connector.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#

import os
import sys

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in central_connector.py')
from twisted.internet.defer import Deferred, maybeDeferred
from twisted.internet.task import LoopingCall


import lib.dhnio as dhnio
import lib.misc as misc
import lib.packetid as packetid
import lib.settings as settings
import lib.contacts as contacts
import lib.transport_control as transport_control
if transport_control._TransportCSpaceEnable:
    import lib.transport_cspace as transport_cspace
from lib.automat import Automat


import lib.automats as automats
import network_connector
import p2p_connector
import central_service

import dhnicon
import money


_CentralConnector = None

#------------------------------------------------------------------------------ 

def A(event=None, arg=None):
    global _CentralConnector
    if _CentralConnector is None:
        _CentralConnector = CentralConnector('central_connector', 'AT_STARTUP', 4)
    if event is not None:
        _CentralConnector.automat(event, arg)
    return _CentralConnector

class CentralConnector(Automat):
    timers = {'timer-1hour':  (60*60, ['CONNECTED', 'DISCONNECTED', 'ONLY_ID']),
              'timer-30sec':  (30,    ['IDENTITY', 'REQUEST_SETTINGS', 'SETTINGS', 'SUPPLIERS', 'DISCONNECTED']),
              'timer-10sec':  (10,    ['IDENTITY'])}
    flagSettings = False

    def state_changed(self, oldstate, newstate):
        automats.set_global_state('CENTRAL ' + newstate)
        p2p_connector.A('central_connector.state', newstate)
        dhnicon.state_changed(network_connector.A().state, p2p_connector.A().state, self.state)

    def A(self, event, arg):
        #---AT_STARTUP---
        if self.state is 'AT_STARTUP':
            if event == 'propagate' :
                self.state = 'IDENTITY'
                self.flagSettings=False
                self.doInitCentralService(arg)
                self.doSendIdentity(arg)
        #---IDENTITY---
        elif self.state is 'IDENTITY':
            if event == 'identity-ack' and not self.isSettingsExist(arg) :
                self.state = 'REQUEST_SETTINGS'
                self.doSendRequestSettings(arg)
            elif event == 'identity-ack' and self.isSettingsExist(arg) and not self.flagSettings :
                self.state = 'SETTINGS'
                self.doSendSettings(arg)
            elif event == 'identity-ack' and self.isSettingsExist(arg) and self.flagSettings and not self.isSuppliersNeeded(arg) :
                self.state = 'CONNECTED'
                self.doSendRemainingPackets(arg)
            elif event == 'identity-ack' and self.flagSettings and self.isSettingsExist(arg) and self.isSuppliersNeeded(arg) :
                self.state = 'SUPPLIERS'
                self.doSendRequestSuppliers(arg)
            elif event == 'timer-10sec' :
                self.doSendIdentity(arg)
            elif event == 'timer-30sec' :
                self.state = 'DISCONNECTED'
        #---SETTINGS---
        elif self.state is 'SETTINGS':
            if event == 'settings-ack' :
                self.state = 'SUPPLIERS'
                self.flagSettings=True
            elif event == 'list-suppliers' :
                self.state = 'CONNECTED'
                self.flagSettings=True
                self.doSendRemainingPackets(arg)
            elif event == 'propagate' :
                self.state = 'IDENTITY'
                self.doSendIdentity(arg)
            elif event == 'timer-30sec' :
                self.state = 'ONLY_ID'
            elif event == 'settings' :
                self.doSendSettings(arg)
        #---REQUEST_SETTINGS---
        elif self.state is 'REQUEST_SETTINGS':
            if event == 'request-settings-ack' and self.isSuppliersNeeded(arg) :
                self.state = 'SUPPLIERS'
                self.flagSettings=True
                self.doSendRequestSuppliers(arg)
            elif event == 'request-settings-ack' and not self.isSuppliersNeeded(arg) :
                self.state = 'CONNECTED'
                self.flagSettings=True
                self.doSendRemainingPackets(arg)
            elif event == 'propagate' :
                self.state = 'IDENTITY'
                self.doSendIdentity(arg)
            elif event == 'timer-30sec' :
                self.state = 'ONLY_ID'
        #---SUPPLIERS---
        elif self.state is 'SUPPLIERS':
            if event == 'list-suppliers' or event == 'list-customers' :
                self.state = 'CONNECTED'
                self.doSendRemainingPackets(arg)
            elif event == 'propagate' :
                self.state = 'IDENTITY'
                self.doSendIdentity(arg)
            elif event == 'timer-30sec' :
                self.state = 'ONLY_ID'
        #---ONLY_ID---
        elif self.state is 'ONLY_ID':
            if event == 'propagate' or event == 'list-suppliers' or event == 'timer-1hour' or event == 'identity-ack' or event == 'list-customers' or event == 'settings' :
                self.state = 'IDENTITY'
                self.flagSettings=False
                self.doSendIdentity(arg)
        #---CONNECTED---
        elif self.state is 'CONNECTED':
            if event == 'settings' :
                self.state = 'SETTINGS'
                self.doSendSettings(arg)
                self.flagSettings=False
            elif event == 'propagate' or event == 'timer-1hour' :
                self.state = 'IDENTITY'
                self.doSendIdentity(arg)
        #---DISCONNECTED---
        elif self.state is 'DISCONNECTED':
            if event == 'propagate' or event == 'list-suppliers' or event == 'timer-1hour' or event == 'identity-ack' or event == 'list-customers' or event == 'settings' or ( event == 'p2p_connector.state' and arg is 'CONNECTED' ) or ( event == 'timer-30sec' and self.isCSpaceOnline(arg) ) :
                self.state = 'IDENTITY'
                self.flagSettings=False
                self.doSendIdentity(arg)

    def isSettingsExist(self, arg):
        return settings.getCentralNumSuppliers() > 0

    def isSuppliersNeeded(self, arg):
        return settings.getCentralNumSuppliers() <= 0 or \
               contacts.numSuppliers() != settings.getCentralNumSuppliers()

    def _saveRequestedSettings(self, newpacket):
        sd = dhnio._unpack_dict(newpacket.Payload)
        settings.uconfig().set('central-settings.needed-megabytes', sd.get('n', str(settings.DefaultNeededMb()))+'MB')
        settings.uconfig().set('central-settings.shared-megabytes', sd.get('d', str(settings.DefaultDonatedMb()))+'MB')
        settings.uconfig().set('central-settings.desired-suppliers', sd.get('s', '2'))
        settings.uconfig().set('emergency.emergency-email', sd.get('e1', ''))
        settings.uconfig().set('emergency.emergency-phone', sd.get('e2', ''))
        settings.uconfig().set('emergency.emergency-fax', sd.get('e3', ''))
        settings.uconfig().set('emergency.emergency-text', sd.get('e4', '').replace('<br>', '\n'))
        settings.uconfig().update()
        reactor.callLater(0, self.automat, 'request-settings-ack', newpacket)

    def doInitCentralService(self, arg):
        central_service.init()

    def doSendIdentity(self, arg):
        transport_control.RegisterInterest(
            lambda packet: self.automat('identity-ack', packet),
            settings.CentralID(),
            central_service.SendIdentity(True))

    def doSendSettings(self, arg):
        packetID = packetid.UniqueID()
        transport_control.RegisterInterest(
            self.settingsAck,
            settings.CentralID(),
            packetID)
        central_service.SendSettings(True, packetID)

    def doSendRequestSettings(self, arg):
        transport_control.RegisterInterest(
            lambda packet: self._saveRequestedSettings(packet),
            settings.CentralID(),
            central_service.SendRequestSettings(True))

    def doSendRequestSuppliers(self, arg):
        return central_service.SendRequestSuppliers()

    def isCSpaceOnline(self, arg):
        if not transport_control._TransportCSpaceEnable:
            return False
        if not settings.enableCSpace():
            return False
        if not transport_cspace.registered():
            return False
        return transport_cspace.A().state == 'ONLINE'

    def settingsAck(self, packet):
        try:
            status, last_receipt, = packet.Payload.split('\n', 2)
            last_receipt = int(last_receipt)
        except:
            status = 'error'
            last_receipt = -1
        dhnio.Dprint(4, 'central_connector.settingsAck [%s] last_receipt=%d' % (status, last_receipt))
        missing_receipts = money.SearchMissingReceipts(last_receipt)
        if len(missing_receipts) > 0:
            reactor.callLater(0, central_service.SendRequestReceipt, missing_receipts)
        self.automat('settings-ack', packet)

    def doSendRemainingPackets(self, arg):
        central_service.LoopSendBandwidthReport()
        central_service.SendRequestMarketList()

        
        
