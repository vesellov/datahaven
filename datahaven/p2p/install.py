#!/usr/bin/python
#install.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

import os
import sys

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in install.py')

from twisted.internet.defer import Deferred


import lib.dhnio as dhnio
import lib.dhncrypto as dhncrypto
import lib.dhnnet as dhnnet
import lib.misc as misc
import lib.settings as settings
import lib.identitycache as identitycache
import lib.nameurl as nameurl
import lib.stun as stun
import lib.identity as identity
import lib.transport_control as transport_control
import lib.automats as automats

import shutdowner
import identitypropagate
import central_service
import run_upnpc


DEBUG_PASS_STUN = False
DEBUG_PASS_SEND_IDENTITY = False
DEBUG_PASS_CACHE_CENTRAL_ID = False

MAX_WAITING_COUNT = 30

_Waiting4NameCount = 0
_Waiting4NameCall = None
_ProgressNotifyCallback = None
_RegistrationInProcess = False
_WorkingProtocols = []
_SentPackets = {}

#-------------------------------------------------------------------------------


def SetProgressNotifyCallback(cb):
    global _ProgressNotifyCallback
    _ProgressNotifyCallback = cb

def ProgressMessage(msg):
    global _ProgressNotifyCallback
    if _ProgressNotifyCallback is not None:
        _ProgressNotifyCallback(msg)

# return the result in the defer.callback (errback never will be called)
# possible values: exist, success, failed, timeout
def RegisterNewUser(login):
    global _RegistrationInProcess
    if _RegistrationInProcess:
        dhnio.Dprint(1, 'install.RegisterNewUser ERROR registration in process')
        return None
    _RegistrationInProcess = True
    dhnio.Dprint(4, 'install.RegisterNewUser ' + login)
    dhnio.WriteFile(settings.UserNameFilename(), login)
    url = nameurl.UrlMake('http', settings.IdentityServerName(), '', login+'.xml')
    identitycache.Clear()
    dhnio.Dprint(4, 'install.RegisterNewUser request ' + url)
    reactor.callLater(0, ProgressMessage, 'checking account name')
    res = dhnnet.getPageTwisted(url)
    finalDefer = Deferred()
    res.addCallback(username_busy, login, finalDefer)
    res.addErrback(username_free, login, finalDefer)
    return finalDefer

def username_busy(x, login, finalDefer):
    global _RegistrationInProcess
    dhnio.Dprint(4, 'install.username_busy')
    _RegistrationInProcess = False
    finalDefer.callback('exist')
    reactor.callLater(1, ProgressMessage, 'user already exist')

def username_free(x, login, finalDefer):
    dhnio.Dprint(4, 'install.username_free')
    reactor.callLater(0, ProgressMessage, 'detecting local IP address')
    reactor.callLater(1, detect_local_ip, login, finalDefer)

def detect_local_ip(login, finalDefer):
    dhnio.Dprint(4, 'install.detect_local_ip')
    if os.path.isfile(settings.LocalIPFilename()):
        localip = dhnio.ReadTextFile(settings.LocalIPFilename())
        reactor.callLater(0, ProgressMessage, 'your local IP is %s' % localip)
        reactor.callLater(1, ProgressMessage, 'detecting external IP address')
        reactor.callLater(2, detect_external_ip, login, finalDefer)
        return
    localip = dhnnet.getLocalIp()
    dhnio.WriteFile(settings.LocalIPFilename(), str(localip))
    reactor.callLater(0, ProgressMessage, 'your local IP is %s' % localip)
    reactor.callLater(1, ProgressMessage, 'detecting external IP address')
    reactor.callLater(2, detect_external_ip, login, finalDefer)

def detect_external_ip(login, finalDefer):
    dhnio.Dprint(4, 'install.detect_external_ip')
    if os.path.isfile(settings.ExternalIPFilename()):
        reactor.callLater(1, stun_success, dhnio.ReadTextFile(settings.ExternalIPFilename()), login, finalDefer)
        return
    if DEBUG_PASS_STUN:
        reactor.callLater(5, stun_success, '127.0.0.1', login, finalDefer)
        return
    d = stun.stunExternalIP(
        close_listener=False, 
        internal_port=settings.getUDPPort(), 
        block_marker=shutdowner.A)
    d.addCallback(stun_success, login, finalDefer)
    d.addErrback(stun_failed, login, finalDefer)

def stun_success(ip, login, finalDefer):
    dhnio.Dprint(4, 'install.stun_success ' + ip)
    dhnio.WriteFile(settings.ExternalIPFilename(), ip)
    reactor.callLater(0, ProgressMessage, 'your public IP is %s' % ip)
    if DEBUG_PASS_CACHE_CENTRAL_ID:
        reactor.callLater(1, cache_central_id_success, None, ip, login, finalDefer)
        return
    reactor.callLater(1, ProgressMessage, 'downloading central server identity')
    reactor.callLater(2, cache_central_id, ip, login, finalDefer)

def stun_failed(x, login, finalDefer):
    global _RegistrationInProcess
    dhnio.Dprint(4, 'install.stun_failed')
    _RegistrationInProcess = False
    reactor.callLater(0, ProgressMessage, 'connection error')
    reactor.callLater(1, registration_failed, finalDefer)

def cache_central_id(ip, login, finalDefer):
    dhnio.Dprint(4, 'install.cache_central_id')
    res = identitycache.immediatelyCaching(settings.CentralID())
    res.addCallback(cache_central_id_success, ip, login, finalDefer)
    res.addErrback(cache_central_id_failed, ip, login, finalDefer)

def cache_central_id_success(x, ip, login, finalDefer):
    dhnio.Dprint(4, 'install.cache_central_id_success')
    reactor.callLater(1, ProgressMessage, 'making the private key and identity file')
    reactor.callLater(2, make_identity, finalDefer, login, ip, 'upnp-disabled', 'upnp-disabled', 'upnp-disabled')
#    if not settings.enableUPNP():
#        reactor.callLater(1, ProgressMessage, 'making the private key and identity file')
#        reactor.callLater(2, make_identity, finalDefer, login, ip, 'upnp-disabled', 'upnp-disabled', 'upnp-disabled')
#    else:
#        reactor.callLater(1, ProgressMessage, 'configuring UPnP device')
#        reactor.callLater(2, install_upnp, ip, login, finalDefer)

def cache_central_id_failed(x, ip, login, finalDefer):
    global _RegistrationInProcess
    dhnio.Dprint(4, 'install.cache_central_id_failed WARNING')
    _RegistrationInProcess = False
    dhnio.restore_and_remove(settings.LocalIdentityFilename(), True)
    reactor.callLater(0, ProgressMessage, 'connection error')
    reactor.callLater(1, registration_failed, finalDefer)

def install_upnp(ip, login, finalDefer):
    dhnio.Dprint(4, 'install.install_upnp ' + ip)
    successTCP = 'upnp-not-found'
    successSSH = 'upnp-not-found'
    successHTTP = 'upnp-not-found'
    if settings.enableTCP():
        shutdowner.A('block')
        successTCP, tcp_port = run_upnpc.update(settings.getTCPPort())
        shutdowner.A('unblock')
        settings.setTCPPort(tcp_port)
#    if settings.enableSSH():
#        successSSH, ssh_port = run_upnpc.update(settings.getSSHPort())
#        settings.setSSHPort(ssh_port)
    if settings.enableHTTP():
        shutdowner.A('block')
        successHTTP, http_port = run_upnpc.update(settings.getHTTPPort())
        shutdowner.A('unblock')
        settings.setHTTPPort(http_port)
    reactor.callLater(0, ProgressMessage, 'making the private key and identity file')
    reactor.callLater(1, make_identity, finalDefer, login, ip, successTCP, successSSH, successHTTP)

def make_identity(finalDefer, login, ip, successTCP, successSSH, successHTTP):
    dhnio.Dprint(4, 'install.make_identity %s %s ' % (login, ip))
    dhnio.WriteFile(settings.ExternalIPFilename(), ip)
    ident = identity.makeDefaultIdentity(login, ip, successTCP, successSSH, successHTTP)
    misc.setLocalIdentity(ident)
    misc.saveLocalIdentity()
    dhnio.remove_backuped_file(settings.LocalIdentityFilename())
    dhnio.backup_and_remove(settings.LocalIdentityFilename())
#    reactor.callLater(0, ProgressMessage, 'propagate my identity')
#    reactor.callLater(1, send_identity, ip, login, finalDefer, False)
    reactor.callLater(0, ProgressMessage, 'starting transport protocols')
    reactor.callLater(1, install_transports, ip, login, finalDefer)

def inbox_packet(newpacket, proto, host):
    global _WorkingProtocols
    dhnio.Dprint(6, 'install.inbox_packet %s from %s://%s' % (newpacket.Command, proto, host))
    if proto not in _WorkingProtocols:
        _WorkingProtocols.append(proto)
    return True

def install_transports(ip, login, finalDefer):
    global _WorkingProtocols
    dhnio.Dprint(4, 'install.install_transports %s %s ' % (login, ip))
    def _init_callback():
        reactor.callLater(0, ProgressMessage, 'update local identity')
        reactor.callLater(1, update_identity, ip, login, finalDefer)
    _WorkingProtocols = []
    transport_control.AddInboxCallback(inbox_packet)
    transport_control.shutdown().addBoth(
        lambda x: transport_control.init(_init_callback))

def update_identity(ip, login, finalDefer, working_protos=None, waiting=True):
    dhnio.Dprint(4, 'install.update_identity')
    lid = misc.getLocalIdentity()
    if settings.enableCSpace() and settings.getCSpaceKeyID() != '':
        lid.setProtoContact('cspace', 'cspace://'+settings.getCSpaceKeyID())
    if settings.enableQ2Q() and settings.getQ2Qusername() != '' and settings.getQ2Qhost() != '':
        lid.setProtoContact('q2q', 'q2q://'+settings.getQ2Quserathost())
    contacts = lid.getContacts()
    first = lid.getContactProto(0)
    for c in contacts:
        proto, x, x, x = nameurl.UrlParse(c)
        if not transport_control.ProtocolIsSupported(proto):
            dhnio.Dprint(4, 'install.update_identity want to remove %s contact' % proto)
            lid.deleteProtoContact(proto)
    if first and working_protos and len(working_protos) > 0 and first not in working_protos:
        wantedproto = working_protos[0]
        if first != 'q2q' and 'q2q' in working_protos:
            wantedproto = 'q2q'
        if first != 'cspace' and 'cspace' in working_protos:
            wantedproto = 'cspace'
        if first != 'tcp' and 'tcp' in working_protos:
            wantedproto = 'tcp'
        dhnio.Dprint(4, 'install.update_identity want to pop %s contact ' % wantedproto)
        lid.popProtoContact(wantedproto)
    misc.setLocalIdentity(lid)
    misc.saveLocalIdentity()
    identitycache.Remove(lid.getIDURL())
    reactor.callLater(0, ProgressMessage, 'sending your identity')
    reactor.callLater(1, send_identity, ip, login, finalDefer, waiting)

def send_identity(ip, login, finalDefer, waiting):
    def _timeout(finalDefer, DL):
        if not DL.called:
            DL.errback(Exception('failed'))
    dhnio.Dprint(4, 'install.send_identity')
    if DEBUG_PASS_SEND_IDENTITY:
        reactor.callLater(1, send_identity_success, None, ip, login, finalDefer)
    else:
        dl = identitypropagate.SendServers()
        dl.addCallback(send_identity_success, ip, login, finalDefer, waiting)
        dl.addErrback(send_identity_failed, ip, login, finalDefer)
        timeoutCall = reactor.callLater(30, _timeout, finalDefer, dl)

def send_identity_success(x, ip, login, finalDefer, waiting):
    global _Waiting4NameCount
    global _Waiting4NameCall
    dhnio.Dprint(4, 'install.send_identity_success')
    if waiting:
        _Waiting4NameCount = 0
        reactor.callLater(0, ProgressMessage, 'waiting response from identity server')
        _Waiting4NameCall = reactor.callLater(1, waiting4name, ip, login, finalDefer)
        return
    reactor.callLater(0, finish_new_identity, ip, login, finalDefer)

def send_identity_failed(x, ip, login, finalDefer):
    global _RegistrationInProcess
    dhnio.Dprint(4, 'install.send_identity_failed')
    _RegistrationInProcess = False
    reactor.callLater(0, ProgressMessage, 'connection error')
    reactor.callLater(1, registration_failed, finalDefer)

def waiting4name(ip, login, finalDefer):
    global _Waiting4NameCount
    global _Waiting4NameCall
    global _RegistrationInProcess
    dhnio.Dprint(4, 'install.waiting4name ' + str(_Waiting4NameCount))
    url = misc.getLocalIdentity().getIDURL()
    identitycache.scheduleForCaching(url)
    if not identitycache.HasKey(url):
        _Waiting4NameCount += 1
        if _Waiting4NameCount > MAX_WAITING_COUNT:
            _Waiting4NameCount = 0
            reactor.callLater(0, finish_new_identity, ip, login, finalDefer)
            return
        _Waiting4NameCall = reactor.callLater(1, waiting4name, ip, login, finalDefer)
        return
    xmlsrc1 = identitycache.FromCache(url).serialize()
    xmlsrc2 = misc.getLocalIdentity().serialize()
    if xmlsrc1 != xmlsrc2:
        _RegistrationInProcess = False
        _Waiting4NameCount = 0
        #transport_control.shutdown().addBoth(lambda x: finalDefer.callback('exist'))
        finalDefer.callback('exist')
        return
    _Waiting4NameCount = 0
    reactor.callLater(1, finish_new_identity, ip, login, finalDefer)

def finish_new_identity(ip, login, finalDefer):
    dhnio.Dprint(4, 'install.finish_new_identity')
    reactor.callLater(0, registration_done, finalDefer)
#    reactor.callLater(0, ProgressMessage, 'connecting to central server')
#    reactor.callLater(1, connect2central, ip, login, finalDefer)

def connect2central(ip, login, finalDefer):
    dhnio.Dprint(4, 'install.connect2central')
    def control(state, data):
        global _WorkingProtocols
        dhnio.Dprint(6, 'install.connect2central.control %s' % state)
        msg = state
        if state == 'Hello':
            msg = '[Identity] sent'
        elif state == 'HelloAck':
            msg = '[Ack] received'
            firstProto = misc.getLocalIdentity().getContactProto(0)
            if firstProto not in _WorkingProtocols:
                working_protos_copy = list(_WorkingProtocols)
                _WorkingProtocols = []
                identitycache.Clear([settings.CentralID()])
                reactor.callLater(0, ProgressMessage, '[Ack] received')
                reactor.callLater(1, ProgressMessage, 'update local identity')
                reactor.callLater(2, update_identity, ip, login, finalDefer, working_protos_copy)
                return False
        elif state == 'Settings':
            msg = '[Settings] sent'
        elif state == 'SettingsAck':
            msg = '[Ack] received'
            reactor.callLater(1, registration_done, finalDefer)
        elif state == 'RequestSettings':
            msg = '[RequestSettings] sent'
        elif state == 'RequestSettingsAck':
            msg = '[Ack] received'
        elif state == 'RequestSuppliers':
            msg = '[RequestSuppliers] sent'
        elif state == 'ListContacts':
            msg = '[ListContacts] received'
            reactor.callLater(1, registration_done, finalDefer)
        elif state == 'ListContactsError':
            msg = 'incorrect packet [ListContacts] received'
            reactor.callLater(1, registration_failed, finalDefer)
        elif state == 'Failed':
            msg = 'central server not responding'
            reactor.callLater(5, registration_failed, finalDefer)
        #reactor.callLater(0, ProgressMessage, msg)
        ProgressMessage(msg)
        return True
    central_service.SetControlFunc(control)
    central_service.shutdown().addBoth(lambda x: centralservice.init(10))

def registration_done(finalDefer):
    global _RegistrationInProcess
    dhnio.Dprint(4, 'install.registration_done')
    _RegistrationInProcess = False
    if not finalDefer.called:
        finalDefer.callback('success')
    reactor.callLater(1, ProgressMessage, 'registration done')

def registration_failed(finalDefer):
    global _RegistrationInProcess
    dhnio.Dprint(4, 'install.registration_failed')
    _RegistrationInProcess = False
    #transport_control.shutdown().addBoth(lambda x: finalDefer.callback('disconnected'))
    if not finalDefer.called:
        finalDefer.callback('disconnected')
    reactor.callLater(1, ProgressMessage, 'registration failed')

#------------------------------------------------------------------------------

# return the result in the defer.callback (errback never will be called)
# possible values:
#    remote_identity_not_valid,
#    invalid_identity_source
#    invalid_identity_url
#    remote_identity_bad_format
#    incorrect_key,
#    idurl_not_exist,
#    signing_error,
#    signature_not_match
#    central_failed,
#    success
def RecoverExistingUser(idurl, private_key_src):
    global _RegistrationInProcess
    if _RegistrationInProcess:
        dhnio.Dprint(1, 'install.RecoverExistingUser ERROR registration in process')
        return None
    _RegistrationInProcess = True
    dhnio.Dprint(4, 'install.RecoverExistingUser ' + idurl)
    finalDefer = Deferred()
    identitycache.Clear()
    res = dhnnet.getPageTwisted(idurl)
    res.addCallback(_recover, idurl, private_key_src, finalDefer)
    res.addErrback(_idurl_not_exist, finalDefer)
    return finalDefer

def _idurl_not_exist(x, finalDefer):
    global _RegistrationInProcess
    _RegistrationInProcess = False
    finalDefer.callback('idurl_not_exist')

def _recover(identity_src, idurl, private_key_src, finalDefer):
    global _RegistrationInProcess
    dhnio.Dprint(4, 'install._recover')

    xmlsrc = identity_src

    reactor.callLater(0, ProgressMessage, 'verification of the user account')

    dhnio.Dprint(4, 'install._recover will backup and remove ' + settings.KeyFileName())
    dhnio.backup_and_remove(settings.KeyFileName())

    dhnio.Dprint(4, 'install._recover will backup and remove ' + settings.LocalIdentityFilename())
    dhnio.backup_and_remove(settings.LocalIdentityFilename())

    try:
        remote_ident = identity.identity(xmlsrc=xmlsrc)
        local_ident = identity.identity(xmlsrc=xmlsrc)
    except:
        dhnio.Dprint(2, 'install._recover ERROR in the identity.__init__()')
        dhnio.DprintException()
#        dhnio.restore_and_remove(settings.KeyFileName(), True)
#        dhnio.restore_and_remove(settings.LocalIdentityFilename(), True)
        _RegistrationInProcess = False
        finalDefer.callback('remote_identity_bad_format')
        return

    try:
        res = remote_ident.Valid()
    except:
        dhnio.Dprint(2, 'install._recover ERROR in the identity.Valid()')
        dhnio.DprintException()
        res = False
    if not res:
#        dhnio.restore_and_remove(settings.KeyFileName(), True)
#        dhnio.restore_and_remove(settings.LocalIdentityFilename(), True)
        _RegistrationInProcess = False
        finalDefer.callback('remote_identity_not_valid')
        return

    dhnio.Dprint(4, 'install._recover will save the new private key')
    dhnio.WriteFile(settings.KeyFileName(), private_key_src)
    try:
        dhncrypto.InitMyKey()
    except:
        dhnio.Dprint(2, 'install._recover ERROR in the dhncrypto.InitMyKey()')
        dhnio.DprintException()
#        dhnio.restore_and_remove(settings.KeyFileName(), True)
#        dhnio.restore_and_remove(settings.LocalIdentityFilename(), True)
        _RegistrationInProcess = False
        finalDefer.callback('incorrect_key')
        return

    try:
        local_ident.sign()
    except:
        dhnio.Dprint(2, 'install._recover ERROR in the identity.sign()')
        dhnio.DprintException()
#        dhnio.restore_and_remove(settings.KeyFileName(), True)
#        dhnio.restore_and_remove(settings.LocalIdentityFilename(), True)
        _RegistrationInProcess = False
        finalDefer.callback('signing_error')
        return

    if remote_ident.signature != local_ident.signature:
        dhnio.Dprint(2, 'install._recover ERROR signature and private key did not match!!!')
#        dhnio.restore_and_remove(settings.KeyFileName(), True)
#        dhnio.restore_and_remove(settings.LocalIdentityFilename(), True)
        _RegistrationInProcess = False
        finalDefer.callback('signature_not_match')
        return

    misc.setLocalIdentity(local_ident)
    misc.saveLocalIdentity()

    dhnio.WriteFile(settings.UserNameFilename(), misc.getIDName())

    dhnio.remove_backuped_file(settings.KeyFileName())
    dhnio.remove_backuped_file(settings.LocalIdentityFilename())

    dhnio.Dprint(4, 'install._recover Done!')
    reactor.callLater(1, _get_central_id, finalDefer)

def _get_central_id(finalDefer):
    reactor.callLater(0, ProgressMessage, 'receiving the Central server Identity')
    res = identitycache.immediatelyCaching(settings.CentralID())
    res.addCallback(_central_id_success, finalDefer)
    res.addErrback(_central_id_failed, finalDefer)

def _central_id_failed(x, finalDefer):
    global _RegistrationInProcess
    _RegistrationInProcess = False
    dhnio.Dprint(4, 'install._central_id_failed WARNING Local Id cached but Central Id not? ...')
    finalDefer.callback('central_failed')

def _central_id_success(x, finalDefer):
    global _RegistrationInProcess
    _RegistrationInProcess = False
    finalDefer.callback('success')
    reactor.callLater(0, ProgressMessage, 'your account was restored!')

def usage():
    print 'usage:'
    print
    print '    install.py register  <username> [tcp port number]'
    print '    install.py recover   <private-key-filename>'
    print '    install.py local     <username>'
    print


def main():
    if len(sys.argv) < 3:
        usage()
        return

    dhnio.init()
    settings.init()
    dhnio.SetDebug(18)


    def done(x):
        print
        print '!!! DONE !!!'
        print 'result is "%s"' % str(x)
        reactor.stop()
        #os._exit(0)


    def progress(s):
        print '[progress message]:', s

    if sys.argv[1] == 'recover':
        #test recovering
        src = dhnio.ReadTextFile(sys.argv[2])
        try:
            lines = src.split('\n')
            idurl = lines[0]
            txt = '\n'.join(lines[1:])
            fname = nameurl.UrlFilename(idurl)
            newurl = nameurl.FilenameUrl(fname)
            if idurl != newurl:
                idurl = ''
                txt = src
        except:
            idurl = ''
            txt = src
        print 'idurl:', idurl
        res = RecoverExistingUser(idurl, txt)
        res.addCallback(done)
        reactor.run()
        return

    elif sys.argv[1] == 'register':
        #test registering
        SetProgressNotifyCallback(progress)
        if len(sys.argv) > 3:
            tcpPort = int(sys.argv[3])
            settings.setTCPPort(tcpPort)
        print 'TCP port is:', settings.getTCPPort()
        res = RegisterNewUser(sys.argv[2])
        res.addCallback(done)
        reactor.run()
        return

    elif sys.argv[1] == 'local':
#        if len(sys.argv) > 3:
#            httpPort = int(sys.argv[3])
#            settings.setHTTPPort(httpPort)
#        print 'HTTP port is:', settings.getHTTPPort()
        ident = identity.makeDefaultIdentity(sys.argv[2])
        misc.setLocalIdentity(ident)
        misc.saveLocalIdentity()
        return

    usage()



if __name__ == '__main__':
    main()




