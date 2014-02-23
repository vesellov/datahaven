#!/usr/bin/env python
#p2p_connector.py
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
    sys.exit('Error initializing twisted.internet.reactor in p2p_connector.py')
from twisted.internet.defer import Deferred, DeferredList, maybeDeferred, succeed
from twisted.internet.task import LoopingCall


import lib.dhnio as dhnio
import lib.misc as misc
import lib.nameurl as nameurl
import lib.settings as settings
import lib.stun as stun
import lib.dhnnet as dhnnet
import lib.transport_control as transport_control
import lib.transport_tcp as transport_tcp
if transport_control._TransportCSpaceEnable:
    import lib.transport_cspace as transport_cspace
if transport_control._TransportUDPEnable:
    import lib.transport_udp as transport_udp


import lib.automat as automat
import lib.automats as automats

import initializer
import shutdowner
import network_connector
import central_connector
import backup_monitor
import backup_db_keeper
import list_files_orator
import fire_hire
import data_sender
import contact_status


import identitypropagate
import run_upnpc
import ratings
import dhnicon

#------------------------------------------------------------------------------ 

_P2PConnector = None
_RevisionNumber = None
_WorkingProtocols = set()

#------------------------------------------------------------------------------

def A(event=None, arg=None):
    global _P2PConnector
    if _P2PConnector is None:
        _P2PConnector = P2PConnector('p2p_connector', 'AT_STARTUP', 6)
    if event is not None:
        _P2PConnector.automat(event, arg)
    return _P2PConnector

class P2PConnector(automat.Automat):
    timers = {'timer-1min':  (30, ['INCOMMING?', 'DISCONNECTED']),
              'timer-20sec': (20, ['INCOMMING?']),}

    def init(self):
        self.ackCounter = 0

    def state_changed(self, oldstate, newstate):
        automats.set_global_state('P2P ' + newstate)
        initializer.A('p2p_connector.state', newstate)
        central_connector.A('p2p_connector.state', newstate)
        dhnicon.state_changed(network_connector.A().state, self.state, central_connector.A().state)

    def A(self, event, arg):
        #---AT_STARTUP---
        if self.state is 'AT_STARTUP':
            if event == 'init' :
                self.state = 'NETWORK?'
                self.doInit(arg)
                backup_monitor.A('init')
                backup_db_keeper.A('init')
                list_files_orator.A('init')
                fire_hire.A('init')
                data_sender.A('init')
        #---NETWORK?---
        elif self.state is 'NETWORK?':
            if ( event == 'network_connector.state' and arg is 'DISCONNECTED' ) :
                self.state = 'DISCONNECTED'
            elif ( event == 'network_connector.state' and arg is 'CONNECTED' ) :
                self.state = 'TRANSPORTS'
                self.doUpdateIdentity(arg)
                self.doUpdateTransports(arg)
        #---TRANSPORTS---
        elif self.state is 'TRANSPORTS':
            if event == 'transports-updated' :
                self.state = 'ID_SERVER'
                self.doUpdateIdentity(arg)
                self.doSendIdentityToIDServer(arg)
        #---ID_SERVER---
        elif self.state is 'ID_SERVER':
            if ( event == 'network_connector.state' and arg is 'CONNECTED' ) or ( event == 'settings' and self.isIdentityChanged(arg) ) :
                self.state = 'TRANSPORTS'
                self.doUpdateIdentity(arg)
                self.doUpdateTransports(arg)
            elif event == 'id-server-success' or event == 'id-server-failed' :
                self.state = 'CENTRAL_SERVER'
                central_connector.A('propagate')
                transport_udp.A('start')
        #---CENTRAL_SERVER---
        elif self.state is 'CENTRAL_SERVER':
            if ( event == 'central_connector.state' and arg in [ 'CONNECTED' , 'DISCONNECTED' ] ) :
                self.state = 'CONTACTS'
                self.doSendIdentityToAllContacts(arg)
            elif ( ( event == 'network_connector.state' and arg is 'CONNECTED' ) ) or ( ( event == 'central_connector.state' and arg is 'ONLY_ID' ) ) or ( event == 'settings' and self.isIdentityChanged(arg) ) :
                self.state = 'TRANSPORTS'
                self.doUpdateIdentity(arg)
                self.doPopBestProto(arg)
                self.doUpdateTransports(arg)
        #---CONTACTS---
        elif self.state is 'CONTACTS':
            if event == 'identity-sent-to-all' :
                self.state = 'INCOMMING?'
            elif ( ( event == 'network_connector.state' and arg is 'CONNECTED' ) ) or ( event == 'settings' and self.isIdentityChanged(arg) ) :
                self.state = 'TRANSPORTS'
                self.doUpdateIdentity(arg)
                self.doUpdateTransports(arg)
        #---INCOMMING?---
        elif self.state is 'INCOMMING?':
            if event == 'inbox-packet' and self.isUsingBestProto(arg) :
                self.state = 'CONNECTED'
                self.doInitRatings(arg)
                backup_monitor.A('restart')
                backup_db_keeper.A('restart')
                data_sender.A('restart')
            elif event == 'inbox-packet' and not self.isUsingBestProto(arg) :
                self.state = 'TRANSPORTS'
                self.doUpdateIdentity(arg)
                self.doPopBestProto(arg)
                self.doUpdateTransports(arg)
            elif ( event == 'network_connector.state' and arg is 'CONNECTED' ) or ( event == 'settings' and self.isIdentityChanged(arg) ) :
                self.state = 'TRANSPORTS'
                self.doUpdateIdentity(arg)
                self.doUpdateTransports(arg)
            elif event == 'timer-1min' or ( event == 'network_connector.state' and arg is 'DISCONNECTED' ) :
                self.state = 'DISCONNECTED'
                self.doInitRatings(arg)
        #---CONNECTED---
        elif self.state is 'CONNECTED':
            if ( event == 'network_connector.state' and arg is 'DISCONNECTED' ) :
                self.state = 'DISCONNECTED'
            elif ( event == 'network_connector.state' and arg not in [ 'CONNECTED' , 'DISCONNECTED' ] ) :
                self.state = 'NETWORK?'
            elif ( event == 'network_connector.state' and arg is 'CONNECTED' ) or ( event == 'settings' and self.isIdentityChanged(arg) ) :
                self.state = 'TRANSPORTS'
                self.doUpdateIdentity(arg)
                self.doUpdateTransports(arg)
            elif event == 'ping-contact' :
                self.doSendMyIdentity(arg)
        #---DISCONNECTED---
        elif self.state is 'DISCONNECTED':
            if ( event == 'network_connector.state' and arg not in [ 'CONNECTED', 'DISCONNECTED', ] ) :
                self.state = 'NETWORK?'
            elif event == 'inbox-packet' or ( event == 'settings' and self.isIdentityChanged(arg) ) or ( ( event == 'network_connector.state' and arg is 'CONNECTED' ) ) :
                self.state = 'TRANSPORTS'
                self.doUpdateIdentity(arg)
                self.doUpdateTransports(arg)
            elif event == 'ping-contact' :
                self.doSendMyIdentity(arg)

    def isUsingBestProto(self, arg):
        return DoWeUseTheBestProto()

    def isIdentityChanged(self, arg):
        return IDchanged(arg)
    
#    def isNetworkConnected(self, arg):
#        return network_connector.A().state is 'CONNECTED'

    def doInit(self, arg):
        global _RevisionNumber
        _RevisionNumber = dhnio.ReadTextFile(settings.RevisionNumberFile()).strip()
        dhnio.Dprint(4, 'p2p_connector.doInit RevisionNumber=%s' % str(_RevisionNumber))
        transport_control.AddInboxCallback(Inbox)
        if transport_control._TransportUDPEnable:
            try:
                import lib.transport_udp_session
                lib.transport_udp_session.SetStateChangedCallbackFunc(TransportUDPSessionStateChanged)
            except:
                dhnio.DprintException()

    def doUpdateIdentity(self, arg):
        UpdateIdentity()

    def doUpdateTransports(self, arg=None):
        UpdateTransports(arg)

    def doSendIdentityToIDServer(self, arg):
        identitypropagate.update().addCallbacks(
            lambda x: self.automat('id-server-success'),
            lambda x: self.automat('id-server-failed'), )
        
    def doSendIdentityToAllContacts(self, arg):
        self.ackCounter = 0
        def increaseAckCounter(packet):
            self.ackCounter += 1
        identitypropagate.start(
            increaseAckCounter, True).addBoth(
                lambda x: self.automat('identity-sent-to-all'))

    def doSendMyIdentity(self, arg):
        identitypropagate.single(arg, wide=True)

    def doPopBestProto(self, arg):
        PopWorkingProto()

    def doInitRatings(self, arg):
        ratings.init()

#-------------------------------------------------------------------------------

def Inbox(newpacket, proto, host, status=None, message=None):
    global _WorkingProtocols
    # here we mark this protocol as working
    if proto in ['tcp', 'udp',]:
        if not dhnnet.IpIsLocal(str(host).split(':')[0]):
            # but we want to check that this packet is come from the Internet, not our local network
            # because we do not want to use this proto as first method if it is not working for all
            if proto not in _WorkingProtocols:
                dhnio.Dprint(2, 'p2p_connector.Inbox [transport_%s] seems to work !!!!!!!!!!!!!!!!!!!!!' % proto)
                dhnio.Dprint(2, '                    We got the first packet from %s://%s' % (proto, str(host)))
                _WorkingProtocols.add(proto)
    elif proto in ['cspace',]:
        if proto not in _WorkingProtocols:
            dhnio.Dprint(2, 'p2p_connector.Inbox [transport_%s] seems to work !!!!!!!!!!!!!!!!!!!!!' % proto)
            dhnio.Dprint(2, '                    We got the first packet from %s://%s' % (proto, str(host)))
            _WorkingProtocols.add(proto)
    A('inbox-packet', (newpacket, proto, host, status, message))


def TransportUDPSessionStateChanged(automatindex, oldstate, newstate):
    if newstate != 'CONNECTED':
        return
    sess = automat.objects().get(automatindex, None)
    if sess is None:
        return
    idurl = sess.remote_idurl
    if idurl is None:
        return
    if contact_status.isOffline(idurl):
        A('ping-contact', idurl)

#------------------------------------------------------------------------------ 

def IPisLocal():
    externalip = misc.readExternalIP()
    localip = misc.readLocalIP()
    return localip != externalip


#if some transports was enabled or disabled we want to update identity contacts
#we empty all of the contacts and create it again in the same order
def UpdateIdentity():
    global _RevisionNumber
    global _WorkingProtocols

    #getting local identity
    lid = misc.getLocalIdentity()
    nowip = misc.readExternalIP()
    order = lid.getProtoOrder()
    lid.clearContacts()

    #prepare contacts data
    cdict = {}
    cdict['tcp'] = 'tcp://'+nowip+':'+settings.getTCPPort()
    if transport_control._TransportSSHEnable:
        cdict['ssh'] = 'ssh://'+nowip+':'+settings.getSSHPort()
    if transport_control._TransportHTTPEnable:
        cdict['http'] = 'http://'+nowip+':'+settings.getHTTPPort()
    if transport_control._TransportQ2QEnable:
        cdict['q2q'] = 'q2q://'+settings.getQ2Quserathost()
    if transport_control._TransportEmailEnable:
        cdict['email'] = 'email://'+settings.getEmailAddress()
    if transport_control._TransportCSpaceEnable:
        cdict['cspace'] = 'cspace://'+settings.getCSpaceKeyID()
    if transport_control._TransportUDPEnable:
        if stun.getUDPClient() is None or stun.getUDPClient().externalAddress is None:
            cdict['udp'] = 'udp://'+nowip+':'+settings.getUDPPort()
        else:
            cdict['udp'] = 'udp://'+stun.getUDPClient().externalAddress[0]+':'+str(stun.getUDPClient().externalAddress[1])

    #making full order list
    for proto in cdict.keys():
        if proto not in order:
            order.append(proto)

    #add contacts data to the local identity
    #check if some transport is not installed
    for proto in order:
        if settings.transportIsEnabled(proto) and settings.transportReceivingIsEnabled(proto):
            contact = cdict.get(proto, None)
            if contact is not None:
                lid.setProtoContact(proto, contact)
        else:
            # if protocol is disabled - mark this
            # because we may want to turn it on in the future
            _WorkingProtocols.discard(proto)
            
    #misc.setLocalIdentity(lid)

    del order

#    #if IP is not external and upnp configuration was failed for some reasons
#    #we want to use another contact methods, NOT tcp or ssh
#    if IPisLocal() and run_upnpc.last_result('tcp') != 'upnp-done':
#        dhnio.Dprint(4, 'p2p_connector.update_identity want to push tcp contact: local IP, no upnp ...')
#        lid.pushProtoContact('tcp')
#        misc.setLocalIdentity(lid)

    #update software version number
    revnum = _RevisionNumber.strip()
    repo, location = misc.ReadRepoLocation()
    lid.version = (revnum.strip() + ' ' + repo.strip() + ' ' + dhnio.osinfo().strip()).strip()
    
    #generate signature with changed content
    lid.sign()
    
    #remember the identity
    misc.setLocalIdentity(lid)

    #finally saving local identity
    misc.saveLocalIdentity()
    dhnio.Dprint(4, 'p2p_connector.UpdateIdentity')
    dhnio.Dprint(4, '    version: %s' % str(lid.version))
    dhnio.Dprint(4, '    contacts: %s' % str(lid.contacts))
    #_UpnpResult.clear()


def UpdateTransports(arg):
    dhnio.Dprint(4, 'p2p_connector.UpdateTransports')
    changes = set()
    if arg and arg not in [ 'CONNECTED', 'ONLY_ID' ]:
        changes = set(arg)
    # let's stop transport not needed anymore    
        pass


    def _stop_transports():
        stoplist = []
        for proto in transport_control.ListSupportedProtocols():
            contact = misc.getLocalIdentity().getProtoContact(proto)
            if contact is None:
                dhnio.Dprint(4, 'p2p_connector.UpdateTransports want to stop transport %s because not present in local identity' % proto)
                stoplist.append(transport_control.StopProtocol(proto))
                continue
            proto_, host, port, filename = nameurl.UrlParse(contact)
            if host.strip() == '':
                continue
            opts = transport_control.ProtocolOptions(proto)
            if opts[0].strip() == '':
                continue
            if proto != proto_:
                dhnio.Dprint(8, 'p2p_connector.UpdateTransports WARNING identity contact is %s, but proto is %s' % (contact, proto))
                continue
            #---tcp---
            if proto == 'tcp':
                if opts[0] != host:
                    dhnio.Dprint(4, 'p2p_connector.UpdateTransports want to stop transport [tcp] because IP changed')
                    stoplist.append(transport_control.StopProtocol(proto))
                    continue
                if opts[1] != port:
                    dhnio.Dprint(4, 'p2p_connector.UpdateTransports want to stop transport [tcp] because port changed')
                    stoplist.append(transport_control.StopProtocol(proto))
                    continue
            #---cspace---
            if proto == 'cspace':
                if opts[0] != host:
                    dhnio.Dprint(4, 'p2p_connector.UpdateTransports want to stop transport [cspace] because keyID changed: %s to %s' % (
                        host, opts[0]))
                    stoplist.append(transport_control.StopProtocol(proto))
                    continue
            #---udp---
            if proto == 'udp':
                if opts[0] != host:
                    dhnio.Dprint(4, 'p2p_connector.UpdateTransports want to stop transport [udp] because IP were changed')
                    stoplist.append(transport_control.StopProtocol(proto))
                    continue
                if opts[1] != port:
                    dhnio.Dprint(4, 'p2p_connector.UpdateTransports want to stop transport [udp] because port were changed')
                    stoplist.append(transport_control.StopProtocol(proto))
                    continue
                if 'transport.transport-udp.transport-udp-port' in changes and settings.enableUDP():
                    dhnio.Dprint(4, 'p2p_connector.UpdateTransports want to stop transport [udp] because port were changed by user')
                    stoplist.append(transport_control.StopProtocol(proto))
                    continue
        #need to wait before all listeners will be stopped
        return DeferredList(stoplist)

    # let's start transport that isn't started yet
    def _start_transports():
        startlist = []
        for contact in misc.getLocalIdentity().getContacts():
            proto, host, port, filename = nameurl.UrlParse(contact)
            opts = transport_control.ProtocolOptions(proto)
            if not transport_control.ProtocolIsSupported(proto):
                if settings.transportIsEnabled(proto) and settings.transportIsInstalled(proto) and settings.transportReceivingIsEnabled(proto):
                    #---tcp---
                    if proto == 'tcp':
                        def _tcp_started(l, opts):
                            dhnio.Dprint(4, 'p2p_connector.UpdateTransports._tcp_started')
                            if l is not None:
                                transport_control.StartProtocol('tcp', l, opts[0], opts[1], opts[2])
                            return l
                        def _tcp_failed(x):
                            dhnio.Dprint(4, 'p2p_connector.UpdateTransports._tcp_failed WARNING: '+str(x))
                            return x
                        def _start_tcp(options):
                            dhnio.Dprint(4, 'p2p_connector.UpdateTransports._start_tcp on port %d' % int(options[1]))
                            d = transport_tcp.receive(int(options[1]))
                            d.addCallback(_tcp_started, options)
                            d.addErrback(_tcp_failed)
                            startlist.append(d)
                        def _upnp_result(result, options):
                            dhnio.Dprint(4, 'p2p_connector.UpdateTransports._upnp_result %s' % str(result))
                            if result is not None:
                                options[1] = str(result[1])
                            _start_tcp(options)
                        def _run_upnpc(port):
                            shutdowner.A('block')
                            run_upnpc.update(port)
                            shutdowner.A('unblock')
                        externalIP = misc.readExternalIP() 
                        if opts is None:
                            opts = (externalIP, '', '')
                        opts = list(opts)
                        opts[0] = externalIP
                        opts[1] = settings.getTCPPort()
                        if settings.enableUPNP():
                            d = maybeDeferred(_run_upnpc, int(opts[1]))
                            d.addCallback(_upnp_result, opts)
                        else:
                            _start_tcp(opts)
                    #---cspace---
                    elif proto == 'cspace' and transport_control._TransportCSpaceEnable:
                        def _cspace_started(x, opts):
                            if not transport_cspace.registered():
                                dhnio.Dprint(4, 'p2p_connector.UpdateTransports._cspace_started WARNING not registered: ' + str(x))
                                return x
                            dhnio.Dprint(4, 'p2p_connector.UpdateTransports._cspace_started')
                            keyID = transport_cspace.keyID()
                            settings.setCSpaceKeyID(keyID)
                            opts[0] = keyID
                            l = transport_cspace.getListener()
                            transport_control.StartProtocol('cspace', l, opts[0], opts[1], opts[2])
                            return x
                        if opts is None:
                            opts = (settings.getCSpaceKeyID(), '', '')
                        opts = list(opts)
                        d = transport_cspace.init().addBoth(_cspace_started, opts)
                        startlist.append(d)
                    #---udp---
                    elif proto == 'udp' and transport_control._TransportUDPEnable:
                        def _udp_start(x, opts):
                            dhnio.Dprint(4, 'p2p_connector.UpdateTransports._udp_start')
                            if opts is None:
                                opts = (stun.getUDPClient().externalAddress[0], str(stun.getUDPClient().externalAddress[1]), '')
                            opts = list(opts)
                            opts[0] = stun.getUDPClient().externalAddress[0]
                            opts[1] = str(stun.getUDPClient().externalAddress[1])
                            transport_udp.init(stun.getUDPClient())
                            l = transport_udp.getListener()
                            if l is not None:
                                transport_control.StartProtocol('udp', l, opts[0], opts[1], opts[2])
                            return x
                        def _udp_failed(x):
                            dhnio.Dprint(4, 'p2p_connector.UpdateTransports._udp_failed')
                            return x
                        if stun.getUDPClient() is None or stun.getUDPClient().externalAddress is None:
                            d = stun.stunExternalIP(
                                close_listener=False, 
                                internal_port=settings.getUDPPort(), 
                                block_marker=shutdowner.A)
                        else:
                            d = succeed('')
                        d.addCallback(_udp_start, opts)
                        d.addErrback(_udp_failed)
                        startlist.append(d)
                        
        #need to wait before all listeners will be started
        return DeferredList(startlist)

    transport_control.init(
        lambda: _stop_transports().addBoth(
            lambda x: _start_transports().addBoth(
                lambda x: A('transports-updated'))))


def IDchanged(changes):
    s = set(changes)
    if s.intersection([
        'transport.transport-tcp.transport-tcp-enable',
        'transport.transport-tcp.transport-tcp-receiving-enable',
        'transport.transport-udp.transport-udp-enable',
        'transport.transport-udp.transport-udp-receiving-enable',
        'transport.transport-cspace.transport-cspace-enable',
        'transport.transport-cspace.transport-cspace-receiving-enable',
        # 'transport.transport-ssh.transport-ssh-enable',
        # 'transport.transport-http.transport-http-enable',
        # 'transport.transport-email.transport-email-enable',
        # 'transport.transport-q2q.transport-q2q-enable',
        # 'transport.transport-skype.transport-skype-enable',
        ]):
        return True
    if 'transport.transport-tcp.transport-tcp-port' in s and settings.enableTCP():
        return True
    if 'transport.transport-udp.transport-udp-port' in s and settings.enableUDP():
        return True
    if 'transport.transport-ssh.transport-ssh-port' in s and settings.enableSSH():
        return True
    if 'transport.transport-q2q.transport-q2q-username' in s and settings.enableQ2Q():
        return True
    if 'transport.transport-cspace.transport-cspace-key-id' in s and settings.enableCSpace():
        return True
    if 'transport.transport-http.transport-http-server-port' in s and settings.enableHTTP():
        return True
    if 'transport.transport-tcp.transport-tcp-port' in s and settings.enableTCP():
        return True
    return False

#    global _SettingsChanges
#    if _SettingsChanges.intersection([
#        'transport.transport-tcp.transport-tcp-enable',
#        'transport.transport-ssh.transport-ssh-enable',
#        'transport.transport-http.transport-http-enable',
#        'transport.transport-email.transport-email-enable',
#        'transport.transport-q2q.transport-q2q-enable',
#        'transport.transport-cspace.transport-cspace-enable',
#        'transport.transport-skype.transport-skype-enable',
#        ]):
#        return True
#    if 'transport.transport-tcp.transport-tcp-port' in _SettingsChanges and settings.enableTCP():
#        return True
#    if 'transport.transport-ssh.transport-ssh-port' in _SettingsChanges and settings.enableSSH():
#        return True
#    if 'transport.transport-q2q.transport-q2q-username' in _SettingsChanges and settings.enableQ2Q():
#        return True
#    if 'transport.transport-http.transport-http-server-port' in _SettingsChanges and settings.enableHTTP():
#        return True
#    if 'transport.transport-tcp.transport-tcp-port' in _SettingsChanges and settings.enableTCP():
#        return True
#    if 'transport.transport-cspace.transport-cspace-key-id' in _SettingsChanges and settings.enableCSpace():
#        return True
#    return False


def DoWeUseTheBestProto():
    global _WorkingProtocols
    #dhnio.Dprint(4, 'p2p_connector.DoWeUseTheBestProto _WorkingProtocols=%s' % str(_WorkingProtocols))
    #if no incomming traffic - do nothing
    if len(_WorkingProtocols) == 0:
        return True
    lid = misc.getLocalIdentity()
    order = lid.getProtoOrder()
    #if no protocols in local identity - do nothing
    if len(order) == 0:
        return True
    first = order[0]
    #if first contact in local identity is not working yet
    #but there is another working methods - switch first method
    if first not in _WorkingProtocols:
        dhnio.Dprint(2, 'p2p_connector.DoWeUseTheBestProto first contact (%s) is not working!   _WorkingProtocols=%s' % (first, str(_WorkingProtocols)))
        return False
    #if tcp contact is on first place and it is working - we are VERY HAPPY! - no need to change anything - return False
    if first == 'tcp' and 'tcp' in _WorkingProtocols:
        return True
    #but if tcp method is not the first and it works - we want to TURN IT ON! - return True
    if first != 'tcp' and 'tcp' in _WorkingProtocols:
        dhnio.Dprint(2, 'p2p_connector.DoWeUseTheBestProto tcp is not first but it works _WorkingProtocols=%s' % str(_WorkingProtocols))
        return False
    #if we are using cspace and it is working - this is fantastic!
    if transport_control._TransportCSpaceEnable:
        if first == 'cspace' and 'cspace' in _WorkingProtocols:
            return True
    #if we are using udp and it is working - not so bad
    if transport_control._TransportUDPEnable:
        if first == 'udp' and 'udp' in _WorkingProtocols:
            return True
    #cspace seems to be working and first contact is not working - so switch to cspace
    if transport_control._TransportCSpaceEnable:
        if first != 'cspace' and 'cspace' in _WorkingProtocols:
            dhnio.Dprint(2, 'p2p_connector.DoWeUseTheBestProto cspace is not first but it works _WorkingProtocols=%s' % str(_WorkingProtocols))
            return False
    #udp is working - we ca use it if all others is failed
    if transport_control._TransportUDPEnable:
        if first != 'udp' and 'udp' in _WorkingProtocols:
            dhnio.Dprint(2, 'p2p_connector.DoWeUseTheBestProto udp is not first but it works _WorkingProtocols=%s' % str(_WorkingProtocols))
            return False
    #in other cases - do nothing
    return True


def PopWorkingProto():
    global _WorkingProtocols
    if len(_WorkingProtocols) == 0:
        return
    lid = misc.getLocalIdentity()
    order = lid.getProtoOrder()
    first = order[0]
    wantedproto = ''
    #if first contact in local identity is not working yet
    #but there is another working methods - switch first method
    if first not in _WorkingProtocols:
        #take (but not remove) any item from the set
        wantedproto = _WorkingProtocols.pop()
        _WorkingProtocols.add(wantedproto)
    # if q2q method is not the first but it works - switch to q2q
    # disabled because we do not use q2q now
    # if first != 'q2q' and 'q2q' in _WorkingProtocols:
    #     wantedproto = 'q2q'
    #if udp method is not the first but it works - switch to udp
    if transport_control._TransportUDPEnable:
        if first != 'udp' and 'udp' in _WorkingProtocols:
            wantedproto = 'udp'
    #if cspace method is not the first but it works - switch to cspace
    if transport_control._TransportCSpaceEnable:
        if first != 'cspace' and 'cspace' in _WorkingProtocols:
            wantedproto = 'cspace'
    #if tcp method is not the first but it works - switch to tcp
    if first != 'tcp' and 'tcp' in _WorkingProtocols:
        wantedproto = 'tcp'
    dhnio.Dprint(4, 'p2p_connector.PopWorkingProto will pop %s contact   order=%s _WorkingProtocols=%s' % (wantedproto, str(order), str(_WorkingProtocols)))
    # now move best proto on the top
    # other users will use this method to send to us
    lid.popProtoContact(wantedproto)
    # save local id
    # also need to propagate our identity
    # other users must know our new contacts
    misc.setLocalIdentity(lid)
    misc.saveLocalIdentity() 


def WorkingProtos():
    global _WorkingProtocols
    return _WorkingProtocols


#------------------------------------------------------------------------------ 

def shutdown():
    dhnio.Dprint(4, 'p2p_connector.shutdown')
    automat.clear_object(A().index)

