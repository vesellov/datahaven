#!/usr/bin/env python
#transport_ssh_client.py
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
import stat

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in transport_ssh_client.py')

#from twisted.conch.client import agent
#from twisted.conch.client import connect
#from twisted.conch.client import default
#from twisted.conch.client import options
from twisted.conch.ssh import channel
#from twisted.conch.ssh import filetransfer
from twisted.conch.ssh import keys
from twisted.conch.ssh import userauth
from twisted.conch.ssh.connection import SSHConnection
from twisted.conch.ssh import common
#from twisted.conch.ssh import userauth
from twisted.internet import defer
from twisted.internet import protocol
from twisted.internet.interfaces import IConsumer
#from twisted.python.filepath import FilePath
#from twisted.python import log
#from twisted.protocols import basic

from zope.interface import implements


#import misc
import dhnio
import transport_control


##import datahaven.lib.identity as identity
##import datahaven.lib.settings as settings
##log.startLogging(sys.stderr)

def fail(err):
    dhnio.Dprint(1, 'transport_ssh.fail NETERROR ' + str(err.getErrorMessage()))
    raise err

class MySSHConnection(SSHConnection):
    def __init__(self, filename, stop_defer):
        SSHConnection.__init__(self)
        self.filename = filename
        self.stop_defer = stop_defer

    def serviceStarted(self):
        dhnio.Dprint(14,'transport_ssh.MySSHConnection.serviceStarted')
        self.openChannel(MySSHSession(self.filename, self.stop_defer))

class MyFileTransferClient(protocol.Protocol):
    BUFFER_SIZE = 16384

    def __init__(self, filename, stop_defer):
        self.filename = filename
        self.stop_defer = stop_defer
        self.buf = ''
        self.total_size = 0
        self.total_sent = 0

    def connectionMade(self):
        dhnio.Dprint(14, 'transport_ssh.MyFileTransferClient.connectionMade')
        self.buf = ''
        self.total_size = 0
        self.total_sent = 0
        try:
            self.total_size = os.stat(self.filename)[stat.ST_SIZE]
            self.fin = open(self.filename, 'rb')
            dhnio.Dprint(14, 'transport_ssh.MyFileTransferClient.connectionMade file %s have %s bytes' % (self.filename, str(self.total_size)))
        except:
            dhnio.Dprint(1, 'transport_ssh.MyFileTransferClient.connectionMade ERROR opening file: ' + str(self.filename))
            dhnio.DprintException()
            self.transport.loseConnection()
            return
        self.sendNextPart()

    def dataReceived(self, data):
        dhnio.Dprint(14, 'transport_ssh.MyFileTransferClient.dataReceived: '+str(data))
        try:
            amount = int(data)
        except:
            dhnio.Dprint(1, 'transport_ssh.MyFileTransferClient.dataReceived NETERROR bad response from the ssh server')
##            transport_control.connectionStatusCallback('ssh', self.transport.getPeer(), None, 'bad response from the ssh server')
            transport_control.sendStatusReport(self.transport.getPeer(),
                self.filename,
                'failed', 'ssh',
                None, 'bad response from the ssh server')
            self.breakTransfer()
            self.connectionLost(0)
            return

        if amount < self.total_size:
            self.sendNextPart()
        else:
            self.finishTransfer()
            self.connectionLost(1)

    def sendNextPart(self):
        dhnio.Dprint(14, 'transport_ssh.MyFileTransferClient.sendNextPart')
        self.buf = ''
        try:
            self.buf = self.fin.read(self.BUFFER_SIZE)
            self.fin.flush()
        except:
            dhnio.Dprint(1, 'transport_ssh.MyFileTransferClient ERROR reading buffer data from file')
            self.breakTransfer()
            self.connectionLost(0)
            return

##        if len(self.buf) == 0:
##            self.finishTransfer()
##            self.connectionLost(1)
##            return
##
        try:
            self.transport.write(self.buf)
        except:
            dhnio.Dprint(1, 'transport_ssh.MyFileTransferClient.sendNextPart NETERROR writing data to the transport')
##            transport_control.connectionStatusCallback('ssh', self.transport.getPeer(), None, 'error writing data to the transport')
            transport_control.sendStatusReport(self.transport.getPeer(),
                self.filename,
                'failed', 'ssh', None,
                'error writing data to the transport' )
            self.breakTransfer()
            self.connectionLost(0)
            return
        self.total_sent += len(self.buf)
        dhnio.Dprint(14, 'transport_ssh.MyFileTransferClient.sendNextPart total %s bytes sent' % str(self.total_sent))

    def finishTransfer(self):
        dhnio.Dprint(14, 'transport_ssh.MyFileTransferClient.finishTransfer')
        try:
            self.fin.close()
        except:
            pass

    def breakTransfer(self):
        dhnio.Dprint(14, 'transport_ssh.MyFileTransferClient.breakTransfer')
        try:
            self.fin.close()
        except:
            pass

    def connectionLost(self, reason):
        dhnio.Dprint(14, 'transport_ssh.MyFileTransferClient.connectionLost')
        try:
            self.fin.close()
        except:
            pass
        self.transport.loseConnection()
        self.stop_defer.callback(1)

class MySSHSession(channel.SSHChannel):
    implements(IConsumer)

    name = 'session'

    def __init__(self, filename, stop_defer):
        channel.SSHChannel.__init__(self)
        self.filename = filename
        self.stop_defer = stop_defer

    def registerProducer(self, producer, streaming):
        self.producer = producer
        if not streaming:
            self.producer.resumeProducing()

    def channelOpen(self, foo):
        d = self.conn.sendRequest(self, 'subsystem',
            common.NS(self.conn.options['subsystem']),
                wantReply=1)
        d.addCallback(self._cbSubsystem)
        d.addErrback(fail)

    def _cbSubsystem(self, result):
        self.client = MyFileTransferClient(self.filename, self.stop_defer)
        self.client.makeConnection(self)
        self.dataReceived = self.client.dataReceived

class MyUserAuth(userauth.SSHUserAuthClient):
    def __init__(self, user, instance, public_key_, private_key_):
        userauth.SSHUserAuthClient.__init__(self,user,instance)
        self.public_key = keys.Key.fromString( public_key_ )
        self.private_key = keys.Key.fromString( private_key_ )

    def getPublicKey(self):
        dhnio.Dprint(14,'transport_ssh.MyUserAuth.getPublicKey')
        return self.public_key.blob()

    def getPrivateKey(self):
        dhnio.Dprint(14,'transport_ssh.MyUserAuth.getPrivateKey')
        return defer.succeed(self.private_key.keyObject)

def my_verifyHostKey(transport, host, pubKey, fingerprint):
    return defer.succeed(1)

##class MySSHClientFactory(SSHClientFactory):
##    def __init__(self, d, options, verifyHostKey, userAuthObject):
##        SSHClientFactory.__init__(self,d,options,verifyHostKey,userAuthObject)


