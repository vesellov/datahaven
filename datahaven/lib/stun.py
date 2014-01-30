#!/usr/bin/python
#stun.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#

import sys
import sets
import struct
import time


try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in stun.py')

from twisted.internet.defer import Deferred, succeed, fail
# from twisted.python import log, failure

import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)


import shtoom.stun
import shtoom.nat
import dhnio


_WorkingDefers = []
_IsWorking = False
_UDPListener = None
_StunClient = None
_LastStunTime = 0
_LastStunResult = None
_TimeoutTask = None

#------------------------------------------------------------------------------ 

class IPStunProtocol(shtoom.stun.StunDiscoveryProtocol):
    datagram_received_callback = None

    def stateChanged(self, old, new):
        dhnio.Dprint(4, 'stun.stateChanged [%s]->[%s]' % (old, new))

    def finishedStun(self):
        local = '0.0.0.0'
        ip = '0.0.0.0'
        port = '0'
        typ = 'unknown'
        alt = 'unknown'
        try:
            if self.externalAddress and self.localAddress and self.natType:
                local = str(self.localAddress)
                ip = str(self.externalAddress[0])
                port = str(self.externalAddress[1])
                typ = str(self.natType.name)
                alt = str(self._altStunAddress) 
        except:
            dhnio.DprintException()
        dhnio.Dprint(2, 'stun.IPStunProtocol.finishedStun local=%s external=%s altStun=%s NAT_type=%s' % (
            local, ip+':'+port, alt, typ))
        if self.result is not None:
            if not self.result.called:
                if ip == '0.0.0.0':
                    self.result.callback(ip)
                else:
                    self.result.callback(ip)
            self.result = None

#    def _hostNotResolved(self, x, localAddress):
#        dhnio.Dprint(2, 'stun.IPStunProtocol._hostNotResolved : %s' % str(x))
#        if self.timerTask and not self.timerTask.called and not self.timerTask.cancelled:
#            self.timerTask.cancel()
#            self.timerTask = None 
#        if not self._finished:
#            self._finishedStun()
    
    def datagramReceived(self, dgram, address):
        # print '    %d bytes from %s' % (len(dgram), str(address)) 
        if self._finished:
            if self.datagram_received_callback is not None:
                return self.datagram_received_callback(dgram, address)
        else:
            stun_dgram = dgram[:20]
            if len(stun_dgram) < 20:
                if self.datagram_received_callback is None:
                    return
                return self.datagram_received_callback(dgram, address)
            else:
                try:
                    mt, pktlen, tid = struct.unpack('!hh16s', stun_dgram)
                except:
                    if self.datagram_received_callback is None:
                        return
                    return self.datagram_received_callback(dgram, address)
        return shtoom.stun.StunDiscoveryProtocol.datagramReceived(self, dgram, address)
    
    def refresh(self):
        self._potentialStuns = {}
        self._stunState = '1'
        self._finished = False
        self._altStunAddress = None
        self.externalAddress = None
        self.localAddress = None
        self.expectedTID = None
        self.oldTIDs = sets.Set()
        self.natType = None
        self.result = Deferred()
        self.count = 0
        self.servers = [(host, port) for host, port in shtoom.stun.DefaultServers]
        
    def setCallback(self, cb, arg=None):
        self.result.addBoth(cb, arg)


def stunExternalIP(timeout=10, verbose=False, close_listener=True, internal_port=5061, block_marker=None):
    global _WorkingDefers
    global _IsWorking
    global _UDPListener
    global _StunClient
    global _LastStunTime
    global _TimeoutTask
    
    if _IsWorking:
        res = Deferred()
        _WorkingDefers.append(res)
        dhnio.Dprint(4, 'stun.stunExternalIP SKIP, already called')
        return res
    
    res = Deferred()
    _WorkingDefers.append(res)
    _IsWorking = True

    dhnio.Dprint(2, 'stun.stunExternalIP')

    shtoom.stun.STUNVERBOSE = verbose
    shtoom.nat._Debug = verbose
    shtoom.nat._cachedLocalIP = None
    shtoom.nat.getLocalIPAddress.clearCache()
    
    if _UDPListener is None:
        dhnio.Dprint(4, 'stun.stunExternalIP prepare listener')
        if _StunClient is None:
            _StunClient = IPStunProtocol()
        else:
            _StunClient.refresh()
    
        try:
            UDP_port = int(internal_port)
            _UDPListener = reactor.listenUDP(UDP_port, _StunClient)
            dhnio.Dprint(4, 'stun.stunExternalIP UDP listening on port %d started' % UDP_port)
        except:
            try:
                _UDPListener = reactor.listenUDP(0, _StunClient)
                dhnio.Dprint(4, 'stun.stunExternalIP multi-cast UDP listening started')
            except:
                dhnio.DprintException()
                for d in _WorkingDefers:
                    d.callback('0.0.0.0')
                _WorkingDefers = []
                _IsWorking = False
                return res

    dhnio.Dprint(6, 'stun.stunExternalIP refresh stun client')
    _StunClient.refresh()
    _StunClient.timeout = timeout

    def stun_finished(x, block_marker):
        global _UDPListener
        global _StunClient
        global _WorkingDefers
        global _IsWorking
        global _LastStunResult
        global _TimeoutTask 
        
        if block_marker:
            block_marker('unblock')
        dhnio.Dprint(6, 'stun.stunExternalIP.stun_finished: ' + str(x).replace('\n', ''))
        _LastStunResult = x
        try:
            if _IsWorking:
                _IsWorking = False
                for d in _WorkingDefers:
                    if x == '0.0.0.0':
                        d.callback(x)
                    else:
                        d.callback(x)
            _WorkingDefers = []
            _IsWorking = False
            if _UDPListener is not None and close_listener is True:
                _UDPListener.stopListening()
                _UDPListener = None
            if _StunClient is not None and close_listener is True:
                del _StunClient
                _StunClient = None
        except:
            dhnio.DprintException()
    
    _StunClient.setCallback(stun_finished, block_marker)

    dhnio.Dprint(6, 'stun.stunExternalIP starting discovery')
    if block_marker:
        block_marker('block')
    reactor.callLater(0, _StunClient.startDiscovery)

    _LastStunTime = time.time() 
    return res


def getUDPListener():
    global _UDPListener
    return _UDPListener


def getUDPClient():
    global _StunClient
    return _StunClient


def stopUDPListener():
    dhnio.Dprint(6, 'stun.stopUDPListener')
    global _UDPListener
    global _StunClient
    result = None
    if _UDPListener is not None:
        result = _UDPListener.stopListening()
        _UDPListener = None
    if _StunClient is not None:
        del _StunClient
        _StunClient = None   
    if result is None:
        result = succeed(1)
    return result     

def last_stun_time():
    global _LastStunTime 
    return _LastStunTime 

def last_stun_result():
    global _LastStunResult
    return _LastStunResult

#------------------------------------------------------------------------------ 

def success(x):
    print x
    if sys.argv.count('continue'):
        reactor.callLater(10, main)
    else:
        reactor.stop()

def fail(x):
    print x
    if sys.argv.count('continue'):
        reactor.callLater(5, main)
    else:
        reactor.stop()

def main(verbose=False):
    if sys.argv.count('port'):
        d = stunExternalIP(verbose=verbose, close_listener=False, internal_port=int(sys.argv[sys.argv.index('port')+1]))
    else:
        d = stunExternalIP(verbose=verbose, close_listener=False,)
    d.addCallback(success)
    d.addErrback(fail)

#------------------------------------------------------------------------------ 

if __name__ == "__main__":
    dhnio.init()
    if sys.argv.count('quite'):
        dhnio.SetDebug(0)
        main(False)
    else:
        # log.startLogging(sys.stdout)
        dhnio.SetDebug(20)
        main(True)
    reactor.run()






