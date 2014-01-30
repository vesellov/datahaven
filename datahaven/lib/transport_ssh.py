#!/usr/bin/env python
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

import os
import sys
from twisted.internet.defer import Deferred
from twisted.python import log
from twisted.python import components
from twisted.cred import portal
from twisted.conch.client import options
from twisted.conch.client import direct
from twisted.conch.ssh import keys
from twisted.conch.ssh import session

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in transport_ssh.py')

if __name__ == '__main__':
    dirpath = os.path.dirname(os.path.abspath(sys.argv[0]))
    sys.path.insert(0, os.path.abspath('datahaven'))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..')))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..', '..')))

import misc
import settings
import dhnio
import dhncrypto
import contacts
import identitycache
import transport_control


from transport_ssh_client import MySSHConnection
from transport_ssh_client import MyUserAuth
from transport_ssh_client import my_verifyHostKey

from transport_ssh_server import MyAvatar
from transport_ssh_server import MyRealm
from transport_ssh_server import MyPublicKeyChecker
from transport_ssh_server import MyFactory
from transport_ssh_server import pub_keys_db


##import datahaven.lib.settings as settings

##log.startLogging(sys.stderr)

#-------------------------------------------------------------------------------
# PUBLIC KEYS DATABASE
#-------------------------------------------------------------------------------

def add_key(name, public_key):
    global pub_keys_db
    if pub_keys_db.has_key(name):
        return
    pub_keys_db[name] = keys.Key.fromString( public_key )
    transport_control.log('ssh', 'add public key to db for ' + name)
    dhnio.Dprint(10, "transport_ssh.add_key for " + name)

def remove_key(name):
    global pub_keys_db
    transport_control.log('ssh', 'remove public key of ' + name)
    if (pub_keys_db.has_key(name)):
        pub_keys_db.pop(name)

def add_identity2db(idlist):
    def _add_ok(src, idurl):
#        words = src.split('\n', 1)
#        if len(words) < 1:
#            dhnio.Dprint(1, 'transport_ssh.add_key ERROR wrong data')
#            return
#        ident = identitycache.FromCache(words[0].strip())
        ident = identitycache.FromCache(idurl)
        if ident == '' or ident is None:
            dhnio.Dprint(1, 'transport_ssh.add_key ERROR still not in the cache')
            return
        add_key(ident.getIDURL(),ident.publickey)


    def _add_fail(x, idurl):
        dhnio.Dprint(10, 'transport_ssh.add_key WARNING adding ssh key for ' + idurl)


    for idurl in idlist:
        if idurl.strip() == '':
            continue

        ident = identitycache.FromCache(idurl)
        if ident == '' or ident is None:
            d = identitycache.immediatelyCaching(idurl)
            d.addCallback(_add_ok, idurl)
            d.addErrback(_add_fail, idurl)
            continue

        add_key(ident.getIDURL(),ident.publickey)




#-------------------------------------------------------------------------------
# SEND
#-------------------------------------------------------------------------------

class SendingFactory(direct.SSHClientFactory):
    def clientConnectionLost(self, connector, reason):
        dhnio.Dprint(14,'transport_ssh.SendingFactory.clientConnectionLost with %s : %s' % (str(connector.getDestination()) ,str(reason.getErrorMessage())))
        direct.SSHClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
##        dhnio.Dprint(1,'transport_ssh.SendingFactory.clientConnectionFailed NETERROR with %s : %s' % (str(connector.getDestination()) ,str(reason.getErrorMessage())))
        direct.SSHClientFactory.clientConnectionFailed(self, connector, reason)
##        transport_control.connectionStatusCallback('ssh', connector.getDestination(), reason, 'connection failed' )
        transport_control.sendStatusReport(connector.getDestination(),
            self.userAuthObject.instance.filename,
            'failed', 'ssh', reason, 'connection failed' )

def send(host, port, username, public_key, private_key, filename):
    def connection_done(x, filename, c):
        dhnio.Dprint(14, 'transport_ssh.send.connection_done ')
##        c.transport.loseConnection()
    def connection_fail(x, filename, c):
        dhnio.Dprint(14, 'transport_ssh.send.connection_fail ')
##        if misc.transport_control_using():
        transport_control.sendStatusReport(host+':'+port, filename,
            'failed', 'ssh',
            x, 'connection failed')      # not so good
##        c.transport.loseConnection()
    def done(x, filename, c):
        dhnio.Dprint(14, 'transport_ssh.send.done')
##        if misc.transport_control_using():
        transport_control.sendStatusReport(host+':'+port, filename,
            'finished', 'ssh')
        c.transport.loseConnection()
    transport_control.log('ssh', 'start sending to '+str(host)+':'+str(port))
    dhnio.Dprint(12, 'transport_ssh.send: %s -> %s:%s' % (filename,host,port))
    port_ = port
    try:
        port_ = int(port)
    except:
        dhnio.Dprint(1,'transport_ssh.send ERROR wrong port number: ' + str(port))
        return
    opts = options.ConchOptions()
    opts.conns = ['direct']
    opts['nocache'] = True
    opts['subsystem'] = 'sftp'
    result_defer = Deferred()
    conn = MySSHConnection(filename, result_defer)
    conn.options = opts
    vhk = my_verifyHostKey
    uao = MyUserAuth(username, conn, public_key, private_key)
    d = Deferred()
    factory = SendingFactory(d, opts, vhk, uao)
    c = reactor.connectTCP(host, port_, factory)
##    client = c.transport
    d.addCallback(connection_done, filename, c)
    d.addErrback(connection_fail, filename, c)
    result_defer.addCallback(done, filename, c)
##    def file_sent(a):
##        dhnio.Dprint(12, 'transport_ssh.send.file_sent: file sent to server')
##        transport_control.log('ssh', 'sending done')
##        client.loseConnection()
##    stopD.addCallback(file_sent)




#-------------------------------------------------------------------------------
# RECEIVE
#-------------------------------------------------------------------------------

def receive(port):
    transport_control.log('ssh', 'start listening on port %s' % str(port))
    dhnio.Dprint(8,'transport_ssh.receive going to listen on port %s' % port)

    def _try_receiving(port, count):
        dhnio.Dprint(10, "transport_ssh.receive count=%d" % count)
        components.registerAdapter(None, MyAvatar, session.ISession)
        d = Deferred()
        myrealm = MyRealm(d)
        portal_ = portal.Portal(myrealm)
        portal_.registerChecker(MyPublicKeyChecker())
        MyFactory.portal = portal_
        try:
            mylistener = reactor.listenTCP(port, MyFactory())
        except:
            mylistener = None
        return mylistener

    def _loop(port, result, count):
        l = _try_receiving(port, count)
        if l is not None:
            dhnio.Dprint(8, "transport_ssh.receive started on port "+ str(port))
            result.callback(l)
            return
        if count > 10:
            dhnio.Dprint(1, "transport_ssh.receive WARNING port %s is busy!" % str(port))
            result.errback(None)
            return
        reactor.callLater(10, _loop, port, result, count+1)

    res = Deferred()
    _loop(port, res, 0)
    return res

    ##        transport_control.connectionStatusCallback('ssh', None, None, 'error listening port %s' % str(port))
##            transport_control.receiveStatusReport('', 'failed',
##                proto='ssh',
##                message='error listening port %s' % str(port))
    ##        dhnio.Dprint(1,'transport_ssh.receive NETERROR listening port %s' % str(port))
##            dhnio.DprintException()

##    def _receive_done(a):
##        print 'receive done. close port.'
##        mylistener.stopListening()
        #we should close port here.
        #but in transport_control we already close it and
        #this line raise error
        #i do not understand this Exception. i am keep thinking
##    return mylistener



def update_db():
    idlist = set()
    idlist.add(misc.getLocalID())
    idlist.add(settings.CentralID())
    #Not sure we need this:
    #idlist.add(settings.MoneyServerID())
    idlist = idlist.union(contacts.getContactsAndCorrespondents())

    add_identity2db(idlist)

def init():
    dhnio.Dprint(4, 'transport_ssh.init')
    update_db()

def main():
    if len(sys.argv) == 4:
        key_pub = dhncrypto.MyPublicKey()
        key_priv = dhncrypto.MyPrivateKey()
        send(sys.argv[1], sys.argv[2], 'testssh', key_pub, key_priv, sys.argv[3])
    elif len(sys.argv) == 3:
        add_key('guestkey', open(sys.argv[2]).read())
        receive(int(sys.argv[1]))
    else:
        print 'args:\n    [host] [port] [file name]\n  or\n    [port] [public key file name]\n'
        sys.exit()

if __name__ == '__main__':
    dhnio.SetDebug(18)
    lf = file('log.p2p', 'ab+')
    log.startLogging(lf, setStdout=False)
    main()
    reactor.run()



