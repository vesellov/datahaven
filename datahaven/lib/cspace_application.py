#!/usr/bin/python
#cspace_application.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
import os
import sys
import logging
import urllib
import StringIO
import time
import struct
import threading
import tempfile

if __name__ == '__main__':
    dirpath = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..')))

from nitro.selectreactor import SelectReactor, SelectStoppedError
from nitro.http import HttpRequest
from nitro.tcp import tcpConnect, TCPStream, TCPMessageStream

from ncrypt.rsa import RSAKey, RSAError
from ncrypt.digest import DigestType, Digest

from cspace.main.service import CSpaceService
from cspace.main.common import isValidUserName, localSettings
from cspace.main.profile import Contact, createProfile, listProfiles, loadProfile, saveProfileContacts, clearProfileContacts
from cspace.main.appletserver import AppletServer
from cspaceapps.appletutil import CSpaceEnv, CSpaceConnector, CSpaceAcceptor


# CSpace can open a socket for us - directly to the remote machine
# after we sent a file we keep it opened ...
# to be able to send the next file as soon as possible
# we can send several files at same time - several opened sockets to this user
# of course we want to the socket after file sent ...
# but let's keep last socket opened ...    or last N sockets 
OPENED_SENDING_STREAMS_NUMBER = 1
# after we receive a file from this man
# we check if we have more files receiving at the moment from him
# if yes - close this stream because not needed
# so keep last N streams opened after receiving
# may be we want to have more streams opened to increase speed 
OPENED_RECEIVING_STREAMS_NUMBER = 2

_SendingDelay = 0.01

_Reactor = None
_Service = None
_Application = None
_ContactStatus = {}
_OutgoingFilesDict = {}
_OutgoingQueue = []
_ReceivingStreams = {}
_SendingStreams = {}

_MyProfile = None
_TempFileFunc = None
_TempLocation = None
_ReceiveNotifyFunc = None
_SendNotifyFunc = None
_StatusNotifyFunc = None
_ContactStatusNotifyFunc = None
_AppLogger = None

#------------------------------------------------------------------------------


def app():
    global _Application
    if _Application is not None:
        return _Application
    _Application = MyCSpaceApplication(False)
    return _Application


def kill_app():
    global _Application
    del _Application
    _Application = None


def run(init_callback=None):
    app().init_callback = init_callback
    app().run()


def stop(shutdown_callback=None):
    app().shutdown_callback = shutdown_callback
    app().stop()

_InstallReactor = None
_InstallKeyID = -1
def on_install_response(returnCode, data):
    global _InstallReactor
    global _InstallKeyID
    if returnCode != 200 :
        _InstallKeyID = -1
    else:
        try :
            _InstallKeyID = int(data)
        except ValueError :
            _InstallKeyID = -1
    _InstallReactor.stop()
def install(username, password, install_callback=None):
    global _InstallReactor
    global _InstallKeyID
    from nitro.selectreactor import SelectReactor
    if _InstallReactor is None:
        _InstallReactor = SelectReactor()
    _InstallKeyID = -1
    rsaKey = RSAKey()
    rsaKey.generate( bits=2048 )
    data = 'username:%s' % username
    digestType = DigestType( 'SHA1' )
    digest = Digest(digestType).digest( data )
    signature = rsaKey.sign( digest, digestType )
    postData = urllib.urlencode(dict(
        username = username,
        public_key = rsaKey.toDER_PublicKey(),
        signature = signature,))
    request = HttpRequest(_InstallReactor)
    httpOp = request.post('http://cspace.in/addkey', postData, on_install_response,)

    _InstallReactor.run()
    del _InstallReactor
    _InstallReactor = None

    if _InstallKeyID < 0:
        if install_callback is not None:
            install_callback(_InstallKeyID)
        return

    st = localSettings()
    username = str(_InstallKeyID)
    st.setString('Settings/SavedProfile', username)
    old_password = st.getString('Settings/SavedPassword')
    if old_password != password and old_password:
        st.setString('Settings/SavedPassword'+'_'+(str(old_password).encode('hex')), old_password)
    st.setString('Settings/SavedPassword', password)
    st.setInt('Settings/RememberKey', 1)
    createProfile(rsaKey, password, username, str(_InstallKeyID))

    if install_callback is not None:
        install_callback(_InstallKeyID)


def register(username):
    app().register(username)


def online():
    return app().service.online()


def offline():
    if app().service.status is app().service.ONLINE:
        return app().service.offline()
    return True


def send(keyID, filename):
    app().send(keyID, filename)


def probe(keyID, cb):
    app().probe(keyID, cb)


def add(keyID, cb=None):
    app().add(keyID, cb)


def isContact(keyID):
    return app().isContact(keyID)


def state(keyID):
    return app().state(keyID)


def status(keyID):
    return app().status(keyID)


def settings():
    return localSettings()


def profile():
#    global _MyProfile
#    if _MyProfile is not None:
#        return _MyProfile
    if not settings().getInt('Settings/RememberKey',0):
        return None
    if not settings().getInt('Settings/RememberKey',0):
        return None
    entries = [entry for userName,keyId,entry in listProfiles()]
    entry = settings().getString('Settings/SavedProfile')
    password = settings().getString('Settings/SavedPassword')
    if not (entry and password and (entry in entries)):
        return None
    #_MyProfile = loadProfile(entry, password)
    #return _MyProfile
    return loadProfile(entry, password)


def pushFileName(SendToKeyID, filename):
    global _OutgoingQueue
    global _OutgoingFilesDict
    if not _OutgoingFilesDict.has_key(SendToKeyID):
        _OutgoingFilesDict[SendToKeyID] = list()
    _OutgoingFilesDict[SendToKeyID].append(filename)
    _OutgoingQueue.append(SendToKeyID)
    #app().ProcessSending()
    #print 'pushFileName', SendToKeyID, 'current thread is', threading.current_thread().name


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


def isInstalled():
    return profile() is not None


def getKeyID():
    p = profile()
    if p is not None:
        return p.keyId
    return ''


def getFrom():
    try:
        return app().service.profile
    except:
        return None


def clearContacts():
    clearProfileContacts(profile)


def receiving_streams(keyID):
    global _ReceivingStreams
    return _ReceivingStreams.get(keyID, None)


def sending_streams(keyID):
    global _SendingStreams
    return _SendingStreams.get(keyID, None)


def hackConfigDir(new_function_object):
    import cspace.util.settings
    cspace.util.settings.getConfigDir = new_function_object


def hackPermissions():
    import cspace.main.permissions
    cspace.main.permissions.predefinedPermissions = """
allow <any-user>     service <any-service>
"""


def setTempFileFunc(f):
    global _TempFileFunc
    _TempFileFunc = f


def setTempLocation(dirpath):
    global _TempLocation
    _TempLocation = dirpath


def setSendNotifyFunc(f):
    global _SendNotifyFunc
    _SendNotifyFunc = f


def setReceiveNotifyFunc(f):
    global _ReceiveNotifyFunc
    _ReceiveNotifyFunc = f


def setStatusNotifyFunc(f):
    global _StatusNotifyFunc
    _StatusNotifyFunc = f


def setContactStatusNotifyFunc(f):
    global _ContactStatusNotifyFunc
    _ContactStatusNotifyFunc = f


def fromPEM_PublicKeyFixed(src):
    from ncrypt.rsa import RSAKey
    from pyasn1.codec.der import decoder
    from base64 import decodestring
    body = src.replace('-----BEGIN RSA PUBLIC KEY-----\n', '')
    body = body.replace('-----END RSA PUBLIC KEY-----', '')
    body = body.replace('\n','')
    derbody = decodestring(body)
    (priv, _) = decoder.decode(derbody)
    as_ints = tuple(int(x) for x in priv)
    k = RSAKey()
    k.loadPublicKey((as_ints[0], as_ints[1]))
    return k


def _stdOutFunc(s):
    print s


class CSpace_stdout:
    softspace = 0
    def read(self): pass
    def write(self, s):
        _stdOutFunc(s)
    def flush(self): pass
    def close(self): pass


def init_log(logLevel=0, logFilename='cspace.log', logWriteMode='w'):
    global _AppLogger
    if logFilename == 'dhnio':
        logging.basicConfig(level=logLevel, stream=CSpace_stdout(),
                            format='%(name)30s    %(levelname)5s   %(message)s', )
    else:
        if not os.path.isdir(os.path.dirname(logFilename)):
            try:
                os.makedirs(os.path.dirname(logFilename))
            except:
                pass
        logging.basicConfig(level=logLevel, filename=logFilename, filemode=logWriteMode,
                            format='%(name)30s    %(levelname)5s   %(message)s', )
    _AppLogger = logging.getLogger('cspace_application')

# need to send files inside same stream
# close stream if only connection error or connection lost
class FileSender(object):
    CHUNK_SIZE = (2 ** 16) - 256

    def __init__(self, reactor, stream, peer):
        self.reactor = reactor
        self.stream = stream
        self.files2send = []
        self.peer = peer
        self.waitOp = None
        self.currentOp = None
        self.bytesSent = 0
        self.totalBytesSent = 0
        self.lastPacketTime = 0
        self.stream.setInputCallback(self.dataReceived)
        self.stream.setCloseCallback(self.connectionLost)
        self.stream.setErrorCallback(self.connectionError)
        self.stream.enableRead(True)
        self.state = 'ready'

    def start(self, filename):
        if self.state != 'ready':
            self.close_file()
            self.state = 'lost'
            self.close_stream()
            return
        self.filename = filename
        try:
            self.file = file(self.filename, 'rb')
            self.file.seek(0, 2)
            self.length = self.file.tell()
            self.file.seek(0)
        except:
            _AppLogger.exception('exception in FileSender.doWaitNewFiles')
            self.failed('failed', 'error reading input file')
            self.close_file()
            self.state = 'lost'
            self.close_stream()
            return
        try:
            self.stream.sendMessage(struct.pack("!Q", self.length))
        except:
            _AppLogger.exception('exception in FileSender.doWaitNewFiles')
            self.failed('failed', 'error writing, seems connection were lost')
            self.close_file()
            self.state = 'lost'
            self.close_stream()
            return
        self.bytesSent = 0
        self.state = 'sending'
        self.doSend()

    def doSend(self):
        self.currentOp = None
        chunk = self.file.read(self.CHUNK_SIZE)
        if not chunk:
            self.close_file()
            self.state = 'waiting'
            self.doWaitFinishSending()
            return
        self.stream.sendMessage(chunk)
        self.bytesSent += len(chunk)
        self.currentOp = self.reactor.callLater(0, self.doSend)

    def doWaitFinishSending(self):
        #all data was sent
        #now need to wait to finish receiving
        #but we do not want to wait too long
        #if we did not receive any response
        #we assume the connection was lost
        def sent_timeout():
            if time.time() - self.lastPacketTime > 30:
                self.waitOp = None
                self.failed('timeout', 'other side not responding')
                self.state = 'lost'
                self.close_stream()
            else:
                self.doWaitFinishSending()
        self.waitOp = self.reactor.callLater(60, sent_timeout)

    def dataReceived(self, data):
        self.lastPacketTime = time.time()
        bytesReceived ,= struct.unpack("!Q", data[:8])
        #print 'FileSender.dataReceived %d/%d' % (bytesReceived, self.length)
        if bytesReceived == self.length:
            #print 'FileSender.dataReceived sent success to', self.peer
            self.done()
            self.state = 'sent'
            self.close_wait_op()
            self.close_stream_if_has_other_opened()
            #self.doWaitNewFiles()
        elif bytesReceived > self.length:
            self.failed('failed', 'data did not sent correctly')
            self.close_wait_op()
            self.state = 'error'
            self.close_stream()
            #self.doWaitNewFiles()

    def connectionLost(self):
        #print 'FileSender.connectionLost with', self.peer, 'state:', self.state
        if self.state in ['sending',]:
            self.failed('failed', 'connection lost while %s' % self.state)
        self.close_file()
        self.close_wait_op()
        self.state = 'lost'
        self.close_stream()

    def connectionError(self, err, errMsg):
        #print 'FileSender.connectionError with', self.peer, errMsg
        if self.state in ['sending',]:
            #print 'FileSender.connectionError while sending with', self.peer, errMsg
            self.failed('failed', 'connection error while %s: %s' % (self.state, errMsg))
        self.close_file()
        self.close_wait_op()
        self.state = 'error'
        self.close_stream()

    def done(self):
        global _SendNotifyFunc
        self.totalBytesSent += self.bytesSent
        _SendNotifyFunc(self.peer, self.filename, 'finished', 'cspace')

    def failed(self, status, msg):
        global _SendNotifyFunc
        _SendNotifyFunc(self.peer, self.filename, status, 'cspace', None, msg)

    def close_wait_op(self):
        if self.waitOp is not None:
            self.waitOp.cancel()
            self.waitOp = None

    def close_file(self):
        try:
            self.file.close()
        except:
            pass
        self.file = None

    def close_stream(self):
        global _AppLogger
        global _SendingStreams
        try:
            if not self.stream.stream.shutdownFlag:
                fileno = self.stream.stream.sock.fileno()
                self.stream.close()
                #print 'FileSender.close_stream with', self.peer, 'sock:', fileno, 'state:', self.state
        except:
            _AppLogger.exception('exception in FileSender.close_stream')
        if _SendingStreams.has_key(self.peer):
            if self in _SendingStreams[self.peer]:
                _SendingStreams[self.peer].remove(self)
                #print 'other streams:', len(_SendingStreams[self.peer])
        else:
            _AppLogger.critical('can not find %s in _SendingStreams' % self.peer)

    def close_stream_if_has_other_opened(self):
        self.close_stream()
        return
#        global _SendingStreams
#        streams = _SendingStreams.get(self.peer, [])
#        if len(streams) > OPENED_SENDING_STREAMS_NUMBER:
#            self.close_stream()


class FileReceiver(object):
    def __init__(self, reactor, peer, stream):
        self.reactor = reactor
        self.peer = peer
        self.stream = stream
        self.bytesReceived = 0
        self.totalBytesReceived = 0
        self.length = 0
        self.fd = None
        self.filename = ''
        self.gotLength = False
        self.close_op = None
        self.state = 'ready'
        self.stream.setInputCallback(self.dataReceived)
        self.stream.setCloseCallback(self.connectionLost)
        self.stream.setErrorCallback(self.connectionError)
        self.stream.enableRead(True)
        #print 'FileReceiver.__init__ peer=%s' % self.peer

    def openFile(self):
        global _TempLocation
        self.fd, self.filename = tempfile.mkstemp('', '', _TempLocation)

    def closeFile(self):
        if self.fd is not None:
            os.fsync(self.fd)
            os.close(self.fd)
            self.fd = None

    def dataReceived(self, data):
        global _ReceiveNotifyFunc
        if self.state == 'ready':
            self.openFile()
            self.length ,= struct.unpack("!Q", data[:8])
            self.bytesReceived = 0
            data = data[8:]
            self.state = 'receiving'
            #print 'FileReceiver.dataReceived length received from %s: %d' % (self.peer, self.length)
            
        if self.state == 'receiving':
            os.write(self.fd, data)
            self.bytesReceived += len(data)
            self.stream.sendMessage(struct.pack("!Q", self.bytesReceived))
            #print 'FileReceiver.dataReceived %d bytes received from %s, total: %d' % (len(data), self.peer, self.bytesReceived)
            if self.bytesReceived == self.length:
                #print 'FileReceiver.dataReceived received all data success from', self.peer, self.length
                self.closeFile()
                self.totalBytesReceived += self.bytesReceived
                _ReceiveNotifyFunc(self.filename, 'finished', 'cspace', self.peer)
                self.state = 'received'
                self.doWaitToClose()

    def doWaitToClose(self):
        # all data was received
        # now need to wait to close that stream
        # we want other side to do this
        # but if it is not - we will close it in 10 seconds
        def close_timeout():
            self.close_op = None
            self.state = 'finished'
            self.close_stream_if_has_other_opened()
        self.close_op = self.reactor.callLater(10, close_timeout)

    def stopWaitToClose(self):
        if self.close_op is not None:
            self.close_op.cancel()
            self.close_op = None

    def connectionLost(self):
        #print 'FileReceiver.connectionLost with', self.peer, 'state:', self.state
        global _ReceiveNotifyFunc
        if self.state == 'receiving':
            self.closeFile()
            self.state = 'lost'
            _ReceiveNotifyFunc(self.filename, 'failed', 'cspace', self.peer, None, 'connection lost')
        self.stopWaitToClose()
        self.close_stream()

    def connectionError(self, err, errMsg):
        #print 'FileReceiver.connectionError with', self.peer, errMsg
        global _ReceiveNotifyFunc
        if self.state == 'receiving':
            #print 'FileReceiver.connectionError while receiving with', self.peer, errMsg
            self.closeFile()
            self.state = 'error'
            _ReceiveNotifyFunc(self.filename, 'failed', 'cspace', self.peer, err, 'connection error: ' + errMsg)
        self.stopWaitToClose()
        self.close_stream()

    def close_stream(self):
        global _AppLogger
        global _ReceivingStreams
        try:
            if not self.stream.stream.shutdownFlag:
                fileno = self.stream.stream.sock.fileno()
                self.stream.close()
                #print 'FileReceiver.close_stream with', self.peer, 'sock:', fileno, 'state:', self.state
        except:
            _AppLogger.exception('exception in FileReceiver.close_stream')
        if _ReceivingStreams.has_key(self.peer):
            if self in _ReceivingStreams[self.peer]:
                _ReceivingStreams[self.peer].remove(self)
                #print 'other streams:', len(_ReceivingStreams[self.peer])
        else:
            _AppLogger.critical('can not find %s in _ReceivingStreams' % self.peer)

    def close_stream_if_has_other_opened(self):
        self.close_stream()
        return
#        global _ReceivingStreams
#        streams = _ReceivingStreams.get(self.peer, [])
#        if len(streams) > OPENED_RECEIVING_STREAMS_NUMBER:
#            self.close_stream()


def AppletServer_onService(self, service, command, sslConn, peerKey, contactName, incomingName):
    global _AppLogger

    if service != 'receive':
        _AppLogger.critical('AppletServer_onService with action %s from %s (%s)' % (action, contactName, incomingName))
        return

    connectionId = self.incoming.addIncoming(sslConn, peerKey)

    def onAccept(err, sock):
        global _AppLogger
        global _ReceiveNotifyFunc
        global _ReceivingStreams
        if err < 0 :
            try:
                if sock is not None:
                    sock.close()
            except:
                _AppLogger.exception('AppletServer_onService.onAccept err=%d, contactName=%s' % (err, contactName))
            _ReceiveNotifyFunc('', 'failed', 'cspace', contactName, err, 'error: ' + str(err))
            return
        if not _ReceivingStreams.has_key(contactName):
            _ReceivingStreams[contactName] = []
        stream = TCPMessageStream(sock, self.reactor)
        newReceiver = FileReceiver(self.reactor, contactName, stream)
        _ReceivingStreams[contactName].append(newReceiver)
        #print 'onAccept new stream created to receive from', contactName, 'sock:', sock.fileno(), 'streams:', len(_ReceivingStreams[contactName])

    def onConnect(connector):
        global _ReceiveNotifyFunc
        if connector.getError() != 0 :
            _ReceiveNotifyFunc('', 'failed', 'cspace', contactName, None, 'error connecting to CSpace')
            return
        sock = connector.getSock()
        CSpaceAcceptor(sock, connectionId, self.reactor, onAccept)

    tcpConnect(('127.0.0.1',self.listenPort), self.reactor, onConnect)


def AppletServer_onAction( self, actionDir, action, command, contactName ) :
    global _AppLogger
    if action != 'send':
        _AppLogger.critical('AppletServer_onAction with action %s from %s' % (action, contactName))
        return

    def onConnectUser( err, sock ) :
        global _AppLogger
        global _SendNotifyFunc
        global _SendingStreams
        if err < 0 :
            try:
                if sock is not None:
                    sock.close()
                #stream.close()
            except:
                _AppLogger.exception('AppletServer_onAction.onConnectUser err=%d, contactName=%s' % (err, contactName))
            _SendNotifyFunc(contactName, '', 'failed', 'cspace', err, 'error:' + str(err))
            return
        #print 'onConnectUser to ', contactName, 'sock:', sock.fileno(), 'err:', err
        filename = popFileName(contactName)
        if filename == '':
            try:
                if sock is not None:
                    sock.close()
                #stream.close()
            except:
                _AppLogger.exception('AppletServer_onAction.onConnectUser err=%d, contactName=%s' % (err, contactName))
            _SendNotifyFunc(contactName, filename, 'failed', 'cspace', None, 'no files to send in the queue')
            return
        if not _SendingStreams.has_key(contactName):
            _SendingStreams[contactName] = []
        stream = TCPMessageStream(sock, self.reactor)
        newSender = FileSender(self.reactor, stream, contactName)
        newSender.start(filename)
        _SendingStreams[contactName].append(newSender)
        #print 'onConnectUser new stream created to send to', contactName, 'sock:', sock.fileno(), 'streams:', len(_SendingStreams[contactName]) 


    def onConnect( connector ) :
        global _SendNotifyFunc
        if connector.getError() != 0 :
            _SendNotifyFunc(contactName, '', 'failed', 'cspace', None, 'connection error: ' + connector.getErrorMsg())
            return
        CSpaceConnector(connector.sock, contactName, 'receive', self.reactor, onConnectUser)

    tcpConnect(('127.0.0.1', self.listenPort), self.reactor, onConnect)


class MyCSpaceApplication:
    def __init__(self, local=False, init_callback=None):
        if local:
            seedNodes = [('127.0.0.1', 10001)]
        else:
            #seedNodes = [('210.210.1.102', 10001)]
            seedNodes = [('208.78.96.185', 10001)]

        sys.modules['cspace.main.appletserver'].AppletServer._onService = AppletServer_onService
        sys.modules['cspace.main.appletserver'].AppletServer._onAction = AppletServer_onAction

        self.working = False
        self.service = CSpaceService(seedNodes)
        self.reactor = self.service.reactor
        self.dispatcher = self.service.dispatcher
        self.init_callback = init_callback
        self.shutdown_callback = None
        self.probeDict = {}
        self.contactsProbedCount = 0
        self.contastsProbbingDelay = 1

        self.dispatcher.register('service.start', self.onStarted)
        self.dispatcher.register('service.stop', self.onStopped)
        self.dispatcher.register('profile.connecting', self.onConnecting)
        self.dispatcher.register('profile.disconnecting', self.onDisconnecting)
        self.dispatcher.register('profile.reconnecting', self.onReconnecting)
        self.dispatcher.register('profile.online', self.onOnline)
        self.dispatcher.register('profile.offline', self.onOffline)
        self.dispatcher.register('contact.action', self.onUserAction)
        self.dispatcher.register('contact.add', self.onAddContact)
        self.dispatcher.register('contact.online', self.onUserOnline)
        self.dispatcher.register('contact.offline', self.onUserOffline)
        self.dispatcher.register('contacts.probing', self.onContactsProbing)
        self.dispatcher.register('contacts.probed', self.onContactsProbed)
        self.dispatcher.register('offlineim.get', self.onOfflineReceive)
        self.dispatcher.register('offlineim.put', self.onOfflineStore)
        self.dispatcher.register('offlineim.del', self.onOfflineDelete)
        self.dispatcher.register('err', self.onError)

        self.service.actionManager.activeActions.append(('send', 'send', '', 0))
        actionId = self.doRegisterAction('send', 'send', '', 0)
        self.service.appletServer.actions.append(actionId)
        self.service.actionManager.setDefaultAction(actionId)

        self.doRegisterService('receive', self.onSessionService)

        self.ProcessSending()


    def ProcessSending(self):
        global _SendingDelay
#        global _SendingStreams
        keyID = readSendingQueue()
        if keyID:
            self.service.action(keyID, 'send')
            _SendingDelay = 0.01
        else:
            if _SendingDelay < 2.0:
                _SendingDelay *= 2.0
        # attenuation
        self.reactor.callLater(_SendingDelay, self.ProcessSending)
        
        #self.service.action(keyID, 'send')
#        if _SendingStreams.has_key(keyID) and len(_SendingStreams[keyID]) > 0:
#            for stream in _SendingStreams[keyID]:
#                if stream.state == 'ready': 
            #        filename = popFileName(keyID)
            #        if filename == '':
            #            _SendNotifyFunc(contactName, filename, 'failed', 'cspace', None, 'no files to send in the queue')
            #            return
#                    stream.newFile(filename)
#                    break
        #print 'ProcessSending new action to', keyID 


    def doRegisterAction(self, actionDir, action, command, order):
        def __onAction(contactName):
            self.service.appletServer._onAction(actionDir, action, command, contactName)
        return self.service.actionManager.registerAction(action, __onAction, order)


    def doRegisterService(self, service, command):
        def __onService(sslConn, peerKey, contactName, incomingName):
            self.service.appletServer._onService(service, command, sslConn, peerKey, contactName, incomingName)
        return self.service.session.registerService(service, __onService)


#    def onAction(self, actionDir, action, command, contactName):
#        if action != 'send':
#            return
#        self.doSend(contactName)


    def onSessionService(self):
        pass


    def onStarted(self):
        global _AppLogger

        if self.service.online():
            clearProfileContacts(self.service.profile)
            self.service.profile.contactKeys.clear()
            self.service.profile.contactNames.clear()
            _AppLogger.info('all contacts was removed at startup')

#        global _StatusNotifyFunc
#        if _StatusNotifyFunc is not None:
#            _StatusNotifyFunc('started')


    def onConnecting(self, profile):
        global _StatusNotifyFunc
        if _StatusNotifyFunc is not None:
            _StatusNotifyFunc('connecting')


    def onOnline(self, profil):
        global _StatusNotifyFunc
        if len(profile().contactNames) == 0:
            if self.init_callback is not None:
                self.init_callback('online')
                self.init_callback = None
        if _StatusNotifyFunc is not None:
            _StatusNotifyFunc('online')


    def onDisconnecting(self, profile):
        global _StatusNotifyFunc
        if _StatusNotifyFunc is not None:
            _StatusNotifyFunc('disconnecting')


    def onReconnecting(self, profile):
        global _StatusNotifyFunc
        if _StatusNotifyFunc is not None:
            _StatusNotifyFunc('reconnecting')


    def onOffline(self, profile):
        global _StatusNotifyFunc
        if self.init_callback is not None:
            self.init_callback('offline')
            self.init_callback = None
        if _StatusNotifyFunc is not None:
            _StatusNotifyFunc('offline')


    def onContactsProbing(self, contacts):
        pass


    def onContactsProbed(self, contacts):
        global _StatusNotifyFunc
        global _AppLogger
        self.contactsProbedCount += 1
        _AppLogger.info('onContactsProbed %d' % self.contactsProbedCount)
        if self.init_callback is not None:
            self.init_callback('online')
            self.init_callback = None
        if _StatusNotifyFunc is not None:
            _StatusNotifyFunc('online')
#        if self.contactsProbedCount < 7:
#            self.contastsProbbingDelay *= 2
#            self.reactor.callLater(self.contastsProbbingDelay + 1, self.service.statusProbe.stopProbing)
#            self.reactor.callLater(self.contastsProbbingDelay + 2, self.service.statusProbe.startProbing)


    def onUserOnline(self, contact):
        global _ContactStatus
        global _ContactStatusNotifyFunc
        if self.probeDict.has_key(contact.name):
            for cb in self.probeDict[contact.name]:
                cb(contact, 'online')
            del self.probeDict[contact.name]
        _ContactStatus[contact.name] = 'online'
        if _ContactStatusNotifyFunc is not None:
            _ContactStatusNotifyFunc(contact.name, 'online')


    def onUserOffline(self, contact):
        global _ContactStatus
        global _ContactStatusNotifyFunc
        if self.probeDict.has_key(contact.name):
            for cb in self.probeDict[contact.name]:
                cb(contact, 'offline')
            del self.probeDict[contact.name]
        _ContactStatus[contact.name] = 'offline'
        if _ContactStatusNotifyFunc is not None:
            _ContactStatusNotifyFunc(contact.name, 'offline')


    def onUserAction(self, contact, action, retval):
        pass


    def onOfflineReceive(self, ts, msg, peerPubKey):
        pass


    def onOfflineStore(self, msg):
        pass


    def onOfflineDelete(self, envelope):
        pass


    def onError(self, msg):
        pass


    def onAddContact(self, contact):
        pass


    def onStopped(self):
        global _StatusNotifyFunc
        if self.shutdown_callback is not None:
            self.shutdown_callback('service stopped')
            self.shutdown_callback = None
        if _StatusNotifyFunc is not None:
            _StatusNotifyFunc('stopped')


    def run(self):
        self.working = True
        self.service.run()
        self.working = False


    def stop(self):
        global _SendingStreams
        global _ReceivingStreams
        for streams in _SendingStreams.values():
            for stream in streams:
                stream.close_stream()
        for streams in _ReceivingStreams.values():
            for stream in streams:
                stream.close_stream()

        self.service.status = self.service.OFFLINE
        self.service.stop()


    def send(self, keyID, filename):
        def _do_send():
            global _SendNotifyFunc
            if self.status(keyID) == self.service.ONLINE:
                pushFileName(keyID, filename)
                #self.service.action(keyID, 'send')
            else:
                _SendNotifyFunc(keyID, filename, 'failed', 'cspace', None, 'contact is offline')

        def _probed(contact, status):
            _do_send()

        def _do_probe():
            self.probe(keyID, _probed)

        def _added(contact):
            if contact is None:
                return
            _do_probe()

        if self.service.profile is None:
            return
        if not self.isContact(keyID):
            self.add(keyID, _added)
            return
        _do_send()


    def add(self, keyID, add_callback=None):
        if self.service.profile.contactNames.has_key(keyID):
            if add_callback is not None:
                add_callback(self.service.profile.contactNames.get(keyID))
            return
        def _onLookupResponse(responseCode, data):
            global _AppLogger
            if responseCode != 200 :
                if add_callback is not None:
                    add_callback(None)
                return
            inp = StringIO.StringIO( data )
            name = inp.readline().strip()
            pemPublicKey = inp.read()
            if name and not isValidUserName(name) :
                if add_callback is not None:
                    add_callback(None)
                return

#            k = RSAKey()
#            try:
#                k.fromPEM_PublicKey( pemPublicKey )
#            except:
#                if add_callback is not None:
#                    add_callback(None)
            try:
                k = fromPEM_PublicKeyFixed( pemPublicKey )
            except:
                _AppLogger.exception('can not create a key for user %s, keyID=%s' %(name, keyID))
                if add_callback is not None:
                    add_callback(None)
                return

            contact = Contact(k, keyID)
            if keyID in self.service.profile.contactNames.keys():
                self.service.profile.removeContact(contact)
            self.service.profile.addContact(contact)
            saveProfileContacts(self.service.profile)
            if add_callback is not None:
                add_callback(contact)

        httpOp = HttpRequest( self.reactor )
        httpOp.get('http://cspace.in/pubkey/%s' % keyID, _onLookupResponse )


    def probe(self, keyID, cb=None):
        if not self.probeDict.has_key(keyID):
            self.probeDict[keyID] = []
        if cb is not None:
            self.probeDict[keyID].append(cb)
        self.service.probe(keyID)


    def isContact(self, keyID):
        if self.service.profile is None:
            return False
        return keyID in self.service.profile.contactNames.keys()


    def contact(self, keyID):
        if self.service.profile is None:
            return None
        if not self.isContact(keyID):
            return None
        return self.service.profile.getContactByName(keyID)


    def status(self, keyID):
        c = self.contact(keyID)
        if c is None:
            return self.service.UNKNOWN
        return hasattr(c, 'status') and c.status or self.service.UNKNOWN

    def state(self, keyID):
        global _ContactStatus
        return _ContactStatus.get(keyID, 'unknown')

#------------------------------------------------------------------------------


##
def test():
    src = '''
-----BEGIN RSA PUBLIC KEY-----
MIIBCAKCAQEA7GlbcsySk8cgHfzx7BmGnF+WWrwFRpMJN26u9BsAL0eETEeQsQXE
gDeKrUHMs5EKtBBRuJlHKy0uxqK0M/KyAfBw7a6HhNQwT2/2dXhylUre1coCHeIv
KBkV1WJxNnjCJwKrWY0y5geKczPnRoAYJFqNZE1XzyYOqYmVoCs6XB5yPw2nOfcV
TX5fXYPzsnA9EaR+l2GKbmwIJXGZTW4kl1P6VCjrtlEL5B1qyOd3JYUm8JRJihca
8LIQrNu00awnxAkUQS0ucp5MHaI0jFK79sgkDujdAWtPL7A/CK97WUMNl9JhAvV/
oN9GFZO5MuNwUcfu1Nqf8Xj18lT1g9bH5wIBBQ==
-----END RSA PUBLIC KEY-----
'''
    k = fromPEM_PublicKeyFixed(src)
##    st = localSettings()
##    old_password = st.getString('Settings/SavedPassword')
##    print old_password
##    str1 = 'Settings/SavedPassword'+'_'+(str(old_password).encode('hex'))
##    print str1
##    st.setString(str1, old_password)

if __name__ == '__main__':
    test()

