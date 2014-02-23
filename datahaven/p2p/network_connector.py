#!/usr/bin/env python
#network_connector.py
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

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in network_connector.py')

from twisted.internet.defer import Deferred, maybeDeferred
from twisted.internet.task import LoopingCall
from twisted.internet import threads

from lib.automat import Automat
import lib.automats as automats

import lib.dhnio as dhnio
import lib.dhnnet as dhnnet
import lib.misc as misc
import lib.settings as settings
import lib.stun as stun
import lib.transport_control as transport_control
if transport_control._TransportCSpaceEnable:
    import lib.transport_cspace as transport_cspace

import p2p_connector
import central_connector
import shutdowner

import dhnicon
import run_upnpc


_NetworkConnector = None
_CounterSuccessConnections = 0
_CounterFailedConnections = 0
_LastSuccessConnectionTime = 0

#------------------------------------------------------------------------------

def A(event=None, arg=None):
    global _NetworkConnector
    if _NetworkConnector is None:
        _NetworkConnector = NetworkConnector('network_connector', 'AT_STARTUP', 4)
    if event is not None:
        _NetworkConnector.automat(event, arg)
    return _NetworkConnector


class NetworkConnector(Automat):
    timers = { 'timer-1min':  (60,   ['CSPACE']),
               'timer-5sec':  (5,    ['CONNECTED', 'DISCONNECTED']),
               'timer-1hour': (60*60, ['DISCONNECTED'] )}
    fast = False
    last_upnp_time = 0
    last_reconnect_time = 0
    last_internet_state = 'disconnected'

    def state_changed(self, oldstate, newstate):
        automats.set_global_state('NETWORK ' + newstate)
        p2p_connector.A('network_connector.state', newstate)
        dhnicon.state_changed(self.state, p2p_connector.A().state, central_connector.A().state)

    def A(self, event, arg):
        #---AT_STARTUP---
        if self.state is 'AT_STARTUP':
            if event == 'init' :
                self.state = 'CSPACE'
                self.doInit(arg)
                self.doCSpaceInit(arg)
                self.Disconnects=0
        #---STUN---
        elif self.state is 'STUN':
            if event == 'stun-success' and not self.isUPNP(arg) :
                self.state = 'CONNECTED'
                self.doDropCounters(arg)
            elif event == 'stun-success' and self.isUPNP(arg) :
                self.state = 'UPNP'
                self.doUPNP(arg)
            elif event == 'stun-failed' :
                self.state = 'DISCONNECTED'
        #---UPNP---
        elif self.state is 'UPNP':
            if event == 'upnp-done' :
                self.state = 'CONNECTED'
                self.doDropCounters(arg)
        #---CONNECTED---
        elif self.state is 'CONNECTED':
            if event == 'timer-5sec' :
                self.doDropCounters(arg)
            elif event == 'reconnect' :
                self.state = 'NETWORK?'
                self.doDropCounters(arg)
                self.doCheckNetworkInterfaces(arg)
                self.Disconnects=0
                self.doRestart(arg)
            elif ( event == 'timer-5sec' or event == 'connection-failed' or event == 'connection-done' ) and not self.isConnectionAlive(arg) :
                self.state = 'NETWORK?'
                self.doDropCounters(arg)
                self.doCheckNetworkInterfaces(arg)
                self.Disconnects=0
        #---NETWORK?---
        elif self.state is 'NETWORK?':
            if event == 'got-network-info' and not self.isNetworkActive(arg) :
                self.state = 'DISCONNECTED'
            elif event == 'got-network-info' and self.isNetworkActive(arg) and self.isCurrentInterfaceActive(arg) :
                self.state = 'INTERNET?'
                self.doTestInternetConnection(arg)
            elif event == 'got-network-info' and self.isNetworkActive(arg) and not self.isCurrentInterfaceActive(arg) :
                self.state = 'CSPACE'
                self.doCSpaceInit(arg)
        #---INTERNET?---
        elif self.state is 'INTERNET?':
            if event == 'internet-failed' :
                self.state = 'DISCONNECTED'
                self.doRememberInternetState(arg)
            elif event == 'internet-success' :
                self.state = 'CSPACE'
                self.doRememberInternetState(arg)
                self.doCSpaceInit(arg)
        #---DISCONNECTED---
        elif self.state is 'DISCONNECTED':
            if event == 'reconnect' or ( event == 'connection-done' and self.isTimePassed(arg) ) or event == 'timer-1hour' or ( event == 'timer-5sec' and self.Disconnects<3 ) :
                self.state = 'NETWORK?'
                self.doCheckNetworkInterfaces(arg)
                self.doRememberTime(arg)
                self.Disconnects+=1
        #---CSPACE---
        elif self.state is 'CSPACE':
            if event == 'cspace-done' or event == 'timer-1min' :
                self.state = 'STUN'
                self.doStunExternalIP(arg)

    def isUPNP(self, arg):
        return settings.enableUPNP() and time.time() - self.last_upnp_time < 60*60

    def isConnectionAlive(self, arg):
        global _CounterSuccessConnections
        global _CounterFailedConnections
        global _LastSuccessConnectionTime
        # if no info yet - we think positive 
        if _CounterSuccessConnections == 0 and _CounterFailedConnections == 0:
            return True
        # if we have only 3 or less failed reports - hope no problems yet 
        if _CounterFailedConnections <= 3:
            return True
        # at least one success report - the connection should be fine
        if _CounterSuccessConnections >= 1:
            return True
        # no success connections after last "drop counters", 
        # but last success connection was not so far 
        if time.time() - _LastSuccessConnectionTime < 60 * 5:
            return True
        # more success than failed - connection is not failed for sure
        if _CounterSuccessConnections > _CounterFailedConnections:
            return True
        dhnio.Dprint(6, 'network_connector.isConnectionAlive    %d/%d' % (_CounterSuccessConnections, _CounterFailedConnections) )
        return False

    def isNetworkActive(self, arg):
        return len(arg) > 0
    
    def isCurrentInterfaceActive(self, arg):
        # Not sure about external IP, because if we have white IP it is the same to local IP
        return ( misc.readLocalIP() in arg ) or ( misc.readExternalIP() in arg ) 

    def isTimePassed(self, arg):
        return time.time() - self.last_reconnect_time < 15

    def doInit(self, arg):
        # if transport_control._TransportCSpaceEnable:
        #     transport_cspace.SetStatusNotifyFunc(cspace_status_changed)
        if transport_control._TransportUDPEnable:
            import lib.transport_udp_session
            lib.transport_udp_session.SetNetworkAddressChangedFunc(NetworkAddressChangedCallback)
        dhnnet.SetConnectionDoneCallbackFunc(ConnectionDoneCallback)
        dhnnet.SetConnectionFailedCallbackFunc(ConnectionFailedCallback)

    def doStunExternalIP(self, arg):
        dhnio.Dprint(4, 'network_connector.doStunExternalIP last result %s was %d seconds ago' % (stun.last_stun_result(), time.time()-stun.last_stun_time()))
        
        def stun_success(externalip):
            if externalip == '0.0.0.0':
                ConnectionFailedCallback(str(externalip), 'stun', '')
                self.automat('stun-failed')
                return
            localip = dhnnet.getLocalIp()
            dhnio.WriteFile(settings.ExternalIPFilename(), str(externalip))
            dhnio.WriteFile(settings.LocalIPFilename(), str(localip))
            ConnectionDoneCallback(str(externalip), 'stun', '')
            self.automat('stun-success')
            
        def stun_failed(x):
            ConnectionFailedCallback(str(x), 'stun', '')
            self.automat('stun-failed')
            
        if time.time() - stun.last_stun_time() < 60:
            if stun.last_stun_result():
                if stun.last_stun_result() != '0.0.0.0':
                    self.automat('stun-success')
                else:
                    self.automat('stun-failed')
            else:
                if self.last_internet_state == 'connected':
                    self.automat('stun-success')
                else:
                    self.automat('stun-failed')
            return
        
        stun.stunExternalIP(
            close_listener=False, 
            internal_port=settings.getUDPPort(),
            block_marker=shutdowner.A,
            verbose=True if dhnio.Debug(10) else False).addCallbacks(
                stun_success, stun_failed)

    def doDropCounters(self, arg):
        global _CounterSuccessConnections
        global _CounterFailedConnections
        # dhnio.Dprint(12, 'network_connector.doDropCounters     current is %d/%d' % (_CounterSuccessConnections, _CounterFailedConnections))
        _CounterSuccessConnections = 0
        _CounterFailedConnections = 0

    def doUPNP(self, arg):
        self.last_upnp_time = time.time()
        UpdateUPNP()

    def doTestInternetConnection(self, arg):
        dhnio.Dprint(4, 'network_connector.doTestInternetConnection')
        dhnnet.TestInternetConnection().addCallbacks(
            lambda x: self.automat('internet-success', 'connected'), 
            lambda x: self.automat('internet-failed', 'disconnected'))
            
    def doCheckNetworkInterfaces(self, arg):
        dhnio.Dprint(4, 'network_connector.doCheckNetworkInterfaces')
        # TODO
        # self.automat('got-network-info', [])
        start_time = time.time()
        if dhnio.Linux():
            def _call():
                return dhnnet.getNetworkInterfaces()
            def _done(result, start_time):
                dhnio.Dprint(4, 'network_connector.doCheckNetworkInterfaces._done: %s in %d seconds' % (str(result), time.time()- start_time))
                self.automat('got-network-info', result)
            d = threads.deferToThread(_call)
            d.addBoth(_done, start_time)
        else:
            ips = dhnnet.getNetworkInterfaces()
            dhnio.Dprint(4, 'network_connector.doCheckNetworkInterfaces DONE: %s in %d seconds' % (str(ips), time.time()- start_time))
            self.automat('got-network-info', ips)

    def doRememberTime(self, arg):
        self.last_reconnect_time = time.time()

    def doCSpaceInit(self, arg):
        if transport_control._TransportCSpaceEnable and settings.enableCSpace():
            def _cspace_done(x):
                if transport_cspace.registered():
                    settings.setCSpaceKeyID(transport_cspace.keyID())
                self.automat('cspace-done', transport_cspace.A().state)
            transport_cspace.init().addBoth(_cspace_done)
        else:
            self.automat('cspace-done', None)

    def doRememberInternetState(self, arg):
        self.last_internet_state = arg

    def doRestart(self, arg):
        try:
            import lib.transport_control
            lib.transport_control.cancel_all_transfers()
            if transport_control._TransportUDPEnable: 
                import lib.transport_udp
                lib.transport_udp.A('reconnect')
            import lib.transport_tcp
            lib.transport_tcp.disconnect_all()
        except:
            dhnio.DprintException()

#------------------------------------------------------------------------------ 


def UpdateUPNP():
    #global _UpnpResult
    dhnio.Dprint(8, 'network_connector.UpdateUPNP ')

#    protos_need_upnp = set(['tcp', 'ssh', 'http'])
    protos_need_upnp = set(['tcp',])

    #we want to update only enabled protocols
    if not settings.enableTCP():
        protos_need_upnp.discard('tcp')
    # if not settings.enableSSH() or not transport_control._TransportSSHEnable:
    #     protos_need_upnp.discard('ssh')
    # if not settings.enableHTTPServer() or not transport_control._TransportHTTPEnable:
    #     protos_need_upnp.discard('http')

    def _update_next_proto():
        if len(protos_need_upnp) == 0:
            #dhnio.Dprint(4, 'network_connector.update_upnp done: ' + str(_UpnpResult))
            A('upnp-done')
            return
        dhnio.Dprint(14, 'network_connector.UpdateUPNP._update_next_proto ' + str(protos_need_upnp))
        proto = protos_need_upnp.pop()
        protos_need_upnp.add(proto)
        if proto == 'tcp':
            port = settings.getTCPPort()
        elif proto == 'ssh':
            port = settings.getSSHPort()
        elif proto == 'http':
            port = settings.getHTTPPort()
        d = threads.deferToThread(_call_upnp, port)
        d.addCallback(_upnp_proto_done, proto)

    def _call_upnp(port):
        # start messing with upnp settings
        # success can be false if you're behind a router that doesn't support upnp
        # or if you are not behind a router at all and have an external ip address
        shutdowner.A('block')
        success, port = run_upnpc.update(port)
        shutdowner.A('unblock')
        return (success, port)

    def _upnp_proto_done(result, proto):
        dhnio.Dprint(4, 'network_connector.UpdateUPNP._upnp_proto_done %s: %s' % (proto, str(result)))
        #_UpnpResult[proto] = result[0]
        #if _UpnpResult[proto] == 'upnp-done':
        if result[0] == 'upnp-done':
            if proto == 'tcp':
                settings.setTCPPort(result[1])
            elif proto == 'ssh':
                settings.setSSHPort(result[1])
            elif proto == 'http':
                settings.setHTTPPort(result[1])
        protos_need_upnp.discard(proto)
        reactor.callLater(0, _update_next_proto)

    _update_next_proto()


def cspace_status_changed(status):
    dhnio.Dprint(4, 'network_connector.cspace_status_changed [%s]' % status.upper())
    A('cspace-status', status)


def ConnectionDoneCallback(param, proto, info):
    global _CounterSuccessConnections 
    global _LastSuccessConnectionTime
    _CounterSuccessConnections += 1
    _LastSuccessConnectionTime = time.time()
    A('connection-done')
    
    
def ConnectionFailedCallback(param, proto, info):
    global _CounterFailedConnections
    if proto is not 'udp':
        _CounterFailedConnections += 1
    A('connection-failed')

def NetworkAddressChangedCallback(newaddress):
    A('reconnect')



