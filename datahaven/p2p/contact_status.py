#!/usr/bin/python
#contact_status.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

"""
A state machine and several extra methods to keep track of current users's online state.
To do p2p communications need to know who is available and who is not.
A one instance of `contact_status()` machine is created for every remote contact and monitor his status. 
"""

import os
import sys
import time

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in contact_status.py')
    

import lib.dhnio as dhnio
import lib.nameurl as nameurl
import lib.transport_control as transport_control
import lib.contacts as contacts
import lib.identitycache as identitycache
import lib.automat as automat
import lib.settings as settings
import lib.commands as commands

if transport_control._TransportCSpaceEnable:
    import lib.transport_cspace as transport_cspace
if transport_control._TransportUDPEnable:
    import lib.transport_udp_session as transport_udp_session    

import ratings


_ContactsStatusDict = {}
_ShutdownFlag = False

#------------------------------------------------------------------------------ 


def init():
    """
    Needs to be called before other methods here.
    """
    dhnio.Dprint(4, 'contact_status.init')
    transport_control.AddInboxCallback(Inbox)
    transport_control.AddOutboxCallback(Outbox)
    transport_control.AddOutboxPacketStatusFunc(OutboxStatus)
    transport_control.AddWorkItemSentCallbackFunc(FileSent)
#    if transport_control._TransportCSpaceEnable:
#        transport_cspace.SetContactStatusNotifyFunc(CSpaceContactStatus)
#    if transport_control._TransportUDPEnable:
#        transport_udp_session.SetStateChangedCallbackFunc(TransportUDPSessionStateChanged)


def shutdown():
    """
    Called from top level code when the software is finishing.
    """
    dhnio.Dprint(4, 'contact_status.shutdown')
    global _ShutdownFlag
    global _ContactsStatusDict
    for A in _ContactsStatusDict.values():
        automat.clear_object(A.index)
    _ContactsStatusDict.clear()
    _ShutdownFlag = True
    

def isOnline(idurl):
    """
    Return True if given contact's state is ONLINE.
    """
    global _ShutdownFlag
    if _ShutdownFlag:
        return False
    if idurl in [None, 'None', '']:
        return False
    global _ContactsStatusDict
    if idurl not in _ContactsStatusDict.keys():
        dhnio.Dprint(6, 'contact_status.isOnline contact %s is not found, made a new instance' % idurl)
    return A(idurl).state == 'CONNECTED'


def isOffline(idurl):
    """
    Return True if given contact's state is OFFLINE.
    """
    global _ShutdownFlag
    if _ShutdownFlag:
        return True
    if idurl in [None, 'None', '']:
        return True
    global _ContactsStatusDict
    if idurl not in _ContactsStatusDict.keys():
        dhnio.Dprint(6, 'contact_status.isOffline contact %s is not found, made a new instance' % idurl)
    return A(idurl).state == 'OFFLINE'


def hasOfflineSuppliers():
    """
    Loops all suppliers and check their state, return True if at least one is OFFLINE.
    """
    for idurl in contacts.getSupplierIDs():
        if isOffline(idurl):
            return True
    return False


def countOfflineAmong(idurls_list):
    """
    Loops all IDs in `idurls_list` and count how many is OFFLINE.
    """
    num = 0
    for idurl in idurls_list:
        if isOffline(idurl):
            num += 1
    return num

def countOnlineAmong(idurls_list):
    """
    Loops all IDs in `idurls_list` and count how many is ONLINE.
    """
    num = 0
    for idurl in idurls_list:
        if idurl:
            if isOnline(idurl):
                num += 1
    return num

#------------------------------------------------------------------------------ 

def A(idurl, event=None, arg=None):
    """
    Access method to interact with a state machine created for given contact.
    """
    global _ShutdownFlag
    global _ContactsStatusDict
    if not _ContactsStatusDict.has_key(idurl):
        if _ShutdownFlag:
            return None
        _ContactsStatusDict[idurl] = ContactStatus(idurl, 'status_%s' % nameurl.GetName(idurl), 'OFFLINE', 10)
    if event is not None:
        _ContactsStatusDict[idurl].automat(event, arg)
    return _ContactsStatusDict[idurl]
      

class ContactStatus(automat.Automat):
    """
    A class to keep track of user's online status.
    """
    
    timers = {
        'timer-20sec': (20.0, ['PING', 'ACK?']),
        }
    
    def __init__(self, idurl, name, state, debug_level):
        self.idurl = idurl
        self.time_connected = None
        automat.Automat.__init__(self, name, state, debug_level)
        dhnio.Dprint(10, 'contact_status.ContactStatus %s %s %s' % (name, state, idurl))
        
    def state_changed(self, oldstate, newstate):
        dhnio.Dprint(6, '%s : [%s]->[%s]' % (nameurl.GetName(self.idurl), oldstate.lower(), newstate.lower()))
        
    def A(self, event, arg):
        #---CONNECTED---
        if self.state is 'CONNECTED':
            if event == 'outbox-packet' and self.isPingPacket(arg) :
                self.state = 'PING'
                self.AckCounter=0
                self.doRepaint(arg)
            elif event == 'sent-failed' and self.isDataPacket(arg) :
                self.state = 'OFFLINE'
                self.doRepaint(arg)
        #---OFFLINE---
        elif self.state is 'OFFLINE':
            if event == 'outbox-packet' and self.isPingPacket(arg) :
                self.state = 'PING'
                self.AckCounter=0
                self.doRepaint(arg)
            elif event == 'inbox-packet' :
                self.state = 'CONNECTED'
                self.doRememberTime(arg)
                self.doRepaint(arg)
        #---PING---
        elif self.state is 'PING':
            if event == 'sent-done' :
                self.state = 'ACK?'
                self.AckCounter=0
            elif event == 'inbox-packet' :
                self.state = 'CONNECTED'
                self.doRememberTime(arg)
                self.doRepaint(arg)
            elif event == 'file-sent' :
                self.AckCounter+=1
            elif event == 'sent-failed' and self.AckCounter>1 :
                self.AckCounter-=1
            elif event == 'timer-20sec' or ( event == 'sent-failed' and self.AckCounter==1 ) :
                self.state = 'OFFLINE'
                self.doRepaint(arg)
        #---ACK?---
        elif self.state is 'ACK?':
            if event == 'inbox-packet' :
                self.state = 'CONNECTED'
                self.doRememberTime(arg)
                self.doRepaint(arg)
            elif event == 'timer-20sec' :
                self.state = 'OFFLINE'
            elif event == 'outbox-packet' and self.isPingPacket(arg) :
                self.state = 'PING'
                self.AckCounter=0
                self.doRepaint(arg)

    def isPingPacket(self, arg):
        return arg.Command == commands.Identity() and arg.wide is True

    def isDataPacket(self, arg):
        return arg[0].command not in [commands.Identity(), commands.Ack()]

    def doRememberTime(self, arg):
        self.time_connected = time.time()
        
    def doRepaint(self, arg):
        if transport_control.GetContactAliveStateNotifierFunc() is not None:
            transport_control.GetContactAliveStateNotifierFunc()(self.idurl)
 
#------------------------------------------------------------------------------ 

def OutboxStatus(workitem, proto, host, status, error, message):
    """
    This method is called from `lib.transport_control` when got a status report after 
    sending a packet to remote peer. If packet sent was failed - user seems to be OFFLINE.   
    """
    if status == 'finished':
        A(workitem.remoteid, 'sent-done', (workitem, proto, host))
    else:
        A(workitem.remoteid, 'sent-failed', (workitem, proto, host))


def Inbox(newpacket, proto, host):
    """
    This is called when some `dhnpacket` was received from remote peer - user seems to be ONLINE.
    """
    A(newpacket.OwnerID, 'inbox-packet', (newpacket, proto, host))
    ratings.remember_connected_time(newpacket.OwnerID)
    

def Outbox(outpacket):
    """
    Called when some `dhnpacket` is placed in the sending queue.
    This packet can be our Identity packet - this is a sort of PING operation 
    to try to connect with that man.    
    """
    A(outpacket.RemoteID, 'outbox-packet', outpacket)


def FileSent(workitem, args):
    """
    This is called when transport_control starts the file transfer to some peer.
    Used to count how many times you PING him.
    """
    A(workitem.remoteid, 'file-sent', (workitem, args))


def PacketSendingTimeout(remoteID, packetID):
    """
    Called from `p2p.io_throttle` when some packet is timed out.
    Right now this do nothing, state machine ignores that event.
    """
    # dhnio.Dprint(6, 'contact_status.PacketSendingTimeout ' + remoteID)
    A(remoteID, 'sent-timeout', packetID)

