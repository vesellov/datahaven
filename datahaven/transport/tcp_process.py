#!/usr/bin/python
#tcp_process.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#



"""
This is a 
This is a sub process to send/receive files between users over TCP protocol.
1) listen for incoming connections on a port 7771 (by default) 
2) establish connections to remote peers
3) keeps TCP session opened to be able to send asap 
"""

import os
import sys
import time
import optparse

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in tcp_process.py')

from twisted.web import xmlrpc
from twisted.internet import task
from twisted.internet import protocol
from twisted.protocols import basic
from twisted.web import server
from twisted.internet.defer import Deferred 
from twisted.internet.error import ConnectionDone

import lib.dhnio as dhnio
import lib.tmpfile as tmpfile

import abstract

#------------------------------------------------------------------------------ 

_InternalPort = 7771
_Listener = None
_XMLRPCListener = None
_XMLRPCProxy = None

#------------------------------------------------------------------------------ 

class TCPFileSender(basic.FileSender):
    def __init__(self, protocol, inputfile, filename, sz, do_status_report, result_defer, description):
        global _RegisterTransferFunc
        global _ByTransferID
        self.protocol = protocol
        self.inputfile = inputfile
        self.filename = filename
        self.sz = sz
        self.do_status_report = do_status_report 
        self.result_defer = result_defer
        self.description = description
        self.sentBytes = 0
        self.peer = self.protocol.remoteaddress # self.protocol.transport.getPeer()
        self.transfer_id = _RegisterTransferFunc(
            'send', self.peer, self.getSentBytes, filename, sz, description)
        _ByTransferID[self.transfer_id] = self.protocol
        # dhnio.Dprint(14, 'transport_tcp.TCPFileSender.init length=%d transfer_id=%s' % (self.sz, self.transfer_id))

    # def __del__(self):
    #     dhnio.Dprint(14, 'transport_tcp.TCPFileSender.del length=%d transfer_id=%s' % (self.sz, self.transfer_id))

    def getSentBytes(self):
        return self.sentBytes
    
    def transformData(self, data):
        datalength = len(data)
        self.sentBytes += datalength
        self.protocol.totalBytesSent += datalength
        return data

class TCPFileReceiver():
    def __init__(self, protocol, length):
        global _RegisterTransferFunc
        global _ByTransferID
        self.protocol = protocol
        self.receivedBytes = 0
        self.length = length
        self.fd, self.filename = tmpfile.make("tcp-in")
        self.peer = self.protocol.remoteaddress # self.protocol.transport.getPeer()
        self.transfer_id = _RegisterTransferFunc(
            'receive', self.peer, self.getReceivedBytes, self.filename, -1)
        _ByTransferID[self.transfer_id] = self.protocol
        # dhnio.Dprint(14, 'transport_tcp.TCPFileReceiver.init length=%d transfer_id=%s' % (self.length, self.transfer_id))
        
    # def __del__(self):
    #     dhnio.Dprint(14, 'transport_tcp.TCPFileReceiver.del length=%d transfer_id=%s' % (self.length, self.transfer_id))

    def getReceivedBytes(self):
        return self.receivedBytes

    def dataReceived(self, data):
        amount = len(data)
        amt = amount
        tail = ''
        if self.length >= 0:
            moreneeded = self.length - self.receivedBytes
            if amount > moreneeded:
                tail = data[moreneeded:]
                data = data[:moreneeded]
                amount = moreneeded
        self.receivedBytes += amount
        os.write(self.fd, data)
        return tail
        
    def close(self, result, reason):    
        global _UnRegisterTransferFunc
        global _ByTransferID
        global _ReceiveStatusFunc
        if self.transfer_id is not None:
            _UnRegisterTransferFunc(self.transfer_id)
            _ByTransferID.pop(self.transfer_id)
        try:
            os.close(self.fd)
        except:
            dhnio.DprintException()
        _ReceiveStatusFunc(self.filename, result, 'tcp', self.peer, reason)
        
    def eof(self):
        self.close('finished', 'file received successfully')    
        
    def cancel(self):
        self.close('failed', 'transfer cancelled')
        
    def lost(self, result, reason):
        self.close(result, reason)
    

class TCPProtocol(protocol.Protocol):
    def __init__(self):
        self.outbox = []
        self.singleconnection = False
        self.remoteaddress = None
        self.peeraddress = None
        self.remoteinternalport = None
        self.fileSender = None
        self.fileReceiver = None
        self.type = None
        self.totalBytesReceived = 0
        self.totalBytesSent = 0
        self.connected = 0
        self.disconnectingTask = None
    
    def __repr__(self):
        return 'TCPProtocol%s [%d files]' % (self.peeraddress, len(self.outbox))
    
    def connectionMade(self):
        dhnio.Dprint(14, 'transport_tcp.TCPProtocol.connectionMade %s' % str(self.transport.getPeer()))
        global _InternalPort
        global _StartedConnections
        global _OpenedConnections
        global _ConnectionsCounter
        self.connected = time.time()
        self.peeraddress = (self.transport.getPeer().host, int(self.transport.getPeer().port))
        self.remoteaddress = self.peeraddress
        started = _StartedConnections.pop(self.peeraddress, None)
        if started:
            # connecting
            self.remoteinternalport = self.remoteaddress[1]
            self.transport.write('0 port %d ' % _InternalPort)
            self.type = 'client'
        else:
            # listening
            self.type = 'server'
        if self.remoteaddress not in _OpenedConnections:
            _OpenedConnections[self.remoteaddress] = []
        _OpenedConnections[self.remoteaddress].append(self)
        _ConnectionsCounter += 1
        for filename, do_status_report, result_defer, description in self.factory.pendingoutboxfiles:
            self.sendfile(filename, do_status_report, result_defer, description)
        self.factory.pendingoutboxfiles = []
        # dhnio.Dprint(16, '    %s' % str(_OpenedConnections))
        # dhnio.Dprint(16, '    %s' % str(_StartedConnections))
     
    def connectionLost(self, reason):
        global _OpenedConnections
        global _ConnectionsCounter
        global _RedirectionsMap
        dhnio.Dprint(14, 'transport_tcp.TCPProtocol.connectionLost with %s' % str(self.transport.getPeer()))
        self.shutdown(reason)
        if self.remoteaddress in _OpenedConnections:
            try:
                _OpenedConnections[self.remoteaddress].remove(self)
            except:
                pass
            if len(_OpenedConnections[self.remoteaddress]) == 0:
                _OpenedConnections.pop(self.remoteaddress)
#        if self.remoteaddress in _RedirectionsMap:
#            _RedirectionsMap.pop(self.remoteaddress)
#        redirects = _RedirectionsMap.keys()
#        for oldaddress in redirects:
#            if _RedirectionsMap[oldaddress] == self.remoteaddress:
#                _RedirectionsMap.pop(oldaddress)
        _ConnectionsCounter -= 1
        # dhnio.Dprint(16, '    %s' % str(_OpenedConnections))
        # dhnio.Dprint(16, '    %s' % str(_StartedConnections))

    def disconnect(self):
        dhnio.Dprint(14, 'transport_tcp.TCPProtocol.disconnect with %s' % str(self.remoteaddress))
        if self.fileSender is not None:
            self.fileSender.file = None
            self.fileSender.stopProducing()
        try:
            self.transport.abortConnection()
        except:
            self.transport.loseConnection()
    
    def dataReceived(self, data):
        global _OpenedConnections
        global _RedirectionsMap
        if self.remoteinternalport is None:
            try:
                _data = data
                ver, x, _data = _data.partition(' ')
                cmd, x, _data = _data.partition(' ')
                port, x, _data = _data.partition(' ')
                int(ver)
                assert cmd in ['port',]
                self.remoteinternalport = int(port)
                data = _data
            except:
                self.remoteinternalport = self.remoteaddress[1]
                self.singleconnection = True
                # dhnio.DprintException()
                # self.disconnect()
            if self.remoteaddress[1] != self.remoteinternalport:
                oldport = self.remoteaddress[1]
                _OpenedConnections[self.remoteaddress].remove(self)
                if len(_OpenedConnections[self.remoteaddress]) == 0:
                    _OpenedConnections.pop(self.remoteaddress)
                old = self.remoteaddress
                self.remoteaddress = (self.transport.getPeer().host, self.remoteinternalport)
                if self.remoteaddress not in _OpenedConnections:
                    _OpenedConnections[self.remoteaddress] = []
                _OpenedConnections[self.remoteaddress].append(self)
                # _RedirectionsMap[old] = self.remoteaddress
                dhnio.Dprint(12, 'transport_tcp.TCPProtocol.dataReceived %s internal port changed %d->%d' % (
                    self, oldport, self.remoteinternalport))
        if not data:
            return
        if self.fileReceiver is None:
            try:
                _data = data
                ver, x, _data = _data.partition(' ')
                cmd, x, _data = _data.partition(' ')
                length, x, _data = _data.partition(' ')
                int(ver)
                assert cmd in ['length',]
                length = int(length)
                data = _data
            except:
                length = -1
                self.singleconnection = True
                # dhnio.DprintException()
                # self.disconnect()
                # return
            self.fileReceiver = TCPFileReceiver(self, length)
        tail = self.fileReceiver.dataReceived(data)
        self.totalBytesReceived += len(data) - len(tail)
        if self.fileReceiver.length == self.fileReceiver.receivedBytes:
            self.fileReceiver.eof()
            del self.fileReceiver
            self.fileReceiver = None 
            if self.remoteaddress in _OpenedConnections:
                if len(_OpenedConnections[self.remoteaddress]) > 1:
                    if self in _OpenedConnections[self.remoteaddress]:
                        dhnio.Dprint(14, 'transport_tcp.TCPProtocol.finishedTransfer want to close extra connection to %s' % (str(self.remoteaddress)))
                        self.disconnect()
                        return
            if opened_connections_count() > 200:
                dhnio.Dprint(12, 'transport_tcp.TCPProtocol.dataReceived too many opened connections, disconnect with %s' % (str(self.remoteaddress)))
                self.disconnect()
                return
        if tail:
            self.dataReceived(tail)
                    

    def sendfile(self, filename, do_status_report, result_defer, description):
        global _ByTransferID
        global _SendStatusFunc
        # global _SingleConnectionHosts
        if self.type == 'client':
            if self.totalBytesReceived == 0:
                if time.time() - self.connected > 60.0:
                    # _SingleConnectionHosts.add(self.remoteaddress[0])
                    if do_status_report:
                        reactor.callLater(0, _SendStatusFunc, self.remoteaddress, filename, 'failed', 'tcp', None, 'remote peer not responding')
                    if result_defer is not None:
                        if not result_defer.called:
                            result_defer.errback(Exception('failed'))
                    dhnio.Dprint(14, 'transport_tcp.TCPProtocol.sendfile connection idle, disconnect with %s' % (str(self.remoteaddress)))        
                    self.disconnect()
                    return
        if not os.path.isfile(filename):
            if do_status_report:
                reactor.callLater(0, _SendStatusFunc, self.remoteaddress, filename, 'failed', 'tcp', None, 'file not exist')
            if result_defer is not None:
                if not result_defer.called:
                    result_defer.errback(Exception('failed'))
            dhnio.Dprint(14, 'transport_tcp.TCPProtocol.sendfile sending file not exist, disconnect with %s' % (str(self.remoteaddress)))
            self.disconnect()
            return
        try:
            sz = os.path.getsize(filename)
        except:
            dhnio.DprintException()
            if do_status_report:
                reactor.callLater(0, _SendStatusFunc, self.remoteaddress, filename, 'failed', 'tcp', None, 'error opening file')
            if result_defer is not None:
                if not result_defer.called:
                    result_defer.errback(Exception('failed'))
            dhnio.Dprint(14, 'transport_tcp.TCPProtocol.sendfile reading file size ERROR, disconnect with %s' % (str(self.remoteaddress)))
            self.disconnect()
            return
        self.outbox.append((filename, sz, do_status_report, result_defer, description))  
        reactor.callLater(0, self.processoutbox)
        
    def processoutbox(self):
        global _SendStatusFunc
        if len(self.outbox) == 0:
            return
        if self.fileSender is not None:
            return
        filename, sz, do_status_report, result_defer, description = self.outbox.pop(0)
        try:
            fin = open(filename, 'rb')
        except:
            dhnio.DprintException()
            if do_status_report:
                _SendStatusFunc(self.remoteaddress, filename, 'failed', 'tcp', None, 'error opening file')
            if result_defer is not None:
                if not result_defer.called:
                    result_defer.errback(Exception('failed'))
            dhnio.Dprint(14, 'transport_tcp.TCPProtocol.sendfile opening file ERROR, disconnect with %s' % (str(self.remoteaddress)))
            self.disconnect()
            return
        self.transport.write('0 length %d ' % sz)
        self.fileSender = TCPFileSender(self, fin, filename, sz, do_status_report, result_defer, description)
        d = self.fileSender.beginFileTransfer(fin, self.transport, self.fileSender.transformData)
        d.addCallback(self.finishedTransfer)
        d.addErrback(self.transferFailed)

    def finishedTransfer(self, result):
        global _UnRegisterTransferFunc
        global _ByTransferID
        global _SendStatusFunc
        global _OpenedConnections
        # global _SingleConnectionHosts
        # dhnio.Dprint(14, 'transport_tcp.TCPProtocol.finishedTransfer host=%s file=%s' % (
        #     str((self.transport.getPeer().host, int(self.transport.getPeer().port))), self.fileSender.filename,))
        try:
            self.fileSender.inputfile.close()
        except:
            dhnio.Dprint(1, 'transport_tcp.TCPProtocol.finishedTransfer ERROR close file failed')
            dhnio.DprintException()
        if self.fileSender.do_status_report:
            _SendStatusFunc(self.remoteaddress, self.fileSender.filename, 'finished', 'tcp')
        if self.fileSender.result_defer is not None:
            if not self.fileSender.result_defer.called:
                self.fileSender.result_defer.callback('finished')
        if self.fileSender.transfer_id is not None:
            _UnRegisterTransferFunc(self.fileSender.transfer_id)
            _ByTransferID.pop(self.fileSender.transfer_id)
        self.fileSender.transform = None
        del self.fileSender
        self.fileSender = None
        if opened_connections_count() > 200:
            dhnio.Dprint(12, 'transport_tcp.TCPProtocol.finishedTransfer too many opened connections, disconnect with %s' % (str(self.remoteaddress)))
            self.disconnect()
            return
        if self.singleconnection or self.remoteinternalport is None:
            dhnio.Dprint(14, 'transport_tcp.TCPProtocol.finishedTransfer singleconnection=%s remoteinternalport=%s, disconnect with %s' % (
                self.singleconnection, self.remoteinternalport, str(self.remoteaddress)))
            self.transport.disconnect()
            # _SingleConnectionHosts.add(self.remoteaddress[0])
        else:
            reactor.callLater(0, self.processoutbox)

    def transferFailed(self, err):
        global _SendStatusFunc
        global _UnRegisterTransferFunc
        global _ByTransferID
        global _OpenedConnections
        # global _SingleConnectionHosts
        # dhnio.Dprint(14, 'transport_tcp.TCPProtocol.transferFailed NETERROR host=%s file=%s error=%s' % (
        #     str((self.transport.getPeer().host, int(self.transport.getPeer().port))), self.fileSender.filename, str(err.getErrorMessage())))
        try:
            self.fileSender.inputfile.close()
        except:
            dhnio.Dprint (1, 'transport_tcp.TCPProtocol.transferFailed ERROR closing file %s' % self.fileSender.filename)
            dhnio.DprintException()
        if self.fileSender.do_status_report:
            _SendStatusFunc(self.remoteaddress, self.fileSender.filename, 'failed', 'tcp', err, 'transfer failed')
        if self.fileSender.result_defer is not None:
            if not self.fileSender.result_defer.called:
                self.fileSender.result_defer.errback(Exception('failed'))
        if self.fileSender.transfer_id is not None:
            _UnRegisterTransferFunc(self.fileSender.transfer_id)
            _ByTransferID.pop(self.fileSender.transfer_id, None)
        self.fileSender.transform = None
        del self.fileSender
        self.fileSender = None
        if opened_connections_count() > 200:
            dhnio.Dprint(12, 'transport_tcp.TCPProtocol.finishedTransfer too many opened connections, disconnect with %s' % (str(self.remoteaddress)))
            self.disconnect()
            return
        if self.singleconnection or self.remoteinternalport is None:
            dhnio.Dprint(14, 'transport_tcp.TCPProtocol.transferFailed singleconnection=%s remoteinternalport=%s, disconnect with %s' % (
                self.singleconnection, self.remoteinternalport, str(self.remoteaddress)))
            self.transport.disconnect()
            # _SingleConnectionHosts.add(self.remoteaddress[0])
        else:
            reactor.callLater(0, self.processoutbox)

    def shutdown(self, reason=None):
        global _SendStatusFunc
        global _UnRegisterTransferFunc
        global _ByTransferID
        if self.fileReceiver is not None:
            typ = getattr(reason, 'type', None)
            if str(typ).count('ConnectionDone'): 
                self.fileReceiver.lost('finished', reason)
            else:
                self.fileReceiver.lost('failed', reason)
            del self.fileReceiver
            self.fileReceiver = None
        if self.fileSender is not None:
            try:
                self.fileSender.inputfile.close()
            except:
                dhnio.DprintException()
            self.fileSender.file = None
            if self.fileSender.do_status_report:
                _SendStatusFunc(self.remoteaddress, self.fileSender.filename, 'failed', 'tcp', None, 'connection lost')
            if self.fileSender.result_defer is not None:
                if not self.fileSender.result_defer.called:
                    self.fileSender.result_defer.errback(Exception('failed'))
            if self.fileSender.transfer_id is not None:
                _UnRegisterTransferFunc(self.fileSender.transfer_id)
                _ByTransferID.pop(self.fileSender.transfer_id, None)
            self.transport.unregisterProducer()
            del self.fileSender
            self.fileSender = None
        pending_transfer_ids = []
        for transfer_id, proto in _ByTransferID.items():
            if proto == self:
                pending_transfer_ids.append(transfer_id)
        for transfer_id in pending_transfer_ids:
            _UnRegisterTransferFunc(transfer_id)
            _ByTransferID.pop(transfer_id, None)

    
class TCPFactory(protocol.ClientFactory):
    protocol = TCPProtocol
    
    def __init__(self):
        self.pendingoutboxfiles = []

    def __repr__(self):
        return 'TCPFactory' 

    def clientConnectionFailed(self, connector, reason):
        global _SendStatusFunc
        global _StartedConnections
        protocol.ClientFactory.clientConnectionFailed(self, connector, reason)
        destaddress = (connector.getDestination().host, int(connector.getDestination().port))
        for filename, do_status_report, result_defer, description in self.pendingoutboxfiles:
            if do_status_report:
                _SendStatusFunc(destaddress, filename, 'failed', 'tcp', reason, 'connection failed')
            if result_defer is not None:
                if not result_defer.called:
                    result_defer.errback(Exception('failed'))
                    result_defer = None
        _StartedConnections.pop(destaddress, None)
        
    def addoutboxfile(self, filename, do_status_report, result_defer, description):
        self.pendingoutboxfiles.append((filename, do_status_report, result_defer, description))


class TransportTCPXMLRPCServer(abstract.AbstractTransportXMLRPCServer):
    
    def xmlrpc_receive(self, tcpport):
        global _InternalPort
        global _Listener
        try:
            _Listener = reactor.listenTCP(int(tcpport), TCPFactory())
            _InternalPort = int(tcpport)
        except:
            _Listener = None
            dhnio.DprintException()
        return _Listener is not None
    
    def xmlrpc_send(self, filename, host):
        """
        """

    def xmlrpc_sendsingle(self, filename, host):
        """
        """

    def xmlrpc_connect(self, host):
        """
        """

    def xmlrpc_disconnect(self, host):
        """
        """
        
    def xmlrpc_cancel_file_receiving(self, transferID):
        """
        """
        
    def xmlrpc_cancel_file_sending(self, transferID):
        """
        """
        
    def xmlrpc_list_sessions(self):
        """
        """


#------------------------------------------------------------------------------ 

def opened_connections():
    global _OpenedConnections
    return _OpenedConnections


def opened_connections_count():
    global _ConnectionsCounter
    return _ConnectionsCounter


def started_connections():
    global _StartedConnections
    return _StartedConnections


def proxy():
    global _XMLRPCProxy
    return _XMLRPCProxy

#------------------------------------------------------------------------------ 

def interface_transport_started(xmlrpcurl):
    proxy().callRemote('transport_started', 'tcp', xmlrpcurl)
    

def interface_register_file_sending(filename, proto, host):
    proxy().callRemote('register_file_sending', 'tcp', filename, proto, host)

#------------------------------------------------------------------------------ 

def parseCommandLine():
    oparser = optparse.OptionParser()
    # oparser.add_option("-p", "--tcpport", dest="tcpport", type="int", help="specify port to listen for incoming TCP connections")
    oparser.add_option("-r", "--rooturl", dest="rooturl", help="specify XMLRPC server URL address in the main process")
    oparser.add_option("-x", "--xmlrpcport", dest="xmlrpcport", type="int", help="specify port for XMLRPC control")
    oparser.add_option("-d", "--debug", dest="debug", action="store_true", help="redirect output to stderr")
    # oparser.set_default('tcpport', 7771)
    oparser.set_default('rooturl', '')
    oparser.set_default('xmlrpcport', 0)
    oparser.set_default('debug', False)
    (options, args) = oparser.parse_args()
    options.xmlrpcport = int(options.xmlrpcport)
    # options.tcpport = int(options.tcpport)
    return options, args


def init():
    """
    Entry point of the TCP transport plug-in.
    Run a XMLRPC server to wait for commands from the main process.
    """
    global _XMLRPCListener
    global _XMLRPCProxy
    (options, args) = parseCommandLine()
    _XMLRPCListener = reactor.listenTCP(options.xmlrpcport, server.Site(TransportTCPXMLRPCServer()))
    _XMLRPCProxy = xmlrpc.Proxy(options.rooturl)
    reactor.callLater(0, interface_transport_started, "http://localhost:%d" % int(_XMLRPCListener.getHost().port))

if __name__ == "__main__":
    init()
    reactor.run()    
    
    