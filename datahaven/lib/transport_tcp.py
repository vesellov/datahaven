#!/usr/bin/python
#transport_tcp.py
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

if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath('..'))

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in transport_tcp.py')

from twisted.internet import task
from twisted.internet import protocol
from twisted.protocols import basic
from twisted.internet.defer import Deferred 
from twisted.internet.error import ConnectionDone

import dhnio
import tmpfile

#------------------------------------------------------------------------------ 

_SendStatusFunc = None
_ReceiveStatusFunc = None
_SendControlFunc = None
_ReceiveControlFunc = None
_RegisterTransferFunc = None
_UnRegisterTransferFunc = None
_ByTransferID = {}
_OpenedConnections = {}
_ConnectionsCounter = 0
_StartedConnections = {}
_SingleConnectionHosts = set()
_InternalPort = 7771
_RedirectionsMap = {}

#------------------------------------------------------------------------------

def init(   sendStatusFunc=None, 
            receiveStatusFunc=None, 
            sendControl=None, 
            receiveControl=None,
            registerTransferFunc=None,
            unregisterTransferFunc=None):
    dhnio.Dprint(4, 'transport_tcp.init')
    global _SendStatusFunc
    global _ReceiveStatusFunc
    global _RegisterTransferFunc
    global _UnRegisterTransferFunc
    if sendStatusFunc is not None:
        _SendStatusFunc = sendStatusFunc
    if receiveStatusFunc is not None:
        _ReceiveStatusFunc = receiveStatusFunc
    if sendControl is not None:
        _SendControlFunc = sendControl 
    if registerTransferFunc is not None:
        _RegisterTransferFunc = registerTransferFunc
    if unregisterTransferFunc is not None:
        _UnRegisterTransferFunc = unregisterTransferFunc
    

def sendsingle(filename, host, port, do_status_report=True, result_defer=None, description=''):
    sender = SingleSendingFactory(
        filename, host, int(port), 
        result_defer=result_defer, 
        do_status_report=do_status_report, 
        send_control_func=None, # (send_control_func or _SendControlFunc),
        description=description)
    reactor.connectTCP(host, int(port), sender)


def send(filename, host, port, do_status_report=True, result_defer=None, description=''):
    global _OpenedConnections
    global _StartedConnections
    global _RedirectionsMap
    remoteaddress = (host, int(port))
#    redirected = _RedirectionsMap.get(remoteaddress, None)
#    if redirected and redirected in _OpenedConnections:
#        if len(_OpenedConnections[redirected]) > 0: 
#            _OpenedConnections[redirected][0].sendfile(filename, do_status_report, result_defer, description)
#            return
    if remoteaddress in _StartedConnections:
        _StartedConnections[remoteaddress].addoutboxfile(filename, do_status_report, result_defer, description)
        return
    if remoteaddress in _OpenedConnections:
        if len(_OpenedConnections[remoteaddress]) > 0: 
            _OpenedConnections[remoteaddress][0].sendfile(filename, do_status_report, result_defer, description)
            return
    conn = TCPFactory()
    conn.addoutboxfile(filename, do_status_report, result_defer, description)
    _StartedConnections[remoteaddress] = conn
    reactor.connectTCP(host, int(port), conn)
    # dhnio.Dprint(14, '    %s' % str(_OpenedConnections))
    # dhnio.Dprint(14, '    %s' % str(_StartedConnections))


def cancel(transferID):
    global _ByTransferID
    inst = _ByTransferID.get(transferID, None)
    if not inst:
        dhnio.Dprint(2, "transport_tcp.cancel ERROR %s is not found" % str(transferID))
        return False
    if isinstance(inst, SingleSendingProtocol):
        inst.fileSender.stopProducing()
        dhnio.Dprint(8, "transport_tcp.cancel sending %s" % str(transferID))
        return True
#    if isinstance(inst, SingleReceiveProtocol):
#        reactor.callLater(0, inst.transport.loseConnection)
#        dhnio.Dprint(8, "transport_tcp.cancel receiving %s" % str(transferID))
#        return True
    if isinstance(inst, TCPProtocol):
        # reactor.callLater(0, inst.transport.loseConnection)
        inst.disconnect()
        # inst.canceltransfer(transferID)
        dhnio.Dprint(8, "transport_tcp.cancel transfer %s - disconnect channel" % str(transferID))
        return True
    dhnio.Dprint(2, "transport_tcp.cancel ERROR incorrect instance for %s" % str(transferID))
    return False
        

def receive(port, receive_control_func=None):
    global _ReceiveControlFunc
    global _InternalPort
    dhnio.Dprint(8, "transport_tcp.receive going to listen on port "+ str(port))

    def _try_receiving(port, count, receive_control_func):
        global _InternalPort
        dhnio.Dprint(8, "transport_tcp.receive count=%d" % count)
        # f = SingleReceiveFactory(receive_control_func)
        f = TCPFactory()
        try:
            mylistener = reactor.listenTCP(int(port), f)
            _InternalPort = int(port)
        except:
            mylistener = None
            dhnio.DprintException()
        return mylistener

    def _loop(port, result, count, receive_control_func):
        if count > 3:
            dhnio.Dprint(1, "transport_tcp.receive WARNING port %s is busy!" % str(port))
            result.callback(None)
            return
        l = _try_receiving(port, count, receive_control_func)
        if l is not None:
            dhnio.Dprint(8, "transport_tcp.receive started on port "+ str(port))
            result.callback(l)
            return
        reactor.callLater(1, _loop, port, result, count+1, receive_control_func)

    res = Deferred()
    _loop(port, res, 0, receive_control_func or _ReceiveControlFunc)
    return res


def disconnect(host, port):
    global _OpenedConnections
    connections = _OpenedConnections.get((str(host), int(port)), [])
    dhnio.Dprint(10, 'transport_tcp.disconnect %s %d, connections=%s' % (host, int(port), connections))
    for connection in connections:
        connection.disconnect()


def disconnect_all():
    global _OpenedConnections
    for peer, connections in _OpenedConnections.items():
        for connection in connections:
            connection.disconnect()
    
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

def single_connection_hosts():
    global _SingleConnectionHosts
    return _SingleConnectionHosts

#------------------------------------------------------------------------------

class SingleFileSender(basic.FileSender):
    
    def __init__(self, protocol):
        self.protocol = protocol
        self.bytesLastRead = 0
    
    def resumeProducing(self):
        #sys.stdout.write('=')
        chunk = ''
        if self.file:
            more_bytes = self.CHUNK_SIZE
            if self.protocol.factory.send_control_func:
                more_bytes = self.protocol.factory.send_control_func(self.bytesLastRead, self.CHUNK_SIZE)
            try:
                chunk = self.file.read(more_bytes)
            except:
                chunk = ''
            self.bytesLastRead = len(chunk)
        if not chunk:
            self.file = None
            self.bytesLastRead = 0
            self.consumer.unregisterProducer()
            if self.deferred:
                self.deferred.callback(self.lastSent)
                self.deferred = None
            return
        if self.transform:
            chunk = self.transform(chunk)
        self.consumer.write(chunk)
        self.lastSent = chunk[-1]


## In Putter "self.factory" references the parent object, so we can
## access arguments like "host", "port", and "filename"
class SingleSendingProtocol(protocol.Protocol):
    fin = None
    sentBytes = 0
    transfer_id = None
    
    def getSentBytes(self):
        return self.sentBytes
    
    def connectionMade(self):
        global _SendStatusFunc
        global _RegisterTransferFunc
        global _ByTransferID
        # dhnio.Dprint(14, 'transport_tcp.SingleSendingProtocol.connectionMade with %s' % str(self.transport.getPeer()))
        if not os.path.isfile(self.factory.filename):
            # dhnio.Dprint(6, 'transport_tcp.SingleSendingProtocol.connectionMade WARNING file %s was not found but we get connected to the %s' % (self.factory.filename, self.factory.host))
            if self.factory.do_status_report:
                _SendStatusFunc(self.transport.getPeer(), self.factory.filename,
                    'failed', 'tcp', None, 'file was not found')
            self.transport.loseConnection()
            if self.factory.result_defer is not None:
                if not self.factory.result_defer.called:
                    self.factory.result_defer.errback(Exception('failed'))
                    self.factory.result_defer = None
            return
        try:
            sz = os.path.getsize(self.factory.filename)
            self.fin = open(self.factory.filename, 'rb')
        except:
            dhnio.DprintException()
            if self.factory.do_status_report:
                _SendStatusFunc(self.transport.getPeer(), self.factory.filename,
                    'failed', 'tcp', None, 'error opening file')
            self.transport.loseConnection()
            if self.factory.result_defer is not None:
                if not self.factory.result_defer.called:
                    self.factory.result_defer.errback(Exception('failed'))
                    self.factory.result_defer = None
            return

        self.fileSender = SingleFileSender(self)
        d = self.fileSender.beginFileTransfer(self.fin, self.transport, self.transformData)
        d.addCallback(self.finishedTransfer)
        d.addErrback(self.transferFailed)
        self.transfer_id = _RegisterTransferFunc(
            'send', (self.transport.getPeer().host, int(self.transport.getPeer().port)), 
            self.getSentBytes, self.factory.filename, sz, self.factory.description)
        _ByTransferID[self.transfer_id] = self

    def transformData(self, data):
        self.sentBytes += len(data)
        return data

    def finishedTransfer(self, result):
        global _SendStatusFunc
        self.transport.loseConnection()
        try:
            self.fin.close()
        except:
            dhnio.Dprint(1, 'transport_tcp.SingleSendingProtocol.finishedTransfer ERROR close file failed')
            dhnio.DprintException()
        if self.factory.do_status_report:
            _SendStatusFunc(self.transport.getPeer(), self.factory.filename, 'finished', 'tcp')
        if self.factory.result_defer is not None:
            if not self.factory.result_defer.called:
                self.factory.result_defer.callback('finished')
                self.factory.result_defer = None
        # dhnio.Dprint(14, 'transport_tcp.SingleSendingProtocol.finishedTransfer host=%s' % (str(self.factory.host)))

    def transferFailed(self, err):
        global _SendStatusFunc
        self.transport.loseConnection()
        try:
            self.fin.close()
        except:
            dhnio.Dprint (1, 'transport_tcp.SingleSendingProtocol.transferFailed ERROR closing file %s' % self.factory.filename)
            dhnio.DprintException()
        if self.factory.do_status_report:
            _SendStatusFunc(self.transport.getPeer(), self.factory.filename, 'failed', 'tcp', err, 'transfer failed')
        if self.factory.result_defer is not None:
            if not self.factory.result_defer.called:
                self.factory.result_defer.errback(Exception('failed'))
                self.factory.result_defer = None
        # dhnio.Dprint(14, 'transport_tcp.SingleSendingProtocol.transferFailed NETERROR host=%s file=%s error=%s' % (str(self.factory.host), str(self.factory.filename), str(err.getErrorMessage())))

    def connectionLost(self, reason):
        global _UnRegisterTransferFunc
        global _ByTransferID
        if self.transfer_id is not None:
            _UnRegisterTransferFunc(self.transfer_id)
            _ByTransferID.pop(self.transfer_id)
        self.transport.loseConnection()
        try:
            self.fin.close()
        except:
            dhnio.DprintException()
        # dhnio.Dprint(14, 'transport_tcp.SingleSendingProtocol.connectionLost with %s' % str(self.transport.getPeer()))

class SingleSendingFactory(protocol.ClientFactory):
    def __init__(self, filename, host, port, result_defer=None, do_status_report=True, send_control_func=None, description=''):
        self.filename = filename
        self.host = host
        self.port = port
        self.protocol = SingleSendingProtocol
        self.result_defer = result_defer
        self.do_status_report = do_status_report
        self.send_control_func = send_control_func # callback which reads from the file
        self.description = description 

    def clientConnectionFailed(self, connector, reason):
        global _SendStatusFunc
        protocol.ClientFactory.clientConnectionFailed(self, connector, reason)
        if self.do_status_report:
            _SendStatusFunc(connector.getDestination(),
                self.filename, 'failed', 'tcp', reason, 'connection failed')
        if self.result_defer is not None:
            if not self.result_defer.called:
                self.result_defer.errback(Exception('failed'))
                self.result_defer = None
        name = str(reason.type.__name__)
        # dhnio.Dprint(14, 'transport_tcp.SingleSendingFactory.clientConnectionFailed NETERROR [%s] with %s:%s' % (
        #     name, connector.getDestination().host, connector.getDestination().port,))

#------------------------------------------------------------------------------

#class SingleReceiveProtocol(protocol.Protocol):
#    def getReceivedBytes(self):
#        return self.receivedBytes
#    
#    def connectionMade(self):
#        global _RegisterTransferFunc
#        global _ByTransferID
#        self.filename = None     # string with path/filename
#        self.fd = None           # integer file descriptor like os.open() returns
#        self.peer = None
#        self.receivedBytes = 0
#        self.transfer_id = None
#        self.blocked = False
#        self.resume_receiving_task = None
#        if self.peer is None:
#            self.peer = self.transport.getPeer()
#        else:
#            if self.peer != self.transport.getPeer():
#                raise Exception("transport_tcp.SingleReceiveProtocol.connectionMade NETERROR thought we had one object per connection")
#        try:
#            from transport_control import black_IPs_dict
#            if self.peer.host in black_IPs_dict().keys() or '.'.join(self.peer.host.split('.')[:-1]) in black_IPs_dict().keys():
#                # dhnio.Dprint(12, 'transport_tcp.SingleReceiveProtocol.connectionMade from BLACK IP: %s, %s' % (str(self.peer.host), str(black_IPs_dict()[self.peer.host])) )
#                self.blocked = True
#                self.transport.loseConnection()
#                return
#        except:
#            pass
#        if self.filename is None:
#            self.fd, self.filename = tmpfile.make("tcp-in")
#        else:   
#            raise Exception("transport_tcp.SingleReceiveProtocol.connectionMade has second connection in same object")
#        if self.fd is None:
#            raise Exception("transport_tcp.SingleReceiveProtocol.connectionMade error opening temporary file")
#        self.transfer_id = _RegisterTransferFunc(
#            'receive', (self.transport.getPeer().host, int(self.transport.getPeer().port)), 
#            self.getReceivedBytes, self.filename, -1)
#        _ByTransferID[self.transfer_id] = self
#
#    def dataReceived(self, data):
#        if self.blocked:
#            return
#        if self.fd is None:
#            raise Exception('transport_tcp.SingleReceiveProtocol.dataReceived from %s but file was not opened' % str(self.peer))
#        amount = len(data)
#        os.write(self.fd, data)
#        self.receivedBytes += amount
#        if self.factory.receive_control_func is not None:
#            seconds_pause = self.factory.receive_control_func(len(data))
#            if seconds_pause > 0:
#                self.transport.pauseProducing()
#                self.resume_receiving_task = reactor.callLater(seconds_pause, self.resumeReceiving)
#
#    def resumeReceiving(self):
#        self.resume_receiving_task = None
#        self.transport.resumeProducing()
#
#    def connectionLost(self, reason):
#        global _ReceiveStatusFunc
#        global _UnRegisterTransferFunc
#        global _ByTransferID
#        if self.resume_receiving_task:
#            self.resume_receiving_task.cancel()
#        if self.transfer_id is not None:
#            _UnRegisterTransferFunc(self.transfer_id)
#            _ByTransferID.pop(self.transfer_id)
#        # dhnio.Dprint(6, 'transport_tcp.SingleReceiveProtocol.connectionLost with %s' % str(self.transport.getPeer()))
#        if self.fd is not None:
#            try:
#                os.close(self.fd)
#            except:
#                dhnio.DprintException()
#        if self.filename is not None:
#            _ReceiveStatusFunc(self.filename, "finished", 'tcp', self.transport.getPeer(), reason)


#class SingleReceiveFactory(protocol.ServerFactory):
#    protocol = SingleReceiveProtocol
#    
#    def __init__(self, receive_control_func):
#        self.receive_control_func = receive_control_func
        
#    def buildProtocol(self, addr):
#        p = SingleReceiveProtocol()
#        p.factory = self
#        return p

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
        # dhnio.Dprint(14, 'transport_tcp.TCPProtocol.clientConnectionFailed opened NETERROR [%s] with %s:%s, id=%d' % (
        #     str(reason.type.__name__), connector.getDestination().host, connector.getDestination().port, id(self.pendingoutboxfiles)))
        _StartedConnections.pop(destaddress, None)
        
    def addoutboxfile(self, filename, do_status_report, result_defer, description):
        self.pendingoutboxfiles.append((filename, do_status_report, result_defer, description))

#------------------------------------------------------------------------------ 

def SendStatusFuncDefault(host, filename, status, proto='', error=None, message=''):
    try:
        from transport_control import sendStatusReport
        sendStatusReport(host, filename, status, proto, error, message)
    except:
        dhnio.DprintException()

def ReceiveStatusFuncDefault(filename, status, proto='', host=None, error=None, message=''):
    try:
        from transport_control import receiveStatusReport
        receiveStatusReport(filename, status, proto, host, error, message)
    except:
        dhnio.DprintException()

def SendControlFuncDefault(prev_read, chunk_size):
    return chunk_size

def ReceiveControlFuncDefault(new_data_size):
    return 0

def RegisterTransferFuncDefault(send_or_receive=None, remote_address=None, callback=None, filename=None, size=None, description='', transfer_id=None):
    try:
        from transport_control import register_transfer
        return register_transfer('tcp', send_or_receive, remote_address, callback, filename, size, description, transfer_id)
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

#------------------------------------------------------------------------------ 

_SendStatusFunc = SendStatusFuncDefault
_ReceiveStatusFunc = ReceiveStatusFuncDefault
_SendControlFunc = SendControlFuncDefault
_ReceiveControlFunc = ReceiveControlFuncDefault
_RegisterTransferFunc = RegisterTransferFuncDefault
_UnRegisterTransferFunc = UnRegisterTransferFuncDefault

#-------------------------------------------------------------------------------

def usage():
        print '''
args:
transport_tcp.py receive [port]                                        to receive
transport_tcp.py send [host] [port] [file name]                        to send a file
transport_tcp.py send [host] [port] [file name] [interval]             to start sending continuously
transport_tcp.py opensend [myport] [peerhost] [peerport] [file name]   send and keep connection opened
'''



#def mytest():
#    dhnio.SetDebug(18)
#
#    filename = "transport_tcp.pyc"              # just some file to send
###    host = "work.offshore.ai"
###    host = "89.223.30.208"
#    host = 'localhost'
#    port = 7771
#
#    if len(sys.argv) == 4:
#        send(sys.argv[3], sys.argv[1], sys.argv[2])
#    elif len(sys.argv) == 2:
#        r = receive(sys.argv[1])
#        print r
#    else:
#        usage()
#        sys.exit()
#    reactor.run()

#bytes_counter = 0
#time_counter = time.time()
#count_period = 1
#current_chunk = 1

def _my_receive_control(new_data_size):
    try:
        from transport_control import ReceiveTrafficControl
        return ReceiveTrafficControl(new_data_size)
    except:
        dhnio.DprintException()
        return 0
    
def _my_send_control(prev_read_size, chunk_size):
    try:
        from transport_control import SendTrafficControl
        return SendTrafficControl(prev_read_size, chunk_size)
    except:
        dhnio.DprintException()
        return chunk_size

def _my_monitor():
#    import transport_control
#    src = ''
#    for address in transport_control._LiveTransfers.keys():
#        for obj in transport_control._LiveTransfers[address]['send']:
#            src += '%d to %s, ' % (obj.sentBytes, str(address))
#        for obj in transport_control._LiveTransfers[address]['receive']:
#            src += '%d from %s, ' % (obj.receivedBytes, str(address))
#    print '>>>', src
    print _OpenedConnections, _StartedConnections
    reactor.callLater(5, _my_monitor)

if __name__ == "__main__":
    #import datahaven.p2p.memdebug as memdebug
    #memdebug.start(8080)
    dhnio.init()
    dhnio.SetDebug(16)
    dhnio.LifeBegins()

    from twisted.internet.defer import setDebugging
    setDebugging(True)

    _my_monitor()

    def _test_cancel():
        import transport_control as tc
        for t in tc.current_transfers():
            cancel(t.transfer_id)

    if len(sys.argv) < 2:
        usage()
        sys.exit(1)
    
    cmd = sys.argv[1].lower().strip()

    if cmd == 'receive':
        r = receive(sys.argv[2])
        reactor.callLater(5, disconnect, '127.0.0.1', 6661)
        reactor.run()
    elif cmd == 'send':
        _SendStatusFunc = lambda host, filename, status, proto='', error=None, message='': \
            sys.stdout.write('                        %s to %s is %s\n' % (filename, host, status))
        if len(sys.argv) < 6:
            send(sys.argv[4], sys.argv[2], sys.argv[3]) # .addBoth(lambda x: dhnio.Dprint(2, 'RESULT:%s'%str(x)))
            # reactor.callLater(10, _test_cancel)
        else:
            l = task.LoopingCall(send, sys.argv[4], sys.argv[2], sys.argv[3])
            l.start(float(sys.argv[5]))
            reactor.callLater(10, _test_cancel)
            reactor.callLater(20, _test_cancel)
        reactor.run()
    elif cmd == 'opensend':
        r = receive(sys.argv[2])
        _SendStatusFunc = lambda host, filename, status, proto='', error=None, message='': \
            sys.stdout.write('                        %s to %s is %s\n' % (filename, host, status))
        reactor.callLater(1, send, sys.argv[5], sys.argv[3], sys.argv[4]) # .addBoth(lambda x: dhnio.Dprint(2, 'RESULT:%s'%str(x)))
        # reactor.callLater(5, disconnect, sys.argv[3], sys.argv[4])
        reactor.run()
    else:
        usage()

