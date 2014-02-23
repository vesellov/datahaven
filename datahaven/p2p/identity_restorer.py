#!/usr/bin/env python
#identity_restorer.py
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
    sys.exit('Error initializing twisted.internet.reactor in identity_restorer.py')
from twisted.internet.defer import Deferred, DeferredList, maybeDeferred
from twisted.internet.task import LoopingCall


from lib.automat import Automat
import lib.dhnio as dhnio
import lib.misc as misc
import lib.settings as settings
import lib.identitycache as identitycache
import lib.identity as identity
import lib.dhncrypto as dhncrypto
import lib.dhnnet as dhnnet


import installer
import lib.automats as automats

import webcontrol

_IdentityRestorer = None
_WorkingIDURL = ''
_WorkingKey = ''

#------------------------------------------------------------------------------ 

def A(event=None, arg=None):
    global _IdentityRestorer
    if _IdentityRestorer is None:
        _IdentityRestorer = IdentityRestorer('identity_restorer', 'READY', 2)
    if event is not None:
        _IdentityRestorer.automat(event, arg)
    return _IdentityRestorer


class IdentityRestorer(Automat):
    MESSAGES = {
        'MSG_01':   ['download central server identity'], 
        'MSG_02':   ['network connection failed', 'red'],
        'MSG_03':   ['download user identity'],
        'MSG_04':   ['user identity not exist', 'red'],
        'MSG_05':   ['verifying user identity and private key'],
        'MSG_06':   ['your account were restored!', 'green'], }
    
    def msg(self, arg): 
        msg = self.MESSAGES.get(arg, ['', 'black'])
        text = msg[0]
        color = 'black'
        if len(msg) == 2:
            color = msg[1]
        return text, color
    
    def state_changed(self, oldstate, newstate):
        automats.set_global_state('ID_RESTORE ' + newstate)
        installer.A('identity_restorer.state', newstate)

    def A(self, event, arg):
        #---READY---
        if self.state is 'READY':
            if event == 'start' :
                self.state = 'CENTRAL_ID'
                self.doPrint(self.msg('MSG_01'))
                self.doSetWorkingIDURL(arg)
                self.doSetWorkingKey(arg)
                self.doRequestCentralIdentity(arg)
        #---CENTRAL_ID---
        elif self.state is 'CENTRAL_ID':
            if event == 'central-id-failed' :
                self.state = 'READY'
                self.doPrint(self.msg('MSG_02'))
                self.doClearWorkingIDURL(arg)
                self.doClearWorkingKey(arg)
            elif event == 'central-id-received' :
                self.state = 'MY_ID'
                self.doPrint(self.msg('MSG_03'))
                self.doRequestMyIdentity(arg)
        #---MY_ID---
        elif self.state is 'MY_ID':
            if event == 'my-id-failed' :
                self.state = 'READY'
                self.doPrint(self.msg('MSG_04'))
                self.doClearWorkingIDURL(arg)
                self.doClearWorkingKey(arg)
            elif event == 'my-id-received' :
                self.state = 'WORK'
                self.doPrint(self.msg('MSG_05'))
                self.doVerifyAndRestore(arg)
        #---WORK---
        elif self.state is 'WORK':
            if event == 'restore-failed' :
                self.state = 'READY'
                self.doPrint(arg)
                self.doClearWorkingIDURL(arg)
                self.doClearWorkingKey(arg)
            elif event == 'restore-success' :
                self.state = 'RESTORED!'
                self.doPrint(self.msg('MSG_06'))
                self.doRestoreSave(arg)
        #---DONE---
        elif self.state is 'DONE':
            pass
        #---RESTORED!---
        elif self.state is 'RESTORED!':
            if event == 'start' :
                self.state = 'DONE'

    def doSetWorkingIDURL(self, arg):
        global _WorkingIDURL
        _WorkingIDURL = arg['idurl']
        
    def doSetWorkingKey(self, arg):
        global _WorkingKey
        _WorkingKey = arg['keysrc']

    def doClearWorkingIDURL(self, arg):
        global _WorkingIDURL
        _WorkingIDURL = ''
        
    def doClearWorkingKey(self, arg):
        global _WorkingKey
        _WorkingKey = ''

    def doRequestCentralIdentity(self, arg):
        dhnio.Dprint(4, 'identity_restorer.doRequestCentralIdentity')
        identitycache.immediatelyCaching(settings.CentralID()).addCallbacks(
            lambda x: self.automat('central-id-received'),
            lambda x: self.automat('central-id-failed'))
        
    def doRequestMyIdentity(self, arg):
        global _WorkingIDURL
        idurl = _WorkingIDURL
        dhnio.Dprint(4, 'identity_restorer.doRequestMyIdentity %s' % idurl)
        dhnnet.getPageTwisted(idurl).addCallbacks(
            lambda src: self.automat('my-id-received', src),
            lambda err: self.automat('my-id-failed', err))
    
    def doVerifyAndRestore(self, arg):
        global _WorkingKey
        dhnio.Dprint(4, 'identity_restorer.doVerifyAndRestore')
    
        remote_identity_src = arg

        if os.path.isfile(settings.KeyFileName()):
            dhnio.Dprint(4, 'identity_restorer.doVerifyAndRestore will backup and remove ' + settings.KeyFileName())
            dhnio.backup_and_remove(settings.KeyFileName())

        if os.path.isfile(settings.LocalIdentityFilename()):    
            dhnio.Dprint(4, 'identity_restorer.doVerifyAndRestore will backup and remove ' + settings.LocalIdentityFilename())
            dhnio.backup_and_remove(settings.LocalIdentityFilename())
    
        try:
            remote_ident = identity.identity(xmlsrc = remote_identity_src)
            local_ident = identity.identity(xmlsrc = remote_identity_src)
        except:
            # dhnio.DprintException()
            reactor.callLater(0.5, self.automat, 'restore-failed', ('remote identity have incorrect format', 'red'))
            return
    
        try:
            res = remote_ident.Valid()
        except:
            dhnio.DprintException()
            res = False
        if not res:
            reactor.callLater(0.5, self.automat, 'restore-failed', ('remote identity is not valid', 'red'))
            return
    
        dhncrypto.ForgetMyKey()
        dhnio.WriteFile(settings.KeyFileName(), _WorkingKey)
        try:
            dhncrypto.InitMyKey()
        except:
            dhncrypto.ForgetMyKey()
            # dhnio.DprintException()
            try:
                os.remove(settings.KeyFileName())
            except:
                pass
            reactor.callLater(0.5, self.automat, 'restore-failed', ('private key is not valid', 'red'))
            return
    
        try:
            local_ident.sign()
        except:
            # dhnio.DprintException()
            reactor.callLater(0.5, self.automat, 'restore-failed', ('error while signing identity', 'red'))
            return
    
        if remote_ident.signature != local_ident.signature:
            reactor.callLater(0.5, self.automat, 'restore-failed', ('signature did not match', 'red'))
            return
    
        misc.setLocalIdentity(local_ident)
        misc.saveLocalIdentity()
    
        dhnio.WriteFile(settings.UserNameFilename(), misc.getIDName())
    
        if os.path.isfile(settings.KeyFileName()+'.backup'):
            dhnio.Dprint(4, 'identity_restorer.doVerifyAndRestore will remove backup file for ' + settings.KeyFileName())
            dhnio.remove_backuped_file(settings.KeyFileName())

        if os.path.isfile(settings.LocalIdentityFilename()+'.backup'):
            dhnio.Dprint(4, 'identity_restorer.doVerifyAndRestore will remove backup file for ' + settings.LocalIdentityFilename())
            dhnio.remove_backuped_file(settings.LocalIdentityFilename())

        reactor.callLater(0.5, self.automat, 'restore-success')
        
    def doRestoreSave(self, arg):
        settings.uconfig().set('central-settings.desired-suppliers', '0')
        settings.uconfig().set('central-settings.needed-megabytes', '0Mb')
        settings.uconfig().set('central-settings.shared-megabytes', '0Mb')
        settings.uconfig().update()

    def doPrint(self, arg):
        installer.A().event('print', arg)









