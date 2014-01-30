#!/usr/bin/env python
#transport_ssh_server.py
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

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in transport_ssh_server.py')

from twisted.cred import portal
from twisted.conch import avatar
from twisted.conch.checkers import SSHPublicKeyDatabase
from twisted.conch.ssh import factory, session
from twisted.internet import protocol
from zope.interface import implements
#import tempfile


#import misc
import dhnio
import transport_control
import dhncrypto
import tmpfile


##from identity import datahaven.lib.identity as identity

#we need to keep public keys which we would like to accept on server
pub_keys_db = {}

class MyReceiveFilesSubsistem(protocol.Protocol):
    filename = ""     # string with path/filename
    fout = ""         # integer file descriptor like os.open() returns
    stop_defer = None
    total_size = 0
##    peer=""

    def __init__(self, *args, **kw):
        dhnio.Dprint(14, 'transport_ssh.MyReceiveFilesSubsistem.__init__')

    def connectionMade(self):
        transport_control.log('ssh', 'new income connection')
        dhnio.Dprint(14, 'transport_ssh.MyReceiveFilesSubsistem.connectionMade')
#        self.fout, self.filename = tempfile.mkstemp(".dhn-ssh-in")
        self.fout, self.filename = tmpfile.make("ssh-in")
        self.total_size = 0
        self.stop_defer = self.transport.session.avatar.stop_defer

    def dataReceived(self, data):
        dhnio.Dprint(14, 'transport_ssh.MyReceiveFilesSubsistem.dataReceived')
        os.write(self.fout,data)
        amount = len(data)
        self.total_size += amount
        self.transport.write(str(self.total_size))
        dhnio.Dprint(14, 'transport_ssh: total %s bytes of data received' % self.total_size)

    def connectionLost(self, reason):
        dhnio.Dprint(14, 'transport_ssh.MyReceiveFilesSubsistem.connectionLost')
        try:
            os.close(self.fout)
            transport_control.receiveStatusReport(
                self.filename,
                "finished",
                'ssh',
                self.transport.getPeer(),
                reason)
        except:
            pass
        if not self.stop_defer.called:
            self.stop_defer.callback('done')
        transport_control.log('ssh', 'income connection finished')
##        self.transport.loseConnection()


class MyAvatar(avatar.ConchUser):
    def __init__(self, username, stop_defer):
        dhnio.Dprint(14, 'transport_ssh.MyAvatar.__init__')
        avatar.ConchUser.__init__(self)
        self.username = username
        self.stop_defer = stop_defer
        self.channelLookup.update({'session':session.SSHSession})
        self.subsystemLookup.update({'sftp': MyReceiveFilesSubsistem})


class MyRealm:
    implements(portal.IRealm)

    stop_defer = None
    def __init__(self, stop_defer):
        self.stop_defer = stop_defer

    def requestAvatar(self, avatarId, mind, *interfaces):
        dhnio.Dprint(14, 'transport_ssh.MyRealm.requestAvatar')
        return interfaces[0], MyAvatar(avatarId, self.stop_defer), lambda: None

class MyPublicKeyChecker(SSHPublicKeyDatabase):
    def checkKey(self, credentials):
        dhnio.Dprint(14, 'transport_ssh.MyPublicKeyChecker.checkKey')
        global pub_keys_db
##        global not_use_publicKeyObj
##        #we do not need to accept this key
##        if credentials.blob == not_use_publicKeyObj:
##            dhnio.Dprint(1, 'transport_ssh: ERROR SECURITY VIOLATION try to login with wrong key' )
##            return False
        for name in pub_keys_db:
##            public_key = keys.getPublicKeyString(data=pub_keys_db[name])
            public_key = pub_keys_db[name]
            if credentials.blob == public_key.blob():
                dhnio.Dprint(14,'transport_ssh: user %s get access to transport_ssh server' % name)
                return True
        return False

class MyFactory(factory.SSHFactory):
##    publicKeys = {
##        'ssh-rsa': not_use_publicKeyObj.keyObject
##    }
##    privateKeys = {
####        'ssh-rsa': keys.getPrivateKeyObject(data=not_use_privateKey)
##        'ssh-rsa': keys.Key.fromString(not_use_privateKey).keyObject
##    }
##    services = {
##        'ssh-userauth': userauth.SSHUserAuthServer,
##        'ssh-connection': connection.SSHConnection
##    }

    def getPublicKeys(self):
        return { 'ssh-rsa': dhncrypto.MyPublicKeyObject() }

    def getPrivateKeys(self):
        return { 'ssh-rsa': dhncrypto.MyPrivateKeyObject() }

    def buildProtocol(self, addr):
        dhnio.Dprint(14, 'transport_ssh.MyFactory.buildProtocol ' + str(addr))
        self._transport = factory.SSHFactory.buildProtocol(self, addr)
        return self._transport

    def stopFactory(self):
        dhnio.Dprint(14, 'transport_ssh.MyFactory.stopFactory')
        try:
            self._transport.loseConnection()
        except:
            pass





