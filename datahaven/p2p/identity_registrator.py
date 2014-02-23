#!/usr/bin/env python
#identity_registrator.py
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

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in identity_registrator.py')
from twisted.internet.defer import Deferred, DeferredList, fail


from lib.automat import Automat
import lib.dhnio as dhnio
import lib.misc as misc
import lib.nameurl as nameurl
import lib.settings as settings
import lib.identitycache as identitycache
import lib.stun as stun
import lib.identity as identity
import lib.dhncrypto as dhncrypto
import lib.tmpfile as tmpfile
import lib.dhnnet as dhnnet
import lib.transport_control as transport_control
import lib.transport_tcp as transport_tcp
if transport_control._TransportCSpaceEnable:
    import lib.transport_cspace as transport_cspace


import shutdowner
import installer
import lib.automats as automats

import webcontrol

_IdentityRegistrator = None
_NewIdentity = None

#------------------------------------------------------------------------------ 

def A(event=None, arg=None):
    global _IdentityRegistrator
    if _IdentityRegistrator is None:
        _IdentityRegistrator = IdentityRegistrator('identity_registrator', 'READY', 2)
    if event is not None:
        _IdentityRegistrator.automat(event, arg)
    return _IdentityRegistrator


class IdentityRegistrator(Automat):
    debug_skip_registration = False
    timers = {'timer-30sec': (30, ['REQUEST_MY_ID']),}
    MESSAGES = {
        'MSG_01': ['checking account name'],
        'MSG_02': ['user %(login)s already exist', 'red'],
        'MSG_03': ['checking network configuration'],
        'MSG_04': ['local IP is %(localip)s'],
        'MSG_05': ['network connection failed', 'red'],
        'MSG_06': ['external IP is %(externalip)s'],
        'MSG_07': ['network connection error', 'red'],
        'MSG_08': ['sending my identity to the identity server'],
        'MSG_09': ['connection error while sending my identity', 'red'],
        'MSG_10': ['verifying my identity on the server'],
        'MSG_11': ['time out connection to the identity server', 'red'],
        'MSG_12': ['verifying my identity'],
        'MSG_13': ['identity verification failed', 'red'],
        'MSG_14': ['new user %(login)s registered successfully!', 'green'], 
        'MSG_15': ['connecting to the identity server'], 
        'MSG_16': ['connection to the identity server was failed', 'red'], 
        'MSG_17': ['CSpace initialization'], }

    def msg(self, arg): 
        msg = self.MESSAGES.get(arg, ['', 'black'])
        text = msg[0] % {
            'login': dhnio.ReadTextFile(settings.UserNameFilename()),
            'externalip': dhnio.ReadTextFile(settings.ExternalIPFilename()),
            'localip': dhnio.ReadTextFile(settings.LocalIPFilename()),}
        color = 'black'
        if len(msg) == 2:
            color = msg[1]
        return text, color

    def state_changed(self, oldstate, newstate):
        automats.set_global_state('ID_REGISTER ' + newstate)
        installer.A('identity_registrator.state', newstate)

#                if self.debug_skip_registration:
#                    installer.A('print', self.msg('MSG_14'))
#                    self.state = 'REGISTERED'
#                    return

    def A(self, event, arg):
        #---READY---
        if self.state is 'READY':
            if event == 'start' :
                self.state = 'ID_SERVER'
                self.doPrint(self.msg('MSG_15'))
                self.doSaveMyName(arg)
                self.doPingIdentityServer(arg)
        #---ID_SERVER---
        elif self.state is 'ID_SERVER':
            if event == 'id-server-response' :
                self.state = 'USER_NAME'
                self.doPrint(self.msg('MSG_01'))
                self.doRequestMyIdentity(arg)
            elif event == 'id-server-failed' :
                self.state = 'READY'
                self.doPrint(self.msg('MSG_16'))
        #---USER_NAME---
        elif self.state is 'USER_NAME':
            if event == 'my-id-exist' :
                self.state = 'READY'
                self.doPrint(self.msg('MSG_02'))
            elif event == 'my-id-not-exist' :
                self.state = 'LOCAL_IP'
                self.doPrint(self.msg('MSG_03'))
                self.doDetectLocalIP(arg)
        #---LOCAL_IP---
        elif self.state is 'LOCAL_IP':
            if event == 'local-ip-detected' :
                self.state = 'CSPACE'
                self.doPrint(self.msg('MSG_17'))
                self.doCSpaceInit(arg)
        #---EXTERNAL_IP---
        elif self.state is 'EXTERNAL_IP':
            if event == 'stun-success' :
                self.state = 'CENTRAL_ID'
                self.doPrint(self.msg('MSG_06'))
                self.doRequestCentralIdentity(arg)
            elif event == 'stun-failed' :
                self.state = 'READY'
                self.doPrint(self.msg('MSG_05'))
        #---CENTRAL_ID---
        elif self.state is 'CENTRAL_ID':
            if event == 'central-id-success' :
                self.state = 'SEND_MY_ID'
                self.doPrint(self.msg('MSG_08'))
                self.doCreateMyIdentity(arg)
                self.doSendMyIdentity(arg)
            elif event == 'central-id-failed' :
                self.state = 'READY'
                self.doPrint(self.msg('MSG_07'))
        #---SEND_MY_ID---
        elif self.state is 'SEND_MY_ID':
            if event == 'my-id-sent' :
                self.state = 'REQUEST_MY_ID'
                self.doPrint(self.msg('MSG_10'))
                self.doRequestMyIdentity(arg)
            elif event == 'my-id-failed' :
                self.state = 'READY'
                self.doPrint(self.msg('MSG_09'))
        #---REQUEST_MY_ID---
        elif self.state is 'REQUEST_MY_ID':
            if event == 'my-id-exist' and self.isMyIdentityValid(arg) :
                self.state = 'REGISTERED'
                self.doPrint(self.msg('MSG_14'))
                self.doSaveMyIdentity(arg)
            elif event == 'my-id-exist' and not self.isMyIdentityValid(arg) :
                self.state = 'READY'
                self.doPrint(self.msg('MSG_13'))
            elif event == 'my-id-not-exist' :
                self.doWait5secAndRequestMyIdentity(arg)
            elif event == 'timer-30sec' :
                self.state = 'READY'
                self.doPrint(self.msg('MSG_11'))
        #---REGISTERED---
        elif self.state is 'REGISTERED':
            pass
        #---CSPACE---
        elif self.state is 'CSPACE':
            if event == 'cspace-done' :
                self.state = 'EXTERNAL_IP'
                self.doPrint(self.msg('MSG_04'))
                self.doStunExternalIP(arg)

    def isMyIdentityValid(self, arg):
        global _NewIdentity
        return _NewIdentity.serialize() == arg

    def doSaveMyName(self, arg):
        login = arg
        dhnio.Dprint(4, 'identity_registrator.doSaveMyName [%s]' % login)
        dhnio.WriteFile(settings.UserNameFilename(), login)
        webcontrol.installing_process_str = ''

    def doPingIdentityServer(self, arg):
        server_url = nameurl.UrlMake('http', settings.IdentityServerName())
        dhnnet.getPageTwisted(server_url).addCallbacks(
            lambda src: self.automat('id-server-response', src),
            lambda err: self.automat('id-server-failed', err))

    def doRequestMyIdentity(self, arg):
        login = dhnio.ReadTextFile(settings.UserNameFilename())
        idurl = nameurl.UrlMake('http', settings.IdentityServerName(), '', login+'.xml')
        dhnio.Dprint(4, 'identity_registrator.doRequestMyIdentity login=%s, idurl=%s' % (login, idurl))
        dhnnet.getPageTwisted(idurl).addCallbacks(
            lambda src: self.automat('my-id-exist', src),
            lambda err: self.automat('my-id-not-exist', err))
        
    def doDetectLocalIP(self, arg):
        localip = dhnnet.getLocalIp()
        dhnio.WriteFile(settings.LocalIPFilename(), localip)
        dhnio.Dprint(4, 'identity_registrator.doDetectLocalIP [%s]' % localip)
        self.automat('local-ip-detected')
        
    def doStunExternalIP(self, arg):
        dhnio.Dprint(4, 'identity_registrator.doStunExternalIP')
        def save(ip):
            dhnio.Dprint(4, 'identity_registrator.doStunExternalIP.save [%s]' % ip)
            dhnio.WriteFile(settings.ExternalIPFilename(), ip)
            self.automat('stun-success', ip)
        stun.stunExternalIP(
            close_listener=False, 
            internal_port=settings.getUDPPort(), 
            block_marker=shutdowner.A).addCallbacks(
                save, lambda x: self.automat('stun-failed'))

    def doRequestCentralIdentity(self, arg):
        identitycache.immediatelyCaching(settings.CentralID()).addCallbacks(
            lambda x: self.automat('central-id-success'),
            lambda x: self.automat('central-id-failed'))
        
    def doCreateMyIdentity(self, arg):
        CreateNewIdentity()
        
    def doSendMyIdentity(self, arg):
        dl = SendNewIdentity()
        dl.addCallback(lambda x: self.automat('my-id-sent'))
        dl.addErrback(lambda x: self.automat('my-id-failed'))
        
    def doSaveMyIdentity(self, arg):
        global _NewIdentity
        misc.setLocalIdentity(_NewIdentity)
        misc.saveLocalIdentity()
        
    def doWait5secAndRequestMyIdentity(self, arg):
        reactor.callLater(5, self.doRequestMyIdentity, None)

    def doCSpaceInit(self, arg):
        if transport_control._TransportCSpaceEnable and settings.enableCSpace():
            def _cspace_done(x):
                reactor.addSystemEventTrigger('before', 'shutdown', transport_cspace.shutdown_final)
                if transport_cspace.registered():
                    settings.setCSpaceKeyID(transport_cspace.keyID())
                self.automat('cspace-done', transport_cspace.A().state)
            transport_cspace.init().addBoth(_cspace_done)
        else:
            self.automat('cspace-done', None)

    def doPrint(self, arg):
        installer.A().event('print', arg)
        
        

def CreateNewIdentity():
    global _NewIdentity
    
    dhncrypto.InitMyKey()
    misc.loadLocalIdentity()
    if misc.isLocalIdentityReady():
        try:
            lid = misc.getLocalIdentity()
            lid.sign()
            # misc.setLocalIdentity(lid)
            # misc.saveLocalIdentity()
            valid = lid.Valid()
        except:
            valid = False
            dhnio.DprintException()
        if valid:
            _NewIdentity = lid
            return
        dhnio.Dprint(2, 'identity_registrator.CreateNewIdentity existing local identity is not VALID')

    login = dhnio.ReadTextFile(settings.UserNameFilename())
    externalIP = dhnio.ReadTextFile(settings.ExternalIPFilename())
    localIP = dhnio.ReadTextFile(settings.LocalIPFilename())

    dhnio.Dprint(4, 'identity_registrator.CreateNewIdentity %s %s ' % (login, externalIP))
    
    idurl = 'http://'+settings.DefaultIdentityServer()+'/'+login.lower()+'.xml'
    ident = identity.identity( )
    ident.sources.append(idurl)

    cdict = {}
    if settings.enableTCP():
        cdict['tcp'] = 'tcp://'+externalIP+':'+settings.getTCPPort()
    if settings.enableCSpace() and transport_control._TransportCSpaceEnable:
        cdict['cspace'] = 'cspace://'
        if settings.getCSpaceKeyID() != '':
            cdict['cspace'] += settings.getCSpaceKeyID()
    if settings.enableUDP() and transport_control._TransportUDPEnable:
        if stun.getUDPClient() is not None:
            if stun.getUDPClient().externalAddress is not None: # _altStunAddress
                cdict['udp'] = 'udp://'+stun.getUDPClient().externalAddress[0]+':'+str(stun.getUDPClient().externalAddress[1])
        
    for c in misc.validTransports:
        if cdict.has_key(c):
            ident.contacts.append(cdict[c])

    ident.publickey = dhncrypto.MyPublicKey()
    ident.date = time.ctime() #time.strftime('%b %d, %Y')

    revnum = dhnio.ReadTextFile(settings.RevisionNumberFile()).strip()
    repo, location = misc.ReadRepoLocation()
    ident.version = (revnum.strip() + ' ' + repo.strip() + ' ' + dhnio.osinfo().strip()).strip()

    ident.sign()
    
    dhnio.WriteFile(settings.LocalIdentityFilename()+'.new', ident.serialize())
    
    _NewIdentity = ident
    

def SendNewIdentity():
    global _NewIdentity
    
    if _NewIdentity is None:
        return fail(Exception(None))
#        d = Deferred()
#        d.errback(Exception(''))
#        return DeferredList([d], fireOnOneErrback=True)
    
    dhnio.Dprint(4, 'identity_registrator.SendNewIdentity ')

    sendfile, sendfilename = tmpfile.make("propagate")
    os.close(sendfile)
    src = _NewIdentity.serialize()
    dhnio.WriteFile(sendfilename, src)

    dlist = []
    for idurl in _NewIdentity.sources:            
        # sources for out identity are servers we need to send to
        protocol, host, port, filename = nameurl.UrlParse(idurl)
        port = settings.IdentityServerPort()
        d = Deferred()
        transport_tcp.sendsingle(sendfilename, host, port, do_status_report=False, result_defer=d, description='Identity')
        dlist.append(d) 

    dl = DeferredList(dlist)
    return dl
                
        
        


