#!/usr/bin/python
#dhnvertex.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

import os
import sys
import struct
import random
import tempfile
import string
import time


if __name__ == '__main__':
    sys.path.append(os.path.abspath(os.path.join('..','..')))
    sys.path.append(os.path.abspath('..'))
    sys.path.append(os.path.abspath('datahaven'))


try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in dhnvertex.py')


from twisted.internet import protocol
from twisted.internet.task import LoopingCall
from twisted.application import service as service_app
from twisted.internet.defer import Deferred, fail
from twisted.internet.base import DelayedCall
from twisted.protocols.basic import FileSender as fsdr
DelayedCall.debug = False


import vertex.q2qclient as q2qclient
import vertex.q2q as q2q

#------------------------------------------------------------------------------

_Q2QDir = os.path.join('.', '.q2qcerts')
_Service = None
_LogFunc = None
_OpenedPorts = {}

_ReceiveNotifyFunc = None
_SentNotifyFunc = None
_TempFileFunc = None

#------------------------------------------------------------------------------

def init(
         q2qdir=os.path.join('.', '.q2qcerts'),
         logFunc=None,
         receiveNotifyFunc=None,
         sentNotifyFunc=None,
         tempFileFunc=None,
         ):

    global _Q2QDir
    global _LogFunc
    global _ReceiveNotifyFunc
    global _SentNotifyFunc
    global _TempFileFunc

    _Q2QDir = q2qdir
    if logFunc is not None:
        _LogFunc = logFunc
    if receiveNotifyFunc is not None:
        _ReceiveNotifyFunc = receiveNotifyFunc
    if sentNotifyFunc is not None:
        _SentNotifyFunc = sentNotifyFunc
    if tempFileFunc is not None:
        _TempFileFunc = tempFileFunc

    logmsg(4, 'dhnvertex.init ' + _Q2QDir)

#    reactor.addSystemEventTrigger('before', 'shutdown', stopService)
    return startService()


def shutdown():
    logmsg(4, 'dhnvertex.shutdown ')
    return stopService()

def getDefaultPath():
    global _Q2QDir
    return os.path.join(_Q2QDir, 'default-address')

def getFrom():
    defpath = getDefaultPath()
    if os.path.exists(defpath):
        fr = file(defpath).read()
    else:
        fr = getService().getDefaultFrom()
        if fr is None:
            return None
        logmsg(4, 'dhnvertex.getFrom  %s set to default user' % fr)
        f = file(defpath, 'wb')
        f.write(fr)
        f.close()
    return q2q.Q2QAddress.fromString(fr)

def getService():
    global _Service
    global _Q2QDir
    if _Service is None:
        if _Q2QDir is None:
            _Q2QDir = os.path.join('.', '.q2qcerts')
        logmsg(8, 'dhnvertex.getService open local database in: %s' % _Q2QDir)
        _Service = q2qclient.ClientQ2QService(_Q2QDir)
    return _Service

def startService():
    global _DispatcherTask
    logmsg(6, 'dhnvertex.startService')
    svc = getService()
    R = service_app.IService(svc).startService()
    #install our Dispatcher
    prevDisp = svc.dispatcher
    svc.dispatcher = MyPTCPConnectionDispatcher(prevDisp.factory)
    svc.dispatcher._ports.update(prevDisp._ports)
    del prevDisp
    _DispatcherTask = LoopingCall(svc.dispatcher.collect_unused_ports)
    _DispatcherTask.start(10, False)
    return R

def stopService():
    global _Service
    global _DispatcherTask
    logmsg(6, 'dhnvertex.stopService')
    if _DispatcherTask is not None:
        if _DispatcherTask.running:
            _DispatcherTask.stop()
    svc = getService()
    _Service = None
    return service_app.IService(svc).stopService()

def register(user, password):
    logmsg(6, 'dhnvertex.register ' + user)
    newAddress = q2q.Q2QAddress.fromString(user)
    svc = getService()
    D = svc.connectQ2Q(q2q.Q2QAddress("",""),
                       q2q.Q2QAddress(newAddress.domain, "accounts"),
                       'identity-admin',
                       q2qclient.UserAdderFactory(
                           newAddress.resource, password))
    D.addCallback(lambda proto: svc.authorize(newAddress, password))
    return D

class FileReceiver(protocol.Protocol):
    gotLength = False
    def portNumber(self):
        try:
            return self.transport.getHost().logical.port
        except:
            return -1

    def connectionMade(self):
        global _TempFileFunc
        logmsg(12, 'dhnvertex.FileReceiver.connectionMade local port is %d' % self.portNumber())
        if _TempFileFunc is None:
            self.fd, self.filename = tempfile.mkstemp(".dhn-q2q-in")
        else:
            self.fd, self.filename = _TempFileFunc('q2q-in')
        port_update(self.portNumber())

    def dataReceived(self, data):
        if not self.gotLength:
            self.length ,= struct.unpack("!Q", data[:8])
            self.bytesReceived = 0
            data = data[8:]
            self.gotLength = True
            logmsg(12, 'dhnvertex.FileReceiver.dataReceived got length: ' + str(self.length))
        os.write(self.fd, data)
        self.bytesReceived += len(data)
        port_update(self.portNumber())

    def connectionLost(self, reason):
        global _ReceiveNotifyFunc
        logmsg(12, 'dhnvertex.FileReceiver.connectionLost local port is %d' % self.portNumber())
        os.fsync(self.fd)
        os.close(self.fd)
        status = 'finished'
        if self.bytesReceived != self.length:
            status = 'incomplete'
        if _ReceiveNotifyFunc is not None:
            _ReceiveNotifyFunc(self.transport.getPeer(), self.filename, status, reason)
        port_update(self.portNumber(), False)

class FileSender(protocol.Protocol):
    def portNumber(self):
        try:
            return self.transport.getHost().logical.port
        except:
            return -1

    def connectionMade(self):
        logmsg(12, 'dhnvertex.FileSender.connectionMade local port is %d' % self.portNumber())
        self.status = 'started'
        try:
            self.filename = self.factory.filename
            self.file = file(self.filename, 'rb')
            self.file.seek(0, 2)
            self.length = self.file.tell()
            self.file.seek(0)
        except:
            logmsg(1, 'dhnvertex.FileSender.connectionMade ERROR while opening the file. closing!')
            self.transport.loseConnection()
            return
        self.transport.write(struct.pack("!Q", self.length))
        d = fsdr().beginFileTransfer(self.file, self)
        d.addCallback(self.done)
        d.addErrback(self.failed)
        port_update(self.portNumber())

    def done(self, x):
        logmsg(12, 'dhnvertex.FileSender.done ')
        self.status = 'finished'
        self.transport.loseConnection()
        port_update(self.portNumber(), False)

    def failed(self, x):
        logmsg(10, 'dhnvertex.FileSender.failed NETERROR ' + str(x.getErrorMessage()))
        self.status = 'failed'
        self.transport.loseConnection()
        port_update(self.portNumber(), False)

    def dataReceived(self, data):
        logmsg(1, 'dhnvertex.FileSender.dataReceived ERROR THE CLIENT IS GETTING DATA from ' + str(self.transport.getPeer()))

    def registerProducer(self, producer, streaming):
        self.transport.registerProducer(producer, streaming)

    def unregisterProducer(self):
        self.transport.unregisterProducer()

    def write(self, data):
        self.transport.write(data)
        port_update(self.portNumber())

    def connectionLost(self, reason):
        global _SentNotifyFunc
        logmsg(12, 'dhnvertex.FileSender.connectionLost ' + str(reason))
        if _SentNotifyFunc is not None:
            _SentNotifyFunc(self.transport.getPeer(), self.filename, self.status, reason)
        port_update(self.portNumber(), False)

class FileSenderFactory(protocol.ClientFactory):
    protocol = FileSender
    def __init__(self, filename):
        self.filename = filename

class FileReceiverFactory(protocol.Factory):
    protocol = FileReceiver


def receive():
    fromAddress = getFrom()
    if fromAddress is None:
        logmsg(1, 'dhnvertex.receive ERROR no default user found. You must register first!')
        return fail(0)
    logmsg(6, 'dhnvertex.receive ' + str(getFrom()))

    service = getService()
    f = FileReceiverFactory()
    d = service.listenQ2Q( fromAddress, {'file-transfer': f}, 'file-transfer',)
    return d


def send(to_user, filename):
    fromAddress = getFrom()
    if fromAddress is None:
        logmsg(1, 'dhnvertex.send ERROR no default user found. You must register first!')
        return fail(0)

    toAddress = q2q.Q2QAddress.fromString(to_user)
    toDomain = toAddress.domainAddress()

    logmsg(12, 'dhnvertex.send  ['+str(fromAddress)+']->['+str(toAddress)+']')

    service = getService()
    f = FileSenderFactory(filename)
    d = service.connectQ2Q(fromAddress, toAddress, 'file-transfer', f, )
    return d

#-------------------------------------------------------------------------------

def port_update(portNum, InUse=True):
    global _OpenedPorts
    if portNum not in _OpenedPorts.keys():
        return
    if InUse:
        _OpenedPorts[portNum] = time.time()
    else:
        _OpenedPorts[portNum] = 0

class MyPTCPConnectionDispatcher(q2q.PTCPConnectionDispatcher):
    TIMEOUT = 60

    def bindNewPort(self, portNum=0):
        global _OpenedPorts
        new_port = q2q.PTCPConnectionDispatcher.bindNewPort(self, portNum)
        _OpenedPorts[new_port] = time.time()
        logmsg(12, 'dhnvertex.MyPTCPConnectionDispatcher.bindNewPort %d opened_ports=%d' % (new_port, len(_OpenedPorts)))
        return new_port

    def unbindPort(self, portNum):
        global _OpenedPorts
        logmsg(12, 'dhnvertex.MyPTCPConnectionDispatcher.unbindPort %d opened_ports=%d' % (portNum, len(_OpenedPorts)))
        if portNum not in _OpenedPorts.keys():
            logmsg(12, 'dhnvertex.MyPTCPConnectionDispatcher.unbindPort WARNING %d not in the opened ports' % portNum )
            return
        _OpenedPorts.pop(portNum, None)
        q2q.PTCPConnectionDispatcher.unbindPort(self, portNum)

    def collect_unused_ports(self):
        global _OpenedPorts
        logmsg(14, 'dhnvertex.MyPTCPConnectionDispatcher.collect_unused_ports opened=%d' % len(_OpenedPorts))
        removeL = []
        for port in _OpenedPorts.keys():
            if time.time() - _OpenedPorts[port] > self.TIMEOUT:
                removeL.append(port)
                continue

        for port in removeL:
            logmsg(12, 'dhnvertex.MyPTCPConnectionDispatcher.collect_unused_ports want to unbind port %d' % port)
            self.unbindPort(port)

        del removeL

#------------------------------------------------------------------------------

def logmsg(level, msg):
    global _LogFunc
    if _LogFunc is not None:
        _LogFunc(level, msg)
    else:
        print '%s%s' % (' '*level, msg)

def rmdir_recursive(dir):
    #http://mail.python.org/pipermail/python-list/2000-December/060960.html
    """Remove a directory, and all its contents if it is not already empty."""
    for name in os.listdir(dir):
        full_name = os.path.join(dir, name)
        # on Windows, if we don't have write permission we can't remove
        # the file/directory either, so turn that on
        if not os.access(full_name, os.W_OK):
            os.chmod(full_name, 0600)
        if os.path.isdir(full_name):
            rmdir_recursive(full_name)
        else:
            os.remove(full_name)
    os.rmdir(dir)

def rndstr(length):
    return ''.join([random.choice(string.letters+string.digits) for i in range(0,length)])

def clear_local_db(local_db_dir=None):
    global _Q2QDir
    if local_db_dir is not None:
        _Q2QDir = local_db_dir
    try:
        if os.path.isdir(_Q2QDir):
            rmdir_recursive(_Q2QDir)
            logmsg(8, 'dhnvertex.clear_local_db %s removed' % _Q2QDir)
    except:
        logmsg(1, 'dhnvertex.clear_local_db ERROR could not remove %s' % _Q2QDir)

#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------


def _test_receive():
    d = receive()
    d.addCallback(lambda x: logmsg(10, 'register receiveing success. now waiting connections ... '))
    d.addErrback(lambda x: logmsg(10, 'register receiving failed!!!' + str(x)))

def _test_send():
    to = sys.argv[2]
    filename = sys.argv[3]

    timeout = 0
    if len(sys.argv) > 4:
        timeout = int(sys.argv[4])

    def _do_send():
        D = send(to, filename)
        D.addCallback(lambda x: logmsg(10, 'connection success'))
        D.addErrback(lambda x: logmsg(10, ' connection failed!!!: '+str(x)))
        return D

    if timeout == 0:
        _do_send().addBoth(lambda x: reactor.stop())
        return

    t = LoopingCall(_do_send)
    logmsg(4, 'dhnvertex._test_send going to start sending %s in loop' % filename)
    t.start(timeout)

def _test_register():
    u = sys.argv[2]
    password = sys.argv[3]

    def ok(x, u, password):
        logmsg(8, 'registration done success: ' + u)
        reactor.stop()

    def fail(x):
        logmsg(8, 'registration failed: ' + str(x))
        reactor.stop()

    d = register(u, password)
    d.addCallback(ok, u, password)
    d.addErrback(fail)

def _print_help():
    print '\nusage:'
    print 'dhnvertex.py receive'
    print 'dhnvertex.py register <user@server> <password>'
    print 'dhnvertex.py send <to_user@server> <filename> [timeout]'
    print 'dhnvertex.py clear'

def _do_cmd(cmd):
    logmsg(4, 'dhnvertex._do_cmd [%s]' % cmd)
    if cmd == 'send':
        _test_send()

    elif cmd == 'receive':
        _test_receive()

    elif cmd == 'register':
        _test_register()

    elif cmd == 'clear':
        clear_local_db()
        sys.exit(0)

    else:
        _print_help()
        sys.exit(0)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        _print_help()
        sys.exit(0)

    init()

    cmd = sys.argv[1].strip().lower()
    _do_cmd(cmd)

    reactor.run()



