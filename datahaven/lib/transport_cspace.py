#!/usr/bin/python
#transport_cspace.py
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
import xmlrpclib
import subprocess
import base64
import random
import optparse

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in transport_cspace.py')

from twisted.internet.defer import Deferred, succeed, fail
from twisted.web import resource
from twisted.web import server
from twisted.internet import protocol
from twisted.internet import interfaces
from zope.interface import implements

import dhnio
import misc
import settings
import tmpfile
import nonblocking
import automat

#------------------------------------------------------------------------------ 

_Debug = False
_BaseDir = '.'
_Controller = None
_CSpaceProcess = None
_Listener = None
_OutgoingFilesDict = {}
_OutgoingQueue = []
_SendingDelay = 0.01
_LastServiceRestartTime = 0
_OpenedStreams = []

_SendStatusFunc = None
_ReceiveStatusFunc = None
_RegisterTransferFunc = None
_UnRegisterTransferFunc = None
_ContactStatusNotifyFunc = None

#------------------------------------------------------------------------------

def init(baseDir=None):
    global _Controller
    global _BaseDir
    global _SendStatusFunc 
    global _ReceiveStatusFunc 
    global _RegisterTransferFunc 
    global _UnRegisterTransferFunc 
    dhnio.Dprint(6, 'transport_cspace.init')
    if _Controller is not None:
        return succeed('already started')
    if baseDir:
        _BaseDir = baseDir 
    _Controller = CSpaceServiceController()
    resultDefer = Deferred()
    A('init', resultDefer)
    return resultDefer


def shutdown():
    global _Controller
    if not _Controller:
        dhnio.Dprint(6, 'transport_cspace.shutdown transport is not started, skip')
        return succeed(0)
    dhnio.Dprint(6, 'transport_cspace.shutdown sending event "shutdown" to the state machine')
    d = Deferred()
    A('shutdown', d)
    return d


def shutdown_final(arg=None):
    global _Controller
    global _Listener
    global _OutgoingFilesDict
    global _OutgoingQueue
    global _TransportCspace
    dhnio.Dprint(6, 'transport_cspace.shutdown_final')
    if _Controller is not None:
        dhnio.Dprint(6, 'transport_cspace.shutdown_final stopping controller')
        _Controller.stop()
        _Controller = None
    if _Listener is not None:
        dhnio.Dprint(6, 'transport_cspace.shutdown_final destroying pseudo listener')
        del _Listener
        _Listener = None
    _OutgoingFilesDict.clear()
    _OutgoingQueue = []
    kill()
    del _TransportCspace
    _TransportCspace = None
    if arg and isinstance(arg, Deferred):
        arg.callback(1)


def run(params=[], process_finished_callback=None):
    global _BaseDir
    global _CSpaceProcess
    if _CSpaceProcess is not None:
        return None
    if dhnio.isFrozen() and dhnio.Windows():
        progpath = os.path.abspath(os.path.join(_BaseDir, 'dhnet.exe'))
        executable = progpath
        cmdargs = [progpath]
        cmdargs.extend(params)
    else:
        progpath = os.path.abspath(os.path.join(_BaseDir, 'dhnet.py'))
        executable = sys.executable
        cmdargs = [executable, progpath]
        cmdargs.extend(params)
    if not os.path.isfile(executable):
        dhnio.Dprint(1, 'transport_cspace.run ERROR %s not found' % executable)
        return None
    if not os.path.isfile(progpath):
        dhnio.Dprint(1, 'transport_cspace.run ERROR %s not found' % progpath)
        return None
    dhnio.Dprint(6, 'transport_cspace.run execute: "%s"' % (' '.join(cmdargs)))

    if dhnio.Windows():
        from twisted.internet import _dumbwin32proc
        real_CreateProcess = _dumbwin32proc.win32process.CreateProcess
        def fake_createprocess(_appName, _commandLine, _processAttributes,
                            _threadAttributes, _bInheritHandles, creationFlags,
                            _newEnvironment, _currentDirectory, startupinfo):
            import win32con
            flags = win32con.CREATE_NO_WINDOW 
            return real_CreateProcess(_appName, _commandLine,
                            _processAttributes, _threadAttributes,
                            _bInheritHandles, flags, _newEnvironment,
                            _currentDirectory, startupinfo)        
        setattr(_dumbwin32proc.win32process, 'CreateProcess', fake_createprocess)
    try:
        _CSpaceProcess = reactor.spawnProcess(CSpaceServiceProtocol(process_finished_callback), executable, cmdargs, path=_BaseDir)
    except:
        dhnio.Dprint(1, 'transport_cspace.run ERROR executing: %s' % str(cmdargs))
        dhnio.DprintException()
        return None
    
    if dhnio.Windows():
        setattr(_dumbwin32proc.win32process, 'CreateProcess', real_CreateProcess)

    dhnio.Dprint(6, 'transport_cspace.run pid=%d' % _CSpaceProcess.pid)
    return _CSpaceProcess


def kill():
    global _CSpaceProcess
    if _CSpaceProcess is not None:
        try:
            _CSpaceProcess.signalProcess('KILL')
            # _CSpaceProcess.kill()
            dhnio.Dprint(6, 'transport_cspace.kill finished "dhnet" process')
        except:
            pass
    del _CSpaceProcess
    _CSpaceProcess = None
    killed = False
    for pid in dhnio.find_process(['dhnet.']): 
        dhnio.kill_process(pid)
        dhnio.Dprint(6, 'transport_cspace.kill pid %d' % pid)
        killed = True
    if killed:
        pidpath = getPIDpath()
        if os.path.isfile(pidpath):
            try:
                os.remove(pidpath)
                dhnio.Dprint(6, 'transport_cspace.kill %s removed' % pidpath)
            except:
                pass

    
def alive():
    global _CSpaceProcess
    if _CSpaceProcess is None:
        return False
    try:
        pid = _CSpaceProcess.pid
    except:
        return False
    if pid == 0:
        return False
    proclist = dhnio.find_process(['dhnet.'])
    if len(proclist) == 0:
        return False
    if pid not in proclist:
        return False 
    return True
    

def registered():    
    exists = [ os.path.isfile(settings.CSpaceRememberKeyFile()),
               os.path.isfile(settings.CSpaceSavedProfileFile()),
               os.path.isfile(settings.CSpaceSavedPasswordFile()),]
    if False in exists:
        return False
    cur_profile_name = dhnio.ReadTextFile(settings.CSpaceSavedProfileFile())
    cur_profile_dir = os.path.join(settings.CSpaceProfilesDir(), cur_profile_name.strip('"'))
    if not os.path.isdir(cur_profile_dir):
        return False
    exists = [os.path.isfile(os.path.join(cur_profile_dir, 'PrivateKey')),
              os.path.isfile(os.path.join(cur_profile_dir, 'KeyID')),]
    if False in exists:
        return False
    return True


def keyID():
    if not registered():
        return None
    cur_profile_name = dhnio.ReadTextFile(settings.CSpaceSavedProfileFile())
    cur_profile_dir = os.path.join(settings.CSpaceProfilesDir(), cur_profile_name.strip('"'))
    return dhnio.ReadTextFile(os.path.join(cur_profile_dir, 'KeyID'))
    

def control():
    global _Controller
    if _Controller is None:
        init()
    return _Controller


def zero():
    return 0


def getfilesize(sz):
    def _sz():
        return sz
    return _sz


def send(filename, keyid, description=''):
    if not os.path.isfile(filename):
        sendingReport(keyid, filename, 'failed', None, 'file not exist')
        return 
    if not os.access(filename, os.R_OK):
        sendingReport(keyid, filename, 'failed', None, 'file can not be read')
        return 
    if A().state is not 'ONLINE':
        sendingReport(keyid, filename, 'failed', None, 'current state is %s' % A().state)
        return
    try:
        size = os.path.getsize(filename)
    except:
        # dhnio.DprintException()
        sendingReport(keyid, filename, 'failed', None, 'file read error')
        return
    transferID = registerTransfer('send', keyid, filename, size, getfilesize(size), description)
    control().send(keyid, filename, transferID, description)


def cancel(transferID):
    control().cancel(transferID)

#------------------------------------------------------------------------------ 

def SetOpenedStreamsNumber(num):
    control().set_opened_streams(num)
    
def opened_opened_streams_list():
    global _OpenedStreams
    return _OpenedStreams

#------------------------------------------------------------------------------ 

def sendingReport(keyid, filename, status, error=None, message=''):
    global _SendStatusFunc
    if _SendStatusFunc:
        return _SendStatusFunc(keyid, filename, status, 'cspace', error, message)
    dhnio.Dprint(6, 'transport_cspace.sendingReport %s to %s is %s, %s' % (filename, keyid, status, message))


def receivingReport(keyID, filename, status, error=None, message=''):
    global _ReceiveStatusFunc
    if _ReceiveStatusFunc:
        return _ReceiveStatusFunc(filename, status, 'cspace', keyID, error, message)
    dhnio.Dprint(6, 'transport_cspace.receivingReport %s from %s is %s' % (filename, keyID, status))


def registerTransfer(send_or_receive, keyid, filename, size, callback, description):
    global _RegisterTransferFunc
    if _RegisterTransferFunc:
        return _RegisterTransferFunc(send_or_receive, keyid, callback, filename, size, description)
    return 1


def unregisterTransfer(transfer_id):
    global _UnRegisterTransferFunc
    if _UnRegisterTransferFunc:
        return _UnRegisterTransferFunc(transfer_id)
    return True


def serviceResponse(command, data):
    global _ContactStatusNotifyFunc
    global _OpenedStreams
    # dhnio.Dprint(8, 'transport_cspace.callback %s %s' % (command, str(data)))
    if command == 'sent':
        try:
            (keyid, filename, transferID, status, err, msg) = data
            if transferID:
                transferID = int(transferID)
            msg = msg.strip('"')
        except:
            dhnio.Dprint(2, 'transport_cspace.serviceResponse ERROR data=%s' % str(data))
            dhnio.DprintException()
            return
        sendingReport(keyid, filename, status, err, msg)
        if transferID:
            unregisterTransfer(transferID)
        else:
            dhnio.Dprint(2, 'transport_cspace.serviceResponse ERROR transferID is None: %s' % str(data))
            
    elif command == 'receive':
        try:
            (keyid, filename, status, err, msg) = data
            msg = msg.strip('"')
        except:
            dhnio.Dprint(2, 'transport_cspace.serviceResponse ERROR data=%s' % str(data))
            dhnio.DprintException()
            return
        size = 1
        if os.path.isfile(filename):
            try:
                size = os.path.getsize(filename)
            except:
                dhnio.DprintException()
        transferID = registerTransfer('receive', keyid, filename, size, getfilesize(size), '')
        unregisterTransfer(transferID)
        receivingReport(keyid, filename, status, err, msg)
        
    elif command == 'contact':
        if _ContactStatusNotifyFunc:
            try:
                contact, status = data
            except:
                dhnio.Dprint(2, 'transport_cspace.serviceResponse ERROR data=%s' % str(data))
                dhnio.DprintException()
                return
            _ContactStatusNotifyFunc(contact, status)
    
    elif command == 'streams':
        try:
            _OpenedStreams, = data 
        except:
            dhnio.Dprint(2, 'transport_cspace.serviceResponse ERROR data=%s' % str(data))
            dhnio.DprintException()
            return
    else:
        if _Controller:
            A(command, data) 


def getPIDpath(appName="CSpace"):
    pidfile = "%s.run" % appName
    pidpath = settings.CSpaceDir()
    if not os.path.exists(pidpath):
        os.makedirs(pidpath)
    pidpath = os.path.join(pidpath, pidfile)
    return pidpath


def pushFileName(SendToKeyID, filename):
    global _OutgoingQueue
    global _OutgoingFilesDict
    if not _OutgoingFilesDict.has_key(SendToKeyID):
        _OutgoingFilesDict[SendToKeyID] = list()
    _OutgoingFilesDict[SendToKeyID].append(filename)
    _OutgoingQueue.append(SendToKeyID)


def popFileName(SendToKeyID):
    global _OutgoingFilesDict
    if not _OutgoingFilesDict.has_key(SendToKeyID):
        return ''
    try:
        return _OutgoingFilesDict[SendToKeyID].pop(0)
    except:
        return ''


def readSendingQueue():
    global _OutgoingQueue
    if len(_OutgoingQueue) == 0:
        return None
    return _OutgoingQueue.pop(0)


def setBaseDir(baseDir):
    global _BaseDir
    _BaseDir = baseDir    

#------------------------------------------------------------------------------ 

_TransportCspace = None
def A(event=None, arg=None):
    global _TransportCspace
    if event == 'shutdown' and _TransportCspace is None:
        shutdown_final(arg)
        return None
    if _TransportCspace is None:
        # set automat name and starting state here
        _TransportCspace = TransportCspace('transport_cspace', 'AT_STARTUP', 6)
    if event is not None:
        _TransportCspace.automat(event, arg)
    return _TransportCspace

# DataHaven.NET transport_cspace() Automat
class TransportCspace(automat.Automat):
    timers = { 'timer-1min': (60, ['OFFLINE']), }
    resultDefer = None
    shutdownDefer = None
    def state_changed(self, oldstate, newstate):
        if newstate in ['ONLINE', 'OFFLINE'] and self.resultDefer is not None and not self.resultDefer.called:
            self.resultDefer.callback(newstate.lower())
            self.resultDefer = None
    def A(self, event, arg):
        #---AT_STARTUP---
        if self.state is 'AT_STARTUP':
            if event == 'init' and not self.isRegistered(arg) :
                self.state = 'REGISTER'
                self.doRegister(arg)
            elif event == 'init' and self.isRegistered(arg) :
                self.state = 'SERVICE'
                self.doExecute(arg)
        #---SERVICE---
        elif self.state is 'SERVICE':
            if event == 'service-started' :
                self.state = 'CONNECTION'
                self.doConnect(arg)
            elif event == 'execute-error' or event == 'shutdown' :
                self.state = 'SHUTDOWN'
                self.doShutdown(arg)
        #---CONNECTION---
        elif self.state is 'CONNECTION':
            if event == 'online' :
                self.state = 'ONLINE'
            elif event == 'offline' :
                self.state = 'OFFLINE'
            elif event == 'connect-error' or event == 'shutdown' :
                self.state = 'SHUTDOWN'
                self.doShutdown(arg)
        #---ONLINE---
        elif self.state is 'ONLINE':
            if event == 'offline' :
                self.state = 'OFFLINE'
            elif event == 'shutdown' :
                self.state = 'DISCONNECTION'
                self.doDisconnect(arg)
            elif event == 'restart' :
                self.state = 'SERVICE'
                self.doRestart(arg)
        #---OFFLINE---
        elif self.state is 'OFFLINE':
            if event == 'shutdown' :
                self.state = 'SHUTDOWN'
                self.doShutdown(arg)
            elif event == 'timer-1min' :
                self.state = 'CONNECTION'
                self.doConnect(arg)
            elif event == 'online' :
                self.state = 'ONLINE'
                self.doProcessSending(arg)
            elif event == 'restart' :
                self.state = 'SERVICE'
                self.doRestart(arg)
        #---REGISTER---
        elif self.state is 'REGISTER':
            if event == 'register-failed' :
                self.state = 'SHUTDOWN'
                self.doShutdown(arg)
            elif event == 'registered' :
                self.state = 'SERVICE'
                self.doExecute(arg)
        #---SHUTDOWN---
        elif self.state is 'SHUTDOWN':
            pass
        #---DISCONNECTION---
        elif self.state is 'DISCONNECTION':
            if event == 'offline' or event == 'timer-1min' :
                self.state = 'SHUTDOWN'
                self.doShutdown(arg)

    def isRegistered(self, arg):
        return registered()

    def doExecute(self, arg):
        global _Debug
        dhnio.Dprint(6, 'transport_cspace.doExecute')
        if arg and self.resultDefer is None:
            self.resultDefer = arg
        kill()
        args = ['--logfile', '"%s"' % settings.CSpaceLogFilename(), 
                '--homedir', '"%s"' % settings.CSpaceDir(),
                '--tmpdir', '"%s"' % os.path.join(settings.TempDir(), 'cspace-in'),
                '--parentpid', '%s' % str(os.getpid()),]
        if _Debug:
            args.insert(0, '--debug')
        if run(params=args) is None:
            self.event('execute-error')
            self.resultDefer.callback('execute-error')

    def doShutdown(self, arg):
        automat.objects().pop(self.index)
        d = self.shutdownDefer
        if d is None:
            d = arg
        shutdown_final(d)

    def doConnect(self, arg):
        dhnio.Dprint(6, 'transport_cspace.doConnect keyID=%s' % keyID())
        control().online()

    def doDisconnect(self, arg):
        dhnio.Dprint(6, 'transport_cspace.doDisconnect arg=%s' % str(arg))
        self.shutdownDefer = arg
        if not control().offline():
            self.automat('offline')

    def doProcessSending(self, arg):
        dhnio.Dprint(6, 'transport_cspace.doProcessSending')

    def doRegister(self, arg):
        global _Debug
        dhnio.Dprint(6, 'transport_cspace.doRegister')
        self.resultDefer = arg
        kill()
        username = dhnio.ReadTextFile(settings.UserNameFilename()).strip() 
        if not username:
            username = 'dhn' + time.strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(os.urandom(12))
        settings.setCSpaceUserName(username)
        settings.setCSpacePassword(password)
        def _process_finished(result):
            if not registered():
                self.event('register-failed')
                self.resultDefer.callback('register-failed')
                return
            self.event('registered')
        def _register(username, password):
            args = [ '--register', username, password,
                     '--logfile', '"%s"' % settings.CSpaceLogFilename(),  
                     '--homedir', '"%s"' % settings.CSpaceDir(),
                     '--tmpdir', '"%s"' % os.path.join(settings.TempDir(), 'cspace-in'), 
                     '--parentpid', '%s' % str(os.getpid())]
            if _Debug:
                args.insert(0, '--debug')
            if run(process_finished_callback=_process_finished, params=args) is None:
                self.event('register-failed')
                self.resultDefer.callback('register-failed')
                return
        reactor.callLater(0, _register, username, password)

    def doRestart(self, arg):
        global _Debug
        global _Controller
        dhnio.Dprint(6, 'transport_cspace.doRestart')
        if arg and self.resultDefer is None:
            self.resultDefer = arg
        kill()
        args = ['--logfile', '"%s"' % settings.CSpaceLogFilename(), 
                '--homedir', '"%s"' % settings.CSpaceDir(),
                '--tmpdir', '"%s"' % os.path.join(settings.TempDir(), 'cspace-in'),
                '--parentpid', '%s' % str(os.getpid()),]
        if _Debug:
            args.insert(0, '--debug')
        if run(params=args) is None:
            self.event('execute-error')
            self.resultDefer.callback('execute-error')
        _Controller._server = None

#------------------------------------------------------------------------------ 

def RestartService():
    global _LastServiceRestartTime
    if time.time() - _LastServiceRestartTime < 60*10:
        return
    A('restart')
    _LastServiceRestartTime = time.time()

#------------------------------------------------------------------------------ 

class CSpaceServiceController():
    def __init__(self):
        self._server = None

    def _getserviceinfo(self):
        pidpath = getPIDpath()
        if not os.path.exists(pidpath) or not os.path.isfile(pidpath):
            return None, None, None
        fInfo = open(pidpath)
        pid = int(fInfo.readline())
        port = int(fInfo.readline())
        applet = int(fInfo.readline())
        return pid, port, applet

    def _getserver(self, netserver=False):
        if self._server is None:
            pid, port, applet = self._getserviceinfo()
            if pid is None:
                return None
            url = "http://localhost:%i/" % port
            dhnio.Dprint(6, 'transport_cspace._getserver connecting to XMLRPC server on %s' % url)
            self._server = xmlrpclib.Server(url, allow_none=True,)
        return self._server
    
    def online(self):
        server = self._getserver()
        if server is not None:
            try:
                result = server.online()
                dhnio.Dprint(6, 'transport_cspace.online response: %s' % str(result))
                return True
            except:
                dhnio.Dprint(6, 'transport_cspace.online ERROR connecting to XMLRPC')
                RestartService()
                return
        else:
            dhnio.Dprint(6, "transport_cspace.online ERROR service not started")
            RestartService()
        return False
    
    def offline(self):
        server = self._getserver()
        if server is not None:
            try:
                result = server.offline()
                dhnio.Dprint(6, 'transport_cspace.offline response: %s' % str(result))
                return True
            except:
                dhnio.Dprint(6, 'transport_cspace.offline ERROR connecting to XMLRPC')
                RestartService()
        else:
            dhnio.Dprint(6, "transport_cspace.offline ERROR service not started")
        return False

    def add(self, buddy, keyid):
        server = self._getserver()
        if server is not None:
            try:
                result = server.add(buddy, keyid)
                dhnio.Dprint(6, 'transport_cspace.add response: %s' % str(result))
                return True
            except:
                dhnio.Dprint(6, 'transport_cspace.add ERROR connecting to XMLRPC')
                RestartService()
        else:
            dhnio.Dprint(6, "transport_cspace.add ERROR service not started")
            RestartService()
        return False

    def remove(self, buddy):
        server = self._getserver()
        if server is not None:
            try:
                result = server.remove(buddy)
                dhnio.Dprint(6, 'transport_cspace.remove response: %s' % str(result))
                return True
            except:
                dhnio.Dprint(6, 'transport_cspace.remove ERROR connecting to XMLRPC')
                RestartService()
        else:
            dhnio.Dprint(6, "transport_cspace.remove ERROR service not started")
            RestartService()
        return False

    def probe(self, buddy):
        server = self._getserver()
        if server is not None:
            try:
                result = server.probe(buddy)
                dhnio.Dprint(6, 'transport_cspace.probe response: %s' % str(result))
                return True
            except:
                dhnio.Dprint(6, 'transport_cspace.probe ERROR connecting to XMLRPC')
                RestartService()
        else:
            dhnio.Dprint(6, "transport_cspace.probe ERROR service not started")
            RestartService()
        return False

    def send(self, keyID, filename, transferID, description):
        server = self._getserver()
        if server is not None:
            try:
                server.send(str(keyID), unicode(filename).encode('utf-8'), transferID, description)
                # dhnio.Dprint(6, 'transport_cspace.send response: %s' % str(result))
                return True
            except:
                dhnio.Dprint(6, 'transport_cspace.send ERROR connecting to XMLRPC')
                unregisterTransfer(transferID)
                sendingReport(keyID, filename, 'failed', None, 'failed connect to XMLRPC')
                RestartService()
        else:
            dhnio.Dprint(6, "transport_cspace.send ERROR service not started")
            unregisterTransfer(transferID)
            sendingReport(keyID, filename, 'failed', None, 'XMLRPC is offfailed connect to XMLRPC')
            RestartService()
        return False

    def cancel(self, transferID):
        server = self._getserver()
        if server is not None:
            try:
                server.cancel(transferID)
                return True
            except:
                dhnio.Dprint(6, 'transport_cspace.cancel ERROR connecting to XMLRPC')
                unregisterTransfer(transferID)
                RestartService()
        else:
            dhnio.Dprint(6, "transport_cspace.cancel ERROR service not started")
            RestartService()
        return False
        
    def set_opened_streams(self, num):
        server = self._getserver()
        if server is not None:
            try:
                server.set_opened_streams(num)
                dhnio.Dprint(6, 'transport_cspace.set_opened_streams %s' % str(num))
                return True
            except:
                dhnio.Dprint(6, 'transport_cspace.set_opened_streams ERROR connecting to XMLRPC')
                RestartService()
        else:
            dhnio.Dprint(6, "transport_cspace.set_opened_streams ERROR service not started")
            RestartService()
        return False

#    def set_sending_streams(self, num):
#        server = self._getserver()
#        if server is not None:
#            try:
#                server.set_sending_streams(num)
#                dhnio.Dprint(6, 'transport_cspace.set_sending_streams %s' % str(num))
#                return True
#            except:
#                dhnio.Dprint(6, 'transport_cspace.set_sending_streams ERROR connecting to XMLRPC')
#                RestartService()
#        else:
#            dhnio.Dprint(6, "transport_cspace.set_sending_streams ERROR service not started")
#            RestartService()
#        return False

    def stop(self):
        server = self._getserver()
        if server is not None:
            try:
                server.stop()
                dhnio.Dprint(6, "transport_cspace.stop service stopped")
                return True
            except:
                pass
        return False
        
#------------------------------------------------------------------------------ 

class CSpaceServiceProtocol(protocol.ProcessProtocol):
    def __init__(self, process_finished_callback=None):
        self.process_finished_callback = process_finished_callback
    def outReceived(self, inp):
        for line in inp.splitlines():
            try:
                command = line.split(' ')[0]
                data = str(line[len(command)+1:].strip())
                if data:
                    try:
                        data = eval(data)
                    except:
                        dhnio.Dprint(6, str(data))
                        dhnio.DprintException()
            except:
                dhnio.Dprint(2, 'transport_cspace.CSpaceServiceProtocol.outReceived ERROR: %s' % line)
                dhnio.DprintException()
            # dhnio.Dprint(6, 'transport_cspace.CSpaceServiceProtocol.outReceived %s %s' % (command, str(data)))
            serviceResponse(command.lstrip('[').rstrip(']'), data)
            
    def errReceived(self, inp):
        for line in inp.splitlines():
            dhnio.Dprint(2, line)
            
    def processEnded(self, reason):
        if self.process_finished_callback:
            self.process_finished_callback(reason)
    
#------------------------------------------------------------------------------ 

class PseudoListener:
    implements(interfaces.IListeningPort)
    def startListening(self):
        A('online')
        return succeed(A().state)
    def stopListening(self):
        return shutdown()
    def getHost(self):
        return keyID()

def getListener():
    global _Listener
    if _Listener is None:
        _Listener = PseudoListener()
    return _Listener

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

def RegisterTransferFuncDefault(send_or_receive, remote_address, callback, filename, size, description=''):
    try:
        from transport_control import register_transfer
        return register_transfer('cspace', send_or_receive, remote_address, callback, filename, size, description)
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

_SendStatusFunc = SendStatusFuncDefault
_ReceiveStatusFunc = ReceiveStatusFuncDefault
_RegisterTransferFunc = RegisterTransferFuncDefault
_UnRegisterTransferFunc = UnRegisterTransferFuncDefault

def SetSendStatusFunc(f):
    global _SendStatusFunc
    _SendStatusFunc = f

def SetReceiveStatusFunc(f):
    global _ReceiveStatusFunc
    _ReceiveStatusFunc = f

def SetRegisterTransferFunc(f):
    global _RegisterTransferFunc
    _RegisterTransferFunc = f
    
def SetUnRegisterTransferFunc(f):
    global _UnRegisterTransferFunc
    _UnRegisterTransferFunc = f
    
def SetContactStatusNotifyFunc(f):
    global _ContactStatusNotifyFunc
    _ContactStatusNotifyFunc = f

#------------------------------------------------------------------------------ 

def parseCommandLine():
    oparser = optparse.OptionParser()
    oparser.add_option("-s", "--send", dest="send", action="store_true", help='send a file to remote peer')
    oparser.add_option("-r", "--receive", dest="receive", action="store_true", help='waiting files from other users')
    oparser.add_option("-b", "--basedir", dest="basedir", help="base directory location where dhnet.py is located")
    oparser.add_option("-d", "--debug", dest="debug", action="store_true", help="also print CSpace output")
    oparser.set_default('debug', False)
    oparser.set_default('send', False)
    oparser.set_default('receive', False)
    oparser.set_default('basedir', '.')
    (options, args) = oparser.parse_args()
    return options, args

def main():
    global _BaseDir
    global _Debug
    options, args = parseCommandLine()
    _BaseDir = options.basedir 
    _Debug = options.debug
    dhnio.init()
    dhnio.SetDebug(18)
    settings.init()
    import identitycache
    identitycache.init()
    reactor.addSystemEventTrigger('before', 'shutdown', shutdown_final)
#    from transport_control import _InitDone
#    _InitDone = True
    def initDone(state, options, args):
        if state != 'online':
            print 'state is %s, exit' % state
            reactor.stop()
            return
        if options.send:
#            def _random_sending(count):
#                import random
#                if count > 10:
#                    return
#                print 'sending file %s to %s' % (args[0], args[1])
#                reactor.callLater(random.randint(0, 2), _random_sending, count+1)
#                send(args[0], args[1])
#                count += 1
#            reactor.callLater(0.5, _random_sending, 0)
            send(args[0], args[1])
            return
        if options.receive:
            print 'state is %s, receiving...' % state
            return
        print 'ONLINE !!!'
    init().addCallback(initDone, options, args)
    # reactor.callLater(20, A, 'shutdown')
    reactor.run() 
    
#------------------------------------------------------------------------------ 

if __name__ == '__main__':
    main()
