#!/usr/bin/python
#transport_udp.py
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
import random

from twisted.internet import reactor
from twisted.internet.task import LoopingCall 
from twisted.internet.defer import Deferred, DeferredList, succeed


import dhnio
import misc
import settings
import nameurl
import contacts
import identitycache

import stun
import shtoom.stun 
import shtoom.nat
                                                                 
import automat
import transport_udp_session 
import transport_udp_server     

_TransportUDP = None
_IsServer = False
# _PeerStateChangedCallback = None

#------------------------------------------------------------------------------ 

def init(client,):
    dhnio.Dprint(4, 'transport_udp.init ' + str(client))
    A('init', client)
    

def shutdown():
    A('stop')
    
# fast=True: put filename in the top of sending queue,
# fast=False: append to the bottom of the queue    
def send(filename, host, port, fast=False, description=''):
    # dhnio.Dprint(6, "transport_udp.send %s to %s:%s" % (os.path.basename(filename), host, port))
    A('send-file', ((host, int(port)), (filename, fast, description)))

def cancel(transferID):
    A('cancel-file', transferID)

def getListener():
    return A()

#------------------------------------------------------------------------------ 

class TransferInfo():
    def __init__(self, remote_address, filename, size):
        self.remote_address = remote_address
        self.filename = filename
        self.size = size

def current_transfers():
    return A().currentTransfers()

#------------------------------------------------------------------------------ 

def Start():
    A('start')
    
    
def Stop():
    A('stop')


def ListContactsCallback(oldlist, newlist):
    A('list-contacts', (oldlist, newlist))
    
#------------------------------------------------------------------------------ 

def SendStatusCallbackDefault(host, filename, status, proto='', error=None, message=''):
    try:
        from transport_control import sendStatusReport
        return sendStatusReport(host, filename, status, proto, error, message)
    except:
        dhnio.DprintException()
        return None

def ReceiveStatusCallbackDefault(filename, status, proto='', host=None, error=None, message=''):
    try:
        from transport_control import receiveStatusReport
        return receiveStatusReport(filename, status, proto, host, error, message)
    except:
        dhnio.DprintException()
        return None

def SendControlFuncDefault(prev_read_size, chunk_size):
    try:
        from transport_control import SendTrafficControl
        return SendTrafficControl(prev_read_size, chunk_size)
    except:
        dhnio.DprintException()
        return chunk_size
        
def ReceiveControlFuncDefault(new_data_size):
    try:
        from transport_control import ReceiveTrafficControl
        return ReceiveTrafficControl(new_data_size)
    except:
        dhnio.DprintException()
        return 0
    
def RegisterTransferFuncDefault(send_or_receive=None, remote_address=None, callback=None, filename=None, size=None, description=None, transfer_id=None):
    try:
        from transport_control import register_transfer
        return register_transfer('udp', send_or_receive, remote_address, callback, filename, size, description, transfer_id)
    except:
        dhnio.DprintException()
    return None
    
def UnRegisterTransferFuncDefault(transfer_id):
    try:
        from transport_control import unregister_transfer
        return unregister_transfer(transfer_id)
    except:
        dhnio.DprintException()
    return None

#def SetPeerStateChangedCallback(cb):
#    global _PeerStateChangedCallback
#    _PeerStateChangedCallback = cb

#------------------------------------------------------------------------------ 

def A(event=None, arg=None):
    global _TransportUDP
    if _TransportUDP is None:
        _TransportUDP = TransportUDP()
    if event is not None:
        _TransportUDP.automat(event, arg)
    return _TransportUDP

#------------------------------------------------------------------------------ 

class TransportUDP(automat.Automat):
    def __init__(self):
        self.client = None
        self.transfers = {}
        self.debug = False
        self.redirections = {}
        self.by_transfer_ID = {}
        automat.Automat.__init__(self, 'transport_udp', 'STOPPED', 6)
        
    def A(self, event, arg):
        #---STARTED---
        if self.state is 'STARTED':
            if event == 'send-file' :
                self.doClientOutboxFile(arg)
            elif event == 'stop' :
                self.state = 'STOPPED'
                self.doShutDownAllUDPSessions(arg)
                self.doShutdownClient(arg)
            elif event == 'list-contacts' and self.isNewUDPContact(arg) :
                self.doRemoveOldUDPSession(arg)
                self.doCreateNewUDPSession(arg)
            elif event == 'child-request-remote-id' :
                self.doRequestRemoteID(arg)
            elif event == 'remote-id-received' and self.isIPPortChanged(arg) :
                self.doRestartUDPSession(arg)
            elif event == 'child-request-recreate' :
                self.doRecreateUDPSession(arg)
            elif event == 'recognize-remote-id' or event == 'detect-remote-ip':
                self.doCloseDuplicatedUDPSession(arg)
            elif event == 'cancel-file' :
                self.doClientCancelFile(arg)
            elif event == 'reconnect' :
                self.doShutDownAllUDPSessions(arg)
                self.doStartAllUDPSessions(arg)
        #---STOPPED---
        elif self.state is 'STOPPED':
            if event == 'init' and self.isOpenedIP(arg) :
                self.state = 'SERVER'
                self.doInitServer(arg)
            elif event == 'init' and not self.isOpenedIP(arg) :
                self.state = 'CLIENT'
                self.doInitClient(arg)
        #---SERVER---
        elif self.state is 'SERVER':
            if event == 'send-file' :
                self.doServerOutboxFile(arg)
            elif event == 'stop' :
                self.state = 'STOPPED'
            elif event == 'cancel-file' :
                self.doServerCancelFile(arg)
        #---CLIENT---
        elif self.state is 'CLIENT':
            if event == 'start' :
                self.state = 'STARTED'
                self.doStartAllUDPSessions(arg)
            elif event == 'stop' :
                self.state = 'STOPPED'
                self.doShutdownClient(arg)

    def isOpenedIP(self, arg):
        if not arg:
            return False
        if not arg.externalAddress:
            return False
        if not arg.localAddress:
            return False            
        return arg.externalAddress[0] == arg.localAddress

    def isNewUDPContact(self, arg):
        return arg[0] != arg[1]
    
    def isIPPortChanged(self, arg):
        idurl = arg
        ident = contacts.getContact(idurl)
        if ident is None:
            return False
        address = ident.getProtoContact('udp')
        if address is None:
            return False
        try:
            ip, port = address[6:].split(':')
            address = (ip, int(port))
        except:
            dhnio.DprintException()
            return False
        address_local = self.remapAddress(address)
        found = False
        for sess in transport_udp_session.sessions():
            if  sess.remote_idurl is not None and \
                sess.remote_idurl == idurl and \
                ( sess.remote_address[0] == address[0] or sess.remote_address[0] == address_local[0] ) and \
                ( sess.remote_address[1] != address[1] and sess.remote_address[1] != address_local[1] ):
                found = True
                dhnio.Dprint(6, 'transport_udp.isIPPortChanged found related session %s with [%s]' % (sess.name, sess.remote_name))
        return found        
    
    def doInitServer(self, arg):
        self.client = arg
        transport_udp_server.init(self.client)
        self.client.datagram_received_callback = transport_udp_server.protocol().datagramReceived
        transport_udp_server.SetReceiveStatusCallback(ReceiveStatusCallbackDefault)
        transport_udp_server.SetSendStatusCallback(SendStatusCallbackDefault)
        # transport_udp_server.SetReceiveControlFunc(ReceiveControlFuncDefault)
        # transport_udp_server.SetSendControlFunc(SendControlFuncDefault)
        transport_udp_server.SetRegisterTransferFunc(RegisterTransferFuncDefault)
        transport_udp_server.SetUnRegisterTransferFunc(UnRegisterTransferFuncDefault)
        
    def doInitClient(self, arg):
        self.client = arg
        self.client.datagram_received_callback = transport_udp_session.data_received
        transport_udp_session.init(self)
        transport_udp_session.SetReceiveStatusCallback(ReceiveStatusCallbackDefault)
        transport_udp_session.SetSendStatusCallback(SendStatusCallbackDefault)
        # transport_udp_session.SetReceiveControlFunc(ReceiveControlFuncDefault)
        # transport_udp_session.SetSendControlFunc(SendControlFuncDefault)
        transport_udp_session.SetRegisterTransferFunc(RegisterTransferFuncDefault)
        transport_udp_session.SetUnRegisterTransferFunc(UnRegisterTransferFuncDefault)
        
    def doShutdownClient(self, arg):
        transport_udp_session.shutdown()
    
    def doStartAllUDPSessions(self, arg):
        all = contacts.getContactsAndCorrespondents()
        if not self.debug:
            all.append(settings.CentralID())
        for idurl in all:
            ident = contacts.getContact(idurl)
            if ident is None:
                continue
            address = ident.getProtoContact('udp')
            if address is None:
                continue
            try:
                proto, ip, port, filename = nameurl.UrlParse(address)
                address = (ip, int(port))
            except:
                dhnio.DprintException()
                continue
            address = self.remapAddress(address)
            sess = transport_udp_session.open_session(address)
            dhnio.Dprint(8, 'transport_udp.doStartAllUDPSessions init %s with [%s]' % (sess.name, nameurl.GetName(idurl)))
            sess.automat('init', idurl)
        
    def doShutDownAllUDPSessions(self, arg):
        transport_udp_session.shutdown_all_sessions()
    
    def doRemoveOldUDPSession(self, arg):
        for idurl in arg[0]:
            if idurl == misc.getLocalID():
                continue
            if idurl not in arg[1]:
                ident = contacts.getContact(idurl)
                if ident is None:
                    continue
                address = ident.getProtoContact('udp')
                if address is None:
                    continue
                try:
                    ip, port = address[6:].split(':')
                    address = (ip, int(port))
                except:
                    dhnio.DprintException()
                    continue
                if transport_udp_session.is_session_opened(address):
                    dhnio.Dprint(8, 'transport_udp.doRemoveOldUDPSession shutdown %s with [%s]' % (str(address), nameurl.GetName(idurl)))
                    reactor.callLater(0, transport_udp_session.A, address, 'shutdown')
                address_local = self.remapAddress(address)
                if address_local != address:
                    if transport_udp_session.is_session_opened(address_local):
                        dhnio.Dprint(8, 'transport_udp.doRemoveOldUDPSession shutdown %s with local peer [%s]' % (str(address_local), nameurl.GetName(idurl)))
                        self.eraseRedirection(address_local)
                        reactor.callLater(0, transport_udp_session.A, address_local, 'shutdown')
                self.eraseRedirection(address)
                self.eraseRedirection(address_local)
                
    def doCreateNewUDPSession(self, arg):
        for idurl in arg[1]:
            if idurl == misc.getLocalID():
                continue
            if idurl not in arg[0]:
                ident = contacts.getContact(idurl)
                if ident is None:
                    continue
                address = ident.getProtoContact('udp')
                if address is None:
                    continue
                try:
                    proto, ip, port, filename = nameurl.UrlParse(address)
                    address = (ip, int(port))
                except:
                    dhnio.DprintException()
                    continue
                address = self.remapAddress(address)
                sess = transport_udp_session.open_session(address)
                dhnio.Dprint(8, 'transport_udp.doCreateNewUDPSession %s with [%s]' % (sess.name, nameurl.GetName(idurl)))
                sess.automat('init', idurl)
    
    def doRestartUDPSession(self, arg):
        idurl = arg
        ident = contacts.getContact(idurl)
        if ident is None:
            return
        address = ident.getProtoContact('udp')
        if address is None:
            return
        try:
            ip, port = address[6:].split(':')
            address = (ip, int(port))
        except:
            dhnio.DprintException()
            return
        address_local = self.remapAddress(address)
        for sess in transport_udp_session.sessions():
            if  sess.remote_idurl is not None and sess.remote_idurl == idurl and \
                ( sess.remote_address[0] == address[0] or sess.remote_address[0] == address_local[0] ) and \
                ( sess.remote_address[1] != address[1] or sess.remote_address[1] != address_local[1] ):
                self.addRedirection(sess.remote_address, address_local)
                sess.automat('shutdown')
                dhnio.Dprint(8, 'transport_udp.doRestartUDPSession "shutdown" to %s with [%s]' % (sess.name, nameurl.GetName(idurl)))
        def start_session(address_local, idurl):
            sess = transport_udp_session.open_session(address_local)
            dhnio.Dprint(8, 'transport_udp.doRestartUDPSession.start_session send "init" to %s with [%s]' % (sess.name, nameurl.GetName(idurl)))
            sess.automat('init', idurl)
        reactor.callLater(1, start_session, address_local, idurl)
         
    def doRecreateUDPSession(self, arg):
        def recreate(idurl, count):
            if count > 5:
                return
            ident = contacts.getContact(idurl)
            if ident is None:
                return
            address = ident.getProtoContact('udp')
            if address is None:
                return
            try:
                ip, port = address[6:].split(':')
                address = (ip, int(port))
            except:
                dhnio.DprintException()
                return
            if transport_udp_session.is_session_opened(address):
                reactor.callLater(1, recreate, idurl, count+1)
                dhnio.Dprint(8, 'transport_udp.doRecreateUDPSession.recreate wait 1 second to finish old session with %s' % str(address))
                return
            address_local = self.remapAddress(address)
            sess = transport_udp_session.open_session(address_local)
            dhnio.Dprint(8, 'transport_udp.doRecreateUDPSession init %s with [%s]' % (sess.name, nameurl.GetName(idurl)))
            sess.automat('init', idurl)
        reactor.callLater(random.randint(1, 10), recreate, arg, 0)
                        
    def doCloseDuplicatedUDPSession(self, arg):
        index, idurl = arg
        current_session = transport_udp_session.get_session_by_index(index)
        if current_session is None:
            dhnio.Dprint(6, 'transport_udp.doCloseDuplicatedUDPSession WARNING current session is None index=%d' % index)
            return
        for sess in transport_udp_session.sessions():
            if sess.index == index:
                continue
            if sess.remote_idurl is not None and sess.remote_idurl == idurl:
                self.addRedirection(sess.remote_address, current_session.remote_address)
                sess.automat('shutdown')
                dhnio.Dprint(8, 'transport_udp.doCloseDuplicatedUDPSession for [%s], redirect to %s, send "shutdown" to %s' % (
                    nameurl.GetName(idurl), current_session.name, sess.name))

    def doServerOutboxFile(self, arg):
        address = arg[0]
        filename, fast, description = arg[1]
        transport_udp_server.send(address, filename, fast, description)    
        
    def doClientOutboxFile(self, arg):
        address = arg[0]
        filename, fast, description = arg[1]
        address = self.remapAddress(address)
        if transport_udp_session.is_session_opened(address):
            transport_udp_session.outbox_file(address, filename, fast, description)
        else:
            if self.redirections.has_key(address) and transport_udp_session.is_session_opened(self.redirections[address]):
                transport_udp_session.outbox_file(self.redirections[address], filename, fast, description)
            else:
                dhnio.Dprint(6, 'transport_udp.doClientOutboxFile WARNING not found session for: ' + str(address))
                transport_udp_session.file_sent(address, filename, 'failed', 'udp', None, 'session not found')

    def doRequestRemoteID(self, arg):
        if isinstance(arg, str): 
            idurl = arg
            identitycache.immediatelyCaching(idurl).addCallbacks(
                lambda src: self.automat('remote-id-received', idurl),
                lambda x: self.automat('remote-id-failed', x))
        else:
            for idurl in arg[1]:
                if idurl == misc.getLocalID():
                    continue
                if idurl not in arg[0]:
                    identitycache.immediatelyCaching(idurl).addCallbacks(
                        lambda src: self.automat('remote-id-received', idurl),
                        lambda x: self.automat('remote-id-failed', x))
                  
    def doClientCancelFile(self, arg):
        transport_udp_session.cancel(arg)

    def doServerCancelFile(self, arg):
        transport_udp_server.cancel(arg)

    def stopListening(self):
        dhnio.Dprint(4, 'transport_udp.stopListening')
        self.automat('stop')
        res = stun.stopUDPListener()
        if res is None:
            res = succeed(1)
        return res

    # use local IP instead of external if it comes from central server 
    def remapAddress(self, address):
        return identitycache.RemapContactAddress(address)
    
    def addRedirection(self, old_address, new_address):
        self.redirections[old_address] = new_address
    
    def eraseRedirection(self, address_to_close):
        to_remove = []
        for old_address, new_address in self.redirections.items():
            if new_address == address_to_close:
                to_remove.append(old_address)
        for address_to_close in to_remove:
            del self.redirections[address_to_close]
        del to_remove
                    
    
#------------------------------------------------------------------------------ 

def main():
    sys.path.append('..')

    def _go_stun(port):
        print '+++++ LISTEN UDP ON PORT', port, 'AND RUN STUN DISCOVERY'
        stun.stunExternalIP(close_listener=False, internal_port=port, verbose=False).addBoth(_stuned)

    def _stuned(ip):
        if stun.getUDPClient() is None:
            print 'UDP CLIENT IS NONE - EXIT'
            reactor.stop()
            return

        print '+++++ EXTERNAL UDP ADDRESS IS', stun.getUDPClient().externalAddress
        
        if sys.argv[1] == 'listen':
            print '+++++ START LISTENING'
            return
        
        if sys.argv[1] == 'connect':
            print '+++++ CONNECTING TO REMOTE MACHINE'
            _try2connect()
            return

        lid = misc.getLocalIdentity()
        udp_contact = 'udp://'+stun.getUDPClient().externalAddress[0]+':'+str(stun.getUDPClient().externalAddress[1])
        lid.setProtoContact('udp', udp_contact)
        lid.sign()
        misc.setLocalIdentity(lid)
        misc.saveLocalIdentity()
        
        print '+++++ UPDATE IDENTITY', str(lid.contacts)
        _send_servers().addBoth(_id_sent)

    def _start_sending_ip():
        init(stun.getUDPClient())
        A().debug = True
        reactor.callLater(1, Start)
        def _start_session():
            # transport_udp_session.SetStateChangedCallbackFunc(_state_changed)
            address = (sys.argv[2], int(sys.argv[3]))
            sess = transport_udp_session.open_session(address)
            filename = sys.argv[4]
            loop_delay = None if len(sys.argv)<6 else int(sys.argv[5])
            transport_udp_session._StateChangedCallbackFunc = lambda index, old, new: _state_changed(index, address[0], new, filename, loop_delay)
            sess.automat('init', None)
        reactor.callLater(2, _start_session)        

    def _state_changed(index, ip, newstate, filename, loop_delay):
        print '+++++ STATE CHANGED     [%s]' % newstate
        sess = automat.objects().get(index)
        if newstate == 'CONNECTED':
            transport_udp_session.SetStateChangedCallbackFunc(None)
            if loop_delay:
                reactor.callLater(2, LoopingCall(send, filename, sess.remote_address[0], sess.remote_address[1]).start, loop_delay, True)
            else:
                reactor.callLater(2, send, filename, sess.remote_address[0], sess.remote_address[1])

    def _send_servers():
        import tmpfile, misc, nameurl, settings, transport_tcp
        sendfile, sendfilename = tmpfile.make("propagate")
        os.close(sendfile)
        LocalIdentity = misc.getLocalIdentity()
        dhnio.WriteFile(sendfilename, LocalIdentity.serialize())
        dlist = []
        for idurl in LocalIdentity.sources:
            # sources for out identity are servers we need to send to
            protocol, host, port, filename = nameurl.UrlParse(idurl)
            port = settings.IdentityServerPort()
            d = Deferred()
            transport_tcp.sendsingle(sendfilename, host, port, do_status_report=False, result_defer=d, description='Identity')
            dlist.append(d) 
        dl = DeferredList(dlist, consumeErrors=True)
        print '+++++ IDENTITY SENT TO %s:%s' % (host, port)
        return dl

    def _try2connect():
        remote_addr = dhnio.ReadTextFile(sys.argv[3]).split(' ')
        remote_addr = (remote_addr[0], int(remote_addr[1]))
        t = int(str(int(time.time()))[-1]) + 1
        data = '0' * t
        stun.getUDPClient().transport.write(data, remote_addr)
        print 'sent %d bytes to %s' % (len(data), str(remote_addr))
        reactor.callLater(1, _try2connect)

    def _id_sent(x):
        print '+++++ ID UPDATED ON THE SERVER', x
        if sys.argv[1] == 'send':
            _start_sending()
        elif sys.argv[1] == 'sendip':
            _start_sending_ip()
        elif sys.argv[1] == 'receive':
            _start_receiving()

    def _start_receiving():
        idurl = sys.argv[2]
        if not idurl.startswith('http://'):
            idurl = 'http://'+settings.IdentityServerName()+'/'+idurl+'.xml'
        print '+++++ START RECEIVING FROM', idurl
        _request_remote_id(idurl).addBoth(_receive_from_remote_peer, idurl)
        
    def _receive_from_remote_peer(x, idurl):
        init(stun.getUDPClient())
        A().debug = True
        contacts.addCorrespondent(idurl)
        reactor.callLater(1, Start)

    def _start_sending():
        idurl = sys.argv[2]
        if not idurl.startswith('http://'):
            idurl = 'http://'+settings.IdentityServerName()+'/'+idurl+'.xml'
        print '+++++ START SENDING TO', idurl
#        if len(sys.argv) == 6:
#            send(sys.argv[5], sys.argv[3], int(sys.argv[4]))
#        elif len(sys.argv) == 4:
        _request_remote_id(idurl).addBoth(_send_to_remote_peer, idurl, sys.argv[3], None if len(sys.argv)<5 else int(sys.argv[4]))

    def _request_remote_id(idurl):
        print '+++++ REQUEST ID FROM SERVER', idurl
        return identitycache.immediatelyCaching(idurl)
    
    def _send_to_remote_peer(x, idurl, filename, loop_delay):
        print '+++++ PREPARE SENDING TO', idurl
        init(stun.getUDPClient())
        A().debug = True
        contacts.addCorrespondent(idurl)
        reactor.callLater(1, Start)
        ident = identitycache.FromCache(idurl)
        if ident is None:
            print '+++++ REMOTE IDENTITY IS NONE'
            reactor.stop()
            return
        x, udphost, udpport, x = ident.getProtoParts('udp')
        transport_udp_session.SetStateChangedCallbackFunc(lambda index, old, new: _state_changed(index, udphost, new, filename, loop_delay))
    
    def _send_file(idurl, filename):
        ident = identitycache.FromCache(idurl)
        if ident is None:
            print '+++++ REMOTE IDENTITY IS NONE'
            reactor.stop()
        x, udphost, udpport, x = ident.getProtoParts('udp')
        print '+++++ SENDING TO', udphost, udpport
        send(filename, udphost, udpport)

    def _test_cancel():
        import transport_control as tc
        for t in tc.current_transfers():
            cancel(t.transfer_id)
        reactor.callLater(11, _test_cancel)

    # reactor.callLater(10, _test_cancel)
    
    dhnio.SetDebug(14)
    dhnio.LifeBegins()
    settings.init()
    misc.loadLocalIdentity()
    # contacts.init()
    # contacts.addCorrespondent(idurl)
    identitycache.init()
    identitycache.SetLocalIPs({'http://identity.datahaven.net/veselin.xml': '192.168.1.3',
                               'http://identity.datahaven.net/veselin-ubuntu-1024.xml': '192.168.1.100'})
    port = int(settings.getUDPPort())
    if sys.argv[1] in ['listen', 'connect']:
        port = int(sys.argv[2])
    _go_stun(port)

#------------------------------------------------------------------------------ 

if __name__ == '__main__':
    if len(sys.argv) not in [2, 3, 4, 5, 6] or sys.argv[1] not in ['send', 'sendip','receive', 'listen', 'connect']:
        print 'transport_udp.py receive <from username>'
        print 'transport_udp.py receive <from idurl>'
        print 'transport_udp.py send <to username> <filename> [loop delay]'
        print 'transport_udp.py send <to idurl> <filename> [loop delay]'
        print 'transport_udp.py sendip <ip address> <port> <filename> [loop delay]'
        print 'transport_udp.py listen <listening port>'
        print 'transport_udp.py connect <listening port> <filename with remote address>'
        sys.exit(0)
        
    main()
    reactor.run()



