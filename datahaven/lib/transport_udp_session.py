#!/usr/bin/python
#transport_udp_session.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#


import os
import sys
import time
import struct
import cStringIO


from twisted.internet import reactor


import dhnio
import settings
import misc
import identitycache
import tmpfile 
import nameurl
import contacts

import automat

#------------------------------------------------------------------------------ 

DHN_STUN_SERVERS = set([
    ('67.207.147.183', 13478),
    ('208.78.96.185', 13478),
    ('178.49.192.122', 13478),
    ])

DHN_STUN_COMMANDS = { 'ROUTE':       'r:',
                     }

#------------------------------------------------------------------------------ 

CODES = {'p:':  'PING',
         'g:':  'GREETING',
         'd:':  'DATA',
         'r:':  'REPORT',
         'a:':  'ALIVE',}

COMMANDS = {'PING':         'p:',
            'GREETING':     'g:',
            'DATA':         'd:',
            'REPORT':       'r:',
            'ALIVE':        'a:',}

BLOCK_SIZE_LEVELS = {   0: 508,
                        1: 1460,
                        2: 2048,
                        3: 3072,
                        4: 4096,
                        5: 5120,
                        6: 6144,
                        7: 7168,
                        8: 8124,
                        }
#sz = 508
#BLOCK_SIZE_LEVELS = {   #0: 508,
#                        0: sz,
#                        1: sz,
#                        2: sz,
#                        3: sz,
#                        4: sz,
#                        5: sz,
#                        6: sz,
#                        7: sz,
#                        }
MAX_BLOCK_SIZE_LEVEL = len(BLOCK_SIZE_LEVELS) - 1

BLOCK_RETRIES = 999999
MAX_WINDOW_SIZE = 32
MIN_WINDOW_SIZE = 1
MAX_ACK_TIME_OUT = 4.0
MIN_ACK_TIME_OUT = 0.5
MAX_TIMEOUTS_RATIO = 0.5
FINE_TIMEOUTS_RATIO = 0.0

#------------------------------------------------------------------------------ 

_ParentObject = None

_IdToAddress = {}
_AddressToId = {}

_SendStatusCallback = None
_ReceiveStatusCallback = None
_SendControlFunc = None
_ReceiveControlFunc = None
_RegisterTransferFunc = None
_UnRegisterTransferFunc = None
_StateChangedCallbackFunc = None
_NetworkAddressChangedFunc = None

_TimerPing = None
_TimerAlive = None
_Timer30sec = None

_SendingDelay = 0.01
_SendingTask = None

_OutboxQueueDelay = 0.01
_OutboxQueueTask = None

#------------------------------------------------------------------------------ 

def init(parent):
    global _ParentObject
    dhnio.Dprint(4, 'transport_udp_session.init')
    _ParentObject = parent
    reactor.callLater(0, process_outbox_queue)
    reactor.callLater(1, process_sessions)
    StartTimers()

   
def shutdown():
    dhnio.Dprint(4, 'transport_udp_session.shutdown')
    StopTimers()
    
   
def A(address, event=None, arg=None):
    s = open_session(address)
    if event is not None:
        s.automat(event, arg)
    return s
      
      
def parent():
    global _ParentObject
    return _ParentObject

#------------------------------------------------------------------------------ 

def dhn_stun_servers_enabled():
    return True

def dhn_stun_servers_request(transport, datagram):
    for addr in DHN_STUN_SERVERS:
        try:
            transport.write(datagram, addr)
        except:
            pass

def dhn_stun_server_response(datagram, address):
    try:
        myipport, peeridurl, peeripport, deltatime = datagram.split(' ')
        if peeripport == '0':
            return
        myip, myport = myipport.split(':')
        myport = int(myport)
        peerip, peerport = peeripport.split(':')
        peerport = int(peerport)
    except:
        dhnio.DprintException()    
        return False
    myaddress = (myip, myport)
    peeraddress = (peerip, peerport)
    x, ip, port, x = misc.getLocalIdentity().getProtoParts('udp')
    # if ip and port and ip != myip and str(port) != str(myport):
        # network_address_changed(myaddress)
        # return
    mappedaddress = peeraddress
    if identitycache.HasLocalIP(peeridurl):
        mappedaddress = (identitycache.GetLocalIP(peeridurl), peeraddress[1]) 
    if mappedaddress != peeraddress:
        if not is_session_opened(mappedaddress):
            s = open_session(mappedaddress)
            dhnio.Dprint(6, 'transport_udp_session.dhn_stun_server_response made a new LOCAL session %s for user [%s], address=%s' % (s.name, nameurl.GetName(peeridurl), str(mappedaddress)))
            s.event('init', peeridurl)
            s.routed = True
    else:
        if not is_session_opened(peeraddress):
            s = open_session(peeraddress)
            dhnio.Dprint(6, 'transport_udp_session.dhn_stun_server_response made a new session %s for user [%s]' % (s.name, nameurl.GetName(peeridurl)))
            s.event('init', peeridurl)
            s.routed = True

def network_address_changed(newaddress):        
    global _NetworkAddressChangedFunc
    if _NetworkAddressChangedFunc is not None:
        _NetworkAddressChangedFunc(newaddress)

#------------------------------------------------------------------------------ 
    
class OutboxFile():
    def __init__(self, peer, remote_idurl, file_id, filename, filesize, description=''):
        global _RegisterTransferFunc
        self.peer = peer
        self.remote_idurl = remote_idurl
        self.file_id = file_id
        self.filename = filename
        # self.transfer_id = transfer_id
        self.description = description
        self.size = filesize
        self.blocks = {} 
        self.num_blocks = 0
        self.bytes_sent = 0
        self.bytes_out = 0
        self.block_id = -1
        self.blocks_timeouts = 0
        self.blocks_counter = 0
        # self.failed_blocks = {}
        # self.has_failed_blocks = False
        self.started = time.time()
        self.timeout = max( int(self.size/settings.SendingSpeedLimit()), 5)
        self.transfer_id = None
        if _RegisterTransferFunc is not None:
            self.transfer_id = _RegisterTransferFunc('send', 
                self.peer.remote_address, self.get_bytes_sent, self.filename, self.size, self.description)
            # _RegisterTransferFunc(callback=self.get_bytes_sent, transfer_id=self.transfer_id)
        # dhnio.Dprint(6, 'transport_udp_session.OutboxFile [%d] to %s' % (self.file_id, nameurl.GetName(self.remote_idurl)))

    def close(self):
        global _UnRegisterTransferFunc
        if _UnRegisterTransferFunc and self.transfer_id:
            _UnRegisterTransferFunc(self.transfer_id)
        # dhnio.Dprint(6, 'transport_udp_session.OutboxFile close [%d] to %s (%s)' % (self.file_id, nameurl.GetName(self.remote_idurl), str(self.peer)))
        # dt = time.time() - self.started 
        # print 'DONE', self.bytes_sent, self.bytes_out, dt, (self.bytes_sent/1024.0)/dt 

    def get_bytes_sent(self):
        return self.bytes_sent 

    def report_block(self, block_id):
        if not self.blocks.has_key(block_id):
            dhnio.Dprint(10, 'transport_udp_session.report_block WARNING unknown block_id in REPORT packet received from %s: [%d]' % (self.peer.remote_address, block_id))
            return
        self.bytes_sent += len(self.blocks[block_id])
        del self.blocks[block_id]
        # sys.stdout.write('%d <<<\n' % block_id)

    def send(self):
        do_send = False
        while len(self.peer.sliding_window) < self.peer.sliding_window_size and self.block_id < self.num_blocks and self.block_id >= 0:
            if not self.send_block(self.block_id):
                break
            self.peer.sliding_window[(self.file_id, self.block_id)] = time.time()
            self.block_id += 1
            do_send = True
        return do_send
    
    def check_blocks_timeouts(self):
        if self.blocks_counter < 10:
            return 0
        ratio = float(self.blocks_timeouts) / float(self.blocks_counter)
        self.blocks_counter = 0
        self.blocks_timeouts = 0
        return ratio
        
    def send_block(self, block_id):
        global _SendControlFunc
        if not self.blocks.has_key(block_id):
            dhnio.Dprint(8, 'transport_udp_session.send_block WARNING block_id=%d not found, file_id=%s, transfer_id=%s, blocks: %d' % (
                block_id, self.file_id, str(self.transfer_id), len(self.blocks) ))
            return False
        data = self.blocks[block_id]
        if _SendControlFunc is not None:
            more_bytes = _SendControlFunc(self.peer.last_bytes_sent, len(data))
            if more_bytes < len(data):
                return False
        self.peer.last_bytes_sent = len(data)
        datagram = COMMANDS['DATA']
        datagram += struct.pack('i', self.file_id)
        datagram += struct.pack('i', block_id)
        datagram += struct.pack('i', self.num_blocks)
        datagram += struct.pack('i', len(data))
        datagram += data
        self.bytes_out += len(data)
        # sys.stdout.write('>>> %d\n' % block_id)
        return self.peer.sendDatagram(datagram)

#    def mark_failed_block(self, block_id):
#        if not self.failed_blocks.has_key(block_id):
#            self.failed_blocks[block_id] = 0
#        self.failed_blocks[block_id] += 1
#        if self.failed_blocks[block_id] >= BLOCK_RETRIES:
#            self.has_failed_blocks = True
#            dhnio.Dprint(14, 'transport_udp_session.mark_failed_block (%d,%d) is failed to send, so transfer %s is failed' % (self.file_id, block_id, self.transfer_id))
#            return True
#        return False
    
    def read_blocks(self):
        fin = open(self.filename, 'rb')
        block_id = 0
        while True:
            block_data = fin.read(BLOCK_SIZE_LEVELS[self.peer.block_size_level])
            if block_data == '':
                break
            self.blocks[block_id] = block_data
            block_id += 1  
        fin.close()
        self.num_blocks = block_id
        self.block_id = 0     
        
    def is_timed_out(self):
        return time.time() - self.started > self.timeout

    def cancel(self):
        dhnio.Dprint(6, 'transport_udp_session.OutboxFile cancel timeout=%d' % self.timeout)
        self.timeout = 0

#------------------------------------------------------------------------------ 

class InboxFile():
    def __init__(self, peer, file_id, num_blocks):
        global _RegisterTransferFunc
        self.fd, self.filename = tmpfile.make("udp-in")
        self.peer = peer
        self.file_id = file_id
        self.num_blocks = num_blocks
        self.blocks = {}
        self.bytes_received = 0
        self.bytes_extra = 0
        self.transfer_id = None
        self.started = time.time()
        self.last_block_time = time.time()
        self.block_timeout = 0
        if _RegisterTransferFunc is not None:
            self.transfer_id = _RegisterTransferFunc('receive', self.peer.remote_address, self.get_bytes_received, self.filename, -1, '')
        # dhnio.Dprint(6, 'transport_udp_session.InboxFile {%s} [%d] from %s' % (self.transfer_id, self.file_id, str(self.peer.remote_address)))

    def close(self):
        global _UnRegisterTransferFunc
        if _UnRegisterTransferFunc is not None and self.transfer_id is not None:
            _UnRegisterTransferFunc(self.transfer_id)
        try:
            if self.bytes_received > 0 and self.bytes_extra > self.bytes_received * 0.1:
                dhnio.Dprint(10, 'transport_udp_session.InboxFile.close WARNING %s%% garbage traffic from %s' % (str(self.bytes_extra/float(self.bytes_received)), self.peer.remote_address))
        except:
            dhnio.DprintException()
        # dhnio.Dprint(6, 'transport_udp_session.InboxFile.close {%s} [%d] from %s' % (self.transfer_id, self.file_id, str(self.peer.remote_address)))
        # dt = time.time() - self.started 
        # print 'DONE', self.bytes_received, self.bytes_extra, dt, (self.bytes_received/1024.0)/dt 

    def get_bytes_received(self):
        return self.bytes_received

    def input_block(self, block_id, block_data):
        if block_id not in self.blocks:
            self.blocks[block_id] = block_data
            self.bytes_received += len(block_data)
        else:
            self.bytes_extra += len(block_data)
        self.last_block_time = time.time()
        self.block_timeout = max( int(len(block_data)/settings.SendingSpeedLimit()), 3) 
    
    def build(self):
        for block_id in xrange(len(self.blocks)):
            os.write(self.fd, self.blocks[block_id])
        os.close(self.fd)
        # dhnio.Dprint(10, 'transport_udp_server.InboxFile.build [%s] file_id=%d, blocks=%d' % (
        #     os.path.basename(filename), file_id, len(self.incommingFiles[file_id])))

    def is_timed_out(self):
        if self.block_timeout == 0:
            return False
        return time.time() - self.last_block_time > self.block_timeout

    
#------------------------------------------------------------------------------ 

class TransportUDPSession(automat.Automat):
    fast = True
    timers = {'timer-60sec':     (60,    ['PING',]),
              'timer-3min':      (60*10,  ['PING',]),
              }
    def __init__(self, address, name, state, debug_level):
        self.remote_address = address
        self.remote_idurl = None
        self.remote_name = None
        self.last_alive_packet_time = 0
        self.incommingFiles = {}
        self.outgoingFiles = {}
        self.maxOutgoingFiles = 1
        self.receivedFiles = {}
        self.outbox_queue = []
        self.tries = 0
        self.ack_timeout = MIN_ACK_TIME_OUT
        self.sliding_window = {}
        self.sliding_window_size = MIN_WINDOW_SIZE
        self.last_bytes_sent = 0
        # self.failedBlocks = {}
        self.hasFailedBlocks = False
        self.block_size_level = 0
        self.remote_id_request_last_time = 0
        self.routed = False
        automat.Automat.__init__(self, name, state, debug_level)
        
    def state_changed(self, oldstate, newstate):
        global _StateChangedCallbackFunc
        if _StateChangedCallbackFunc is not None:
            _StateChangedCallbackFunc(self.index, oldstate, newstate)
        
    def A(self, event, arg):
        #---CONNECTED---
        if self.state is 'CONNECTED':
            if event == 'datagram-received' :
                self.doReceiveData(arg)
            elif event == 'timer-30sec' and self.isAlive(arg) :
                self.doAlive(arg)
            elif event == 'shutdown' :
                self.state = 'CLOSED'
                self.doDestroyMe(arg)
            elif event == 'timer-30sec' and not self.isAlive(arg) :
                self.state = 'PING'
                self.doParentRequestRemoteID(arg)
                self.doPing(arg)
        #---AT_STARTUP---
        elif self.state is 'AT_STARTUP':
            if event == 'shutdown' :
                self.state = 'CLOSED'
                self.doDestroyMe(arg)
            elif event == 'init' :
                self.state = 'PING'
                self.doSaveIDURL(arg)
                self.doParentRequestRemoteID(arg)
                self.doPing(arg)
        #---PING---
        elif self.state is 'PING':
            if event == 'datagram-received' and self.isPingOrGreeting(arg) :
                self.state = 'GREETING'
                self.doReceiveData(arg)
                self.doGreeting(arg)
            elif event == 'datagram-received' and not self.isPingOrGreeting(arg) :
                self.doReceiveData(arg)
            elif event == 'shutdown' :
                self.state = 'CLOSED'
                self.doDestroyMe(arg)
            elif event == 'timer-60sec' :
                self.doParentRequestRemoteID(arg)
            elif event == 'timer-5sec' :
                self.doPing(arg)
            elif event == 'timer-3min' :
                self.state = 'CLOSED'
                self.doDestroyMe(arg)
                self.doParentRecreateMe(arg)
        #---GREETING---
        elif self.state is 'GREETING':
            if event == 'datagram-received' and self.isGreetingOrAlive(arg) :
                self.state = 'CONNECTED'
                self.doReceiveData(arg)
                self.doAlive(arg)
            elif event == 'datagram-received' and not self.isGreetingOrAlive(arg) :
                self.doReceiveData(arg)
            elif event == 'timer-5sec' :
                self.doGreeting(arg)
            elif event == 'shutdown' :
                self.state = 'CLOSED'
                self.doDestroyMe(arg)
            elif event == 'timer-30sec' :
                self.state = 'PING'
                self.doParentRequestRemoteID(arg)
                self.doPing(arg)
        #---CLOSED---
        elif self.state is 'CLOSED':
            pass

    def isPingOrGreeting(self, arg):
        try:
            datagram, addr = arg
        except:
            return False
        return datagram[:2] in [ COMMANDS['PING'], COMMANDS['GREETING'], ] 
            
    def isGreetingOrAlive(self, arg):
        return arg[0][:2] in [ COMMANDS['GREETING'], COMMANDS['ALIVE'], ]
    
    def isAlive(self, arg):
        return time.time() - self.last_alive_packet_time < 60.0 * 1.0 + 5.0
    
    def doSaveIDURL(self, arg):
        self.remote_idurl = arg
        self.remote_name = nameurl.GetName(self.remote_idurl)
  
    def doPing(self, arg):
        self.sendDatagram(COMMANDS['PING'])
        if not self.routed:
            if dhn_stun_servers_enabled():
                if self.remote_idurl:
                    request = DHN_STUN_COMMANDS['ROUTE']+('%s %s' % (misc.getLocalID(), self.remote_idurl))
                    dhn_stun_servers_request(parent().client.transport, request)
    
    def doGreeting(self, arg):
        self.sendDatagram(COMMANDS['GREETING']+misc.getLocalID())
    
    def doAlive(self, arg):
        self.sendDatagram(COMMANDS['ALIVE'])
    
    def doReceiveData(self, arg):
        global _ReceiveControlFunc
        try:
            datagram, addr = arg
        except:
            return
        io = cStringIO.StringIO(datagram)
        code = io.read(2)
        cmd = CODES.get(code, None)
        if cmd is None:
            # dhnio.Dprint(2, 'transport_udp_session.doReceiveData WARNING incorrect data from %s: [%s]' % (self.remote_address, code))
            return
        if _ReceiveControlFunc:
            seconds_pause = _ReceiveControlFunc(len(datagram))
            if seconds_pause > 0:
                # transport_udp.A().client.transport.pauseProducing()
                parent().client.client.transport.pauseProducing()
                # self.client.transport.pauseProducing()
                # reactor.callLater(seconds_pause, transport_udp.A().client.transport.resumeProducing)
                reactor.callLater(seconds_pause, parent().client.transport.resumeProducing)
        # dhnio.Dprint(8, '                                UDP:[%s] from %s' % (cmd, self.remote_address))
        self.last_alive_packet_time = time.time()
        #--- DATA
        if cmd == 'DATA':
            try:
                file_id = struct.unpack('i', io.read(4))[0]
                block_id = struct.unpack('i', io.read(4))[0]
                num_blocks = struct.unpack('i', io.read(4))[0]
                data_size = struct.unpack('i', io.read(4))[0]
            except:
                dhnio.DprintException()
                return
            if not self.incommingFiles.has_key(file_id):
                if self.receivedFiles.has_key(file_id):
                    if time.time() - self.receivedFiles[file_id] > 10:
                        # we receive the file, but 10 seconds since that we still receive the acks
                        # definitely something wrong - drop session 
                        self.automat('shutdown')
                        return 
                    self.sendDatagram(COMMANDS['REPORT'] + struct.pack('i', file_id) + struct.pack('i', block_id))
                    return
                if len(self.incommingFiles) >= 2 * self.maxOutgoingFiles:
                    # too many incoming files - drop session
                    self.automat('shutdown') 
                    return
                self.incommingFiles[file_id] = InboxFile(self, file_id, num_blocks)
            inp_data = io.read()
            if len(inp_data) != data_size:
                dhnio.Dprint(2, 'transport_udp_session.doReceiveData WARNING incorrect datagram received from %s, not full data' % str(self.remote_address))
                return
            self.incommingFiles[file_id].input_block(block_id, inp_data) 
            self.sendDatagram(COMMANDS['REPORT'] + struct.pack('i', file_id) + struct.pack('i', block_id))
            # dhnio.Dprint(12, 'transport_udp_session.doReceiveData [%d] (%d/%d) from %s, state=%s' % (file_id, block_id, num_blocks, self.remote_address, self.state))
            if len(self.incommingFiles[file_id].blocks) == num_blocks:
                # dhnio.Dprint(12, 'transport_udp_session.doReceiveData new file [%d] (%d/%d) from %s' % (file_id, block_id, num_blocks, self.remote_address))
                self.incommingFiles[file_id].build()
                file_received(self.incommingFiles[file_id].filename, 'finished', 'udp', self.remote_address)
                self.incommingFiles[file_id].close()   
                del self.incommingFiles[file_id]   
                self.receivedFiles[file_id] = time.time()
                self.eraseOldFileIDs()
        #--- REPORT
        elif cmd == 'REPORT':
            try:
                file_id = struct.unpack('i', io.read(4))[0]
            except:
                dhnio.DprintException()
                return
            if not self.outgoingFiles.has_key(file_id):
                # if not self.receivedFiles.has_key(file_id):
                #     dhnio.Dprint(8, 'transport_udp_session.doReceiveData WARNING unknown file_id in REPORT packet received from %s: [%d]' % (self.remote_address, file_id))
                return
            try:
                block_id = struct.unpack('i', io.read(4))[0]
            except:
                dhnio.DprintException()
                return
            self.outgoingFiles[file_id].report_block(block_id)
            self.sliding_window.pop((file_id, block_id), None)
            self.sliding_window_size += 1
            if self.sliding_window_size > MAX_WINDOW_SIZE:
                self.sliding_window_size = MAX_WINDOW_SIZE
            if len(self.outgoingFiles[file_id].blocks) == 0:
                self.reportSentDone(file_id)
                self.closeOutboxFile(file_id)
            # dhnio.Dprint(8, 'transport_udp_session.doReceiveData REPORT on [%d,%d] received, blocks=%d, window=%d' % (file_id, block_id, len(self.outgoingFiles[file_id]), self.sliding_window_size))
        #--- GREETING
        elif cmd == 'GREETING':
            greeting_idurl = io.read()
            dhnio.Dprint(12, 'transport_udp_session.doReceiveData GREETING "%s" from %s, remote_idurl=%s, remote_address=%s, state=%s' % (
                greeting_idurl[:120], str(addr), self.remote_idurl, self.remote_address, self.state))
            if greeting_idurl:
                if nameurl.UrlMake(parts=nameurl.UrlParse(greeting_idurl)) != greeting_idurl:
                    dhnio.Dprint(2, 'transport_udp_session.doReceiveData WARNING incorrect idurl=%s in GREETING packet from %s' % (greeting_idurl, self.name))
                    self.sendDatagram(COMMANDS['PING'])
                else:
                    if self.remote_idurl is None:
                        self.remote_idurl = greeting_idurl
                        self.remote_name = nameurl.GetName(self.remote_idurl)
                        dhnio.Dprint(6, 'transport_udp_session.doReceiveData got idurl=%s in GREETING packet from %s' % (greeting_idurl, self.name))
                        parent().automat('recognize-remote-id', (self.index, self.remote_idurl))
                    else:
                        if self.remote_idurl != greeting_idurl:
                            dhnio.Dprint(2, 'transport_udp_session.doReceiveData WARNING wrong idurl=%s in GREETING packet from %s' % (greeting_idurl, self.name))
                    ident = contacts.getContact(greeting_idurl)
                    if ident:
                        udpip = ident.getIP('udp')
                        if udpip:
                            if udpip != addr[0]:
                                parent().automat('detect-remote-ip', (self.index, self.remote_idurl))
                    self.sendDatagram(COMMANDS['ALIVE'])
            else:
                dhnio.Dprint(2, 'transport_udp_session.doReceiveData WARNING did not found idurl in GREETING packet from %s, send PING again' % self.name)
                self.sendDatagram(COMMANDS['PING'])
        #--- PING
        elif cmd == 'PING':
            self.sendDatagram(COMMANDS['GREETING']+misc.getLocalID())
        #--- ALIVE            
        elif cmd == 'ALIVE':
            pass

    def doDestroyMe(self, arg):
        # dhnio.Dprint(6, 'transport_udp_session.doDestroyMe %s' % self.name)
        file_ids_to_remove = self.incommingFiles.keys()
        for file_id in file_ids_to_remove:
            try:
                os.close(self.incommingFiles[file_id].fd)
            except:
                dhnio.DprintException()
            file_received(self.incommingFiles[file_id].filename, 'failed', 'udp', self.remote_address, None, 'session has been closed')
            self.incommingFiles[file_id].close()   
            del self.incommingFiles[file_id]
        file_ids_to_remove = self.outgoingFiles.keys()
        for file_id in file_ids_to_remove:
            file_sent(self.remote_address, self.outgoingFiles[file_id].filename, 'failed', 'udp', None, 'session has been closed')
            self.closeOutboxFile(file_id)
        self.receivedFiles.clear()
        self.sliding_window.clear()
        automat.objects().pop(self.index)
        
    def doParentRequestRemoteID(self, arg):
        if self.remote_idurl:
            # dhnio.Dprint(8, 'transport_udp_session.doParentRequestRemoteID [%s] for session %s' % (self.remote_name, self.name))
            parent().automat('child-request-remote-id', self.remote_idurl)

    def doParentRecreateMe(self, arg):
        if self.remote_idurl:
            parent().automat('child-request-recreate', self.remote_idurl)


    def sendDatagram(self, data):
        # dhnio.Dprint(10, '    [UDP] %d bytes to %s (%s)' % (len(data), self.remote_address, nameurl.GetName(self.remote_idurl)))
        if parent().client is not None:
        # if transport_udp.A().client is not None:
            try:
                # transport_udp.A().client.transport.write(data, self.remote_address)
                parent().client.transport.write(data, self.remote_address)
                return True
            except:
                return False 
        else:
            dhnio.Dprint(2, 'transport_udp_session.sendDatagram WARNING client is None')
            return False      
        
    def makeFileID(self):
        return int(str(int(time.time() * 100.0))[4:])   

#    def register_outbox_file(self, filename, sz, callback, description=''): 
#        global _RegisterTransferFunc
#        if _RegisterTransferFunc is None:
#            return None
#        transfer_id = _RegisterTransferFunc('send', self.remote_address, callback, filename, sz, description)
#        return transfer_id
   
    def addOutboxFile(self, filename, description=''):
        self.outbox_queue.append((filename, description))
        # transfer_id, filesize = self.register_outbox_file(filename, description)
        # if transfer_id:
        #     self.outbox_queue.append((filename, filesize, transfer_id, description))
        # else:
        #     file_sent(self.remote_address, filename, 'failed', 'udp', None, 'unable to register transfer')
        # dhnio.Dprint(6, 'transport_udp_session.addOutboxFile [%s], total outbox files: %d' % (os.path.basename(filename), len(self.outbox_queue)))
        
    def putOutboxFile(self, filename, description=''):
        self.outbox_queue.insert(0, (filename, description))
        # transfer_id, filesize = self.register_outbox_file(filename, description)
        # if transfer_id:
        #     self.outbox_queue.insert(0, (filename, filesize, transfer_id, description)) 
        # else:
        #     file_sent(self.remote_address, filename, 'failed', 'udp', None, 'unable to register transfer')
        # dhnio.Dprint(6, 'transport_udp_session.putOutboxFile [%s], total outbox files: %d' % (os.path.basename(filename), len(self.outbox_queue)))
    
    def eraseOldFileIDs(self):
        if len(self.receivedFiles) > 10:
            file_ids = self.receivedFiles.keys()
            cur_tm = time.time()
            for file_id in file_ids:
                if cur_tm - self.receivedFiles[file_id] > 60 * 20:
                    del self.receivedFiles[file_id]
            del file_ids 

    def closeOutboxFile(self, file_id):
        self.outgoingFiles[file_id].close()
        del self.outgoingFiles[file_id]

    def reportSentDone(self, file_id):
        file_sent(self.remote_address, self.outgoingFiles[file_id].filename, 'finished', 'udp')
        self.block_size_level += 1
        if self.block_size_level > MAX_BLOCK_SIZE_LEVEL:
            self.block_size_level = MAX_BLOCK_SIZE_LEVEL
        # print self.block_size_level
    
    def reportSentFailed(self, file_id, why=''):
        file_sent(self.remote_address, self.outgoingFiles[file_id].filename, 'failed', 'udp', None, why)
        self.block_size_level -= 2
        if self.block_size_level < 0:
            self.block_size_level = 0
        # print self.block_size_level

    def processOutboxQueue(self):
        # global _UnRegisterTransferFunc
        has_reads = False
        while len(self.outbox_queue) > 0 and len(self.outgoingFiles) < self.maxOutgoingFiles:        
            # filename, filesize, transfer_id, description = self.outbox_queue.pop(0)
            filename, description = self.outbox_queue.pop(0)
            has_reads = True
            # we have a queue of files to be sent
            # somehow file may be removed before we start sending it
            # so we check it here and skip not existed files
            if not os.path.isfile(filename):
                file_sent(self.remote_address, filename, 'failed', 'udp', None, 'file were removed')
                # if _UnRegisterTransferFunc:
                #     _UnRegisterTransferFunc(transfer_id)
                continue
            try:
                sz = os.path.getsize(filename)
            except:
                file_sent(self.remote_address, filename, 'failed', 'udp', None, 'can not get file size')
                continue
#            if os.access(filename, os.R_OK):
#                file_sent(self.remote_address, filename, 'failed', 'udp', None, 'access denied')
#                continue
            file_id = self.makeFileID()
            f = OutboxFile(self, self.remote_idurl, file_id, filename, sz, description)
            f.read_blocks()
            self.outgoingFiles[file_id] = f
        return has_reads

    def checkIncomingFiles(self):
        for file_id in self.incommingFiles.keys():
            if self.incommingFiles[file_id].is_timed_out():
                self.automat('shutdown')
                return

    def processSending(self):
        has_sends = False
        has_timedout = False
        failed_ids = []
        for file_id in self.outgoingFiles.keys():
            if self.outgoingFiles[file_id].send():
                has_sends = True
            if self.outgoingFiles[file_id].is_timed_out():
                if self.outgoingFiles[file_id].timeout == 0:
                    failed_ids.append((file_id, 'canceled'))
                else:
                    # failed_ids.append((file_id, 'timeout'))
                    has_timedout = True
        for file_id, why in failed_ids:
            self.reportSentFailed(file_id, why)
            self.closeOutboxFile(file_id)
        del failed_ids
        if has_timedout:
            # if some packets we currently sending is timed out
            # all other in the outbox will fail too - so erase all.
            self.clearOutboxQueue()
        has_sends = has_sends or self.checkWindow()
        return has_sends
    
    def clearOutboxQueue(self):
        failed = []
        while len(self.outbox_queue) > 0:
            filename, filesize, transfer_id, description = self.outbox_queue.pop(0)
            failed.append((filename, filesize, transfer_id, description))
        for filename, filesize, transfer_id, description in failed:
            reactor.callLater(0, file_sent, self.remote_address, filename, 'failed', 'udp', None, 'timeout')
        del failed
            
    def checkWindow(self):
        if len(self.sliding_window) == 0:
            return False
        to_remove = [] 
        to_update = {}
        cur_tm = time.time()
        do_send = True
        for block_info, tm in self.sliding_window.items():
            if cur_tm - tm < self.ack_timeout: # give some time to get an Ack. 
                continue
            to_remove.append(block_info)
            file_id = block_info[0]
            block_id = block_info[1]
            if not self.outgoingFiles.has_key(file_id):
                # dhnio.Dprint(2, 'transport_udp_session.checkWindow WARNING unknown file_id [%d] from %s' % (file_id, nameurl.GetName(self.remote_idurl)))
                continue
            if not self.outgoingFiles[file_id].blocks.has_key(block_id):
                dhnio.Dprint(2, 'transport_udp_session.checkWindow WARNING unknown block_id: %d' % block_id)
                continue
            do_send = True
            to_update[block_info] = cur_tm
            outFile = self.outgoingFiles[file_id]
            outFile.blocks_timeouts += 1
            outFile.send_block(block_id)
            timeouts_ratio = outFile.check_blocks_timeouts()
            self.adjust_ack_timeout(timeouts_ratio)
#            self.outgoingFiles[file_id].send_block(block_id)
#            isFailed = self.outgoingFiles[file_id].mark_failed_block(block_id)
#            if not isFailed:
#                to_update[block_info] = cur_tm
        for block_info in to_remove:
            del self.sliding_window[block_info]
            # dhnio.Dprint(8, 'transport_udp_session.doCheckWindow (%d,%d) removed, window=%d' % (file_id, block_id, len(self.sliding_window)))
        for block_info, tm in to_update.items():
            self.sliding_window[block_info] = tm
            # dhnio.Dprint(8, 'transport_udp_session.doCheckWindow (%s) resending to %s, window=%d' % (block_info, self.remote_address, len(self.sliding_window)))
        if len(to_remove) > 0:
            self.sliding_window_size = int( self.sliding_window_size / 2.0 )
            if self.sliding_window_size < MIN_WINDOW_SIZE:
                self.sliding_window_size = MIN_WINDOW_SIZE
            # dhnio.Dprint(8, 'transport_udp_session.doCheckWindow decreased, window=%d' % self.sliding_window_size)
        del to_remove
        del to_update
        return 

    def adjust_ack_timeout(self, timeouts_ratio):
        if timeouts_ratio >= MAX_TIMEOUTS_RATIO:
            self.ack_timeout *= 2.0
            if self.ack_timeout > MAX_ACK_TIME_OUT:
                self.ack_timeout = MAX_ACK_TIME_OUT
                # TODO transfer is failed - udp packets did not get acket
                # drop connection!
                # TODO change transport_udp_server to drop connection
                self.automat('shutdown')
            # else:
            #     print('adjust_ack_timeout %f' % self.ack_timeout)
        elif timeouts_ratio <= FINE_TIMEOUTS_RATIO:
            self.ack_timeout /= 2.0
            if self.ack_timeout < MIN_ACK_TIME_OUT:
                self.ack_timeout = MIN_ACK_TIME_OUT
                # TODO transfer is great!
                #      increase window size, block size? 
            # else:
            #     print('adjust_ack_timeout %f' % self.ack_timeout)

    def cancel(self, transferID):
        for i in xrange(len(self.outbox_queue)):
            filename, filesize, transfer_id, description = self.outbox_queue[i]
            if transferID == transfer_id:
                del self.outbox_queue[i]
                break
        for file_id in self.outgoingFiles.keys():
            if self.outgoingFiles[file_id].transfer_id == transferID:
                self.outgoingFiles[file_id].cancel()
                # self.receivedFiles[file_id] = time.time()
                break
        for file_id in self.incommingFiles.keys():
            if self.incommingFiles[file_id].transfer_id == transferID:
                self.incommingFiles[file_id].build()
                file_received(self.incommingFiles[file_id].filename, 'failed', 'udp', self.remote_address)              
                self.incommingFiles[file_id].close()
                del self.incommingFiles[file_id]
                self.receivedFiles[file_id] = time.time()
                break

#------------------------------------------------------------------------------ 
    
def check_outbox_queue():    
    has_reads = False
    for sess in sessions():
        if sess.processOutboxQueue():
            has_reads = True
    if has_reads:
        check_sending_queue()
    return has_reads 
    
def check_sending_queue():    
    has_sends = False
    for sess in sessions():
        if sess.processSending():
            has_sends = True
    return has_sends

def check_incoming_files():
    for sess in sessions():
        sess.checkIncomingFiles()
    
def process_outbox_queue():
    global _OutboxQueueDelay
    global _OutboxQueueTask
    
    has_reads = check_outbox_queue()

    _OutboxQueueDelay = misc.LoopAttenuation(
        _OutboxQueueDelay, 
        has_reads, 
        settings.MinimumSendingDelay(), 
        settings.MaximumSendingDelay(),)
    
    # attenuation
    _OutboxQueueTask = reactor.callLater(_OutboxQueueDelay, process_outbox_queue)
        

def process_sessions():
    global _SendingDelay
    global _SendingTask
    
    check_incoming_files()
    
    has_sends = check_sending_queue()
    
    _SendingDelay = misc.LoopAttenuation(
        _SendingDelay, 
        has_sends, 
        settings.MinimumSendingDelay(), 
        settings.MaximumSendingDelay(),)
    
    # attenuation
    _SendingTask = reactor.callLater(_SendingDelay, process_sessions)
    
#------------------------------------------------------------------------------ 

def sessions():
    for a in automat.objects().values():
        if a.name.startswith('udp_'):
            yield a


def open_session(address):
    name = 'udp_%s_%s' % (address[0].replace('.','_'), str(address[1]))
    for a in automat.objects().values():
        if a.name == name:
            return a
    a = TransportUDPSession(address, name, 'AT_STARTUP', 12)
    return a


def get_session(address):
    name = 'udp_%s_%s' % (address[0].replace('.','_'), str(address[1]))
    for a in automat.objects().values():
        if a.name == name:
            return a
    return None


def get_session_by_index(index):
    return automat.objects().get(index, None)


def is_session_opened(address):
    name = 'udp_%s_%s' % (address[0].replace('.','_'), str(address[1]))
    for a in automat.objects().values():
        if a.name == name:
            return True
    return False
        

def outbox_file(address, filename, fast=False, description=''):
#    dhnio.Dprint(6, 'transport_udp_session.outbox_file %s to %s (%s)' % (
#        os.path.basename(filename), nameurl.GetName(idurl), str(address)))
    s = open_session(address)
    if s.state != 'CONNECTED':
        file_sent(s.remote_address, filename, 'failed', 'udp', None, 'remote peer is not connected')
        return
    if fast:
        s.putOutboxFile(filename, description)
    else:
        s.addOutboxFile(filename, description)
    check_outbox_queue()


def cancel(transferID):
    for sess in sessions():
        sess.cancel(transferID)
    

def big_event(event, arg=None):
    for sess in sessions():
        sess.event(event, arg)


def data_received(datagram, address):
    try:
        from transport_control import black_IPs_dict
        if address[0] in black_IPs_dict().keys() or '.'.join(address[0].split('.')[:-1]) in black_IPs_dict().keys():
            # dhnio.Dprint(12, 'transport_udp_session.data_received %d bytes from BLACK IP: %s, %s' % (len(datagram), str(address[0]), str(black_IPs_dict()[address[0]])) )
            return
    except:
        pass
    if dhn_stun_servers_enabled():
        if address in DHN_STUN_SERVERS:
            dhn_stun_server_response(datagram, address)
            return
    if not is_session_opened(address):
        s = open_session(address)
        idurl = identitycache.GetIDURLByIPPort(address[0], address[1])
        if idurl:
            dhnio.Dprint(6, 'transport_udp_session.data_received from KNOWN user, made a new session %s for [%s]' % (s.name, nameurl.GetName(idurl)))
            s.event('init', idurl)
        else:
            dhnio.Dprint(6, 'transport_udp_session.data_received from UNKNOWN user, made a new session %s' % s.name)
            s.event('init', None)
    A(address, 'datagram-received', (datagram, address))


def shutdown_all_sessions():
    big_event('shutdown')
    
    
def file_received(filename, status, proto='', host=None, error=None, message=''):
    global _ReceiveStatusCallback
    if _ReceiveStatusCallback is not None:
        _ReceiveStatusCallback(filename, status, proto, host, error, message)
    
    
def file_sent(host, filename, status, proto='', error=None, message=''):
    global _SendStatusCallback
    if _SendStatusCallback is not None:
        _SendStatusCallback(host, filename, status, proto, error, message)


#def timer30sec():
#    global _Timer30sec
#    big_event('timer-30sec')
#    _Timer30sec = reactor.callLater(ndom.randint(25,35), timer30sec)


def timerAlive():
    global _TimerAlive
    big_event('timer-30sec')
    _TimerAlive = reactor.callLater(30, timerAlive)


def timerPing():
    global _TimerPing
    big_event('timer-5sec')
    _TimerPing = reactor.callLater(5, timerPing)
    
#------------------------------------------------------------------------------ 
    
def SetReceiveStatusCallback(cb):
    global _ReceiveStatusCallback
    _ReceiveStatusCallback = cb
    
def SetSendStatusCallback(cb):
    global _SendStatusCallback
    _SendStatusCallback = cb
    
def SetSendControlFunc(f):
    global _SendControlFunc
    _SendControlFunc = f
    
def SetReceiveControlFunc(f):
    global _ReceiveControlFunc
    _ReceiveControlFunc = f

def SetRegisterTransferFunc(f):
    global _RegisterTransferFunc
    _RegisterTransferFunc = f

def SetUnRegisterTransferFunc(f):
    global _UnRegisterTransferFunc
    _UnRegisterTransferFunc = f

def SetStateChangedCallbackFunc(f):
    global _StateChangedCallbackFunc
    _StateChangedCallbackFunc = f
    
def SetNetworkAddressChangedFunc(f):
    global _NetworkAddressChangedFunc
    _NetworkAddressChangedFunc = f
    
#------------------------------------------------------------------------------ 

    
def StartTimers():
    global _Timer30sec
    global _TimerAlive
    global _TimerPing
#    if _Timer30sec is None:
#        timer30sec()
    if _TimerAlive is None: 
        timerAlive()
    if _TimerPing is None:
        timerPing()


def StopTimers():
    global _Timer30sec
    global _TimerAlive
    global _TimerPing
#    if _Timer30sec:
#        _Timer30sec.cancel()
#        _Timer30sec = None
    if _TimerAlive:
        _TimerAlive.cancel()
        _TimerAlive = None
    if _TimerPing:
        _TimerPing.cancel()
        _TimerPing = None





