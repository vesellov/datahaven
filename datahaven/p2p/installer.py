#!/usr/bin/env python
#installer.py
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
    sys.exit('Error initializing twisted.internet.reactor in installer.py')
from twisted.internet.defer import Deferred, maybeDeferred
from twisted.internet.task import LoopingCall


import lib.dhnio as dhnio
import lib.misc as misc
import lib.nameurl as nameurl
import lib.packetid as packetid
import lib.settings as settings
import lib.contacts as contacts
import lib.transport_control as transport_control
import lib.diskusage as diskusage
from lib.automat import Automat


import initializer
import p2p_connector
import identity_registrator
import identity_restorer
import install_wizard
import lib.automats as automats

import dhninit
import dhnupdate
import identitypropagate
import webcontrol


_Installer = None

#------------------------------------------------------------------------------ 

def A(event=None, arg=None):
    global _Installer
    if _Installer is None:
        _Installer = Installer('installer', 'AT_STARTUP', 2)
    if event is not None:
        _Installer.automat(event, arg)
    return _Installer


class Installer(Automat):
    output = {}
    RECOVER_RESULTS = {
        'remote_identity_not_valid':  ('remote Identity is not valid', 'red'),
        'invalid_identity_source':    ('incorrect source of the Identity file', 'red'),
        'invalid_identity_url':       ('incorrect Identity file location', 'red'),
        'remote_identity_bad_format': ('incorrect format of the Identity file', 'red'),
        'incorrect_key':              ('Private Key is not valid', 'red'),
        'idurl_not_exist':            ('Identity URL address not exist or not reachable at this moment', 'blue'),
        'signing_error':              ('unable to sign the local Identity file', 'red'),
        'signature_not_match':        ('remote Identity and Private Key did not match', 'red'),
        'central_failed':             ('unable to connect to the Central server, try again later', 'blue'),
        'success':                    ('account restored!', 'green'), }

    def getOutput(self, state=None):
        if state is None:
            state = self.state
        return self.output.get(state, {})

    def init(self):
        self.flagCmdLine = False
        
    def state_changed(self, oldstate, newstate):
        automats.set_global_state('INSTALL ' + newstate)
        initializer.A('installer.state', newstate)

    def A(self, event, arg):
        #---AT_STARTUP---
        if self.state is 'AT_STARTUP':
            if event == 'init' :
                self.state = 'WHAT_TO_DO?'
                self.flagCmdLine=False
                self.doIncreaseDebugLevel(arg)
            elif event == 'register-cmd-line' :
                self.state = 'REGISTER'
                self.flagCmdLine=True
                self.doIncreaseDebugLevel(arg)
                identity_registrator.A('start', arg)
            elif event == 'recover-cmd-line' :
                self.state = 'RECOVER'
                self.flagCmdLine=True
                self.doIncreaseDebugLevel(arg)
                identity_restorer.A('start', arg)
        #---WHAT_TO_DO?---
        elif self.state is 'WHAT_TO_DO?':
            if event == 'register-selected' :
                self.state = 'INPUT_NAME'
                self.doUpdate(arg)
            elif event == 'recover-selected' :
                self.state = 'LOAD_KEY'
                self.doUpdate(arg)
        #---INPUT_NAME---
        elif self.state is 'INPUT_NAME':
            if event == 'back' :
                self.state = 'WHAT_TO_DO?'
                self.doClearOutput(arg)
                self.doUpdate(arg)
            elif event == 'register-start' and self.isNameValid(arg) :
                self.state = 'REGISTER'
                self.doClearOutput(arg)
                identity_registrator.A('start', arg)
                self.doUpdate(arg)
            elif event == 'register-start' and not self.isNameValid(arg) :
                self.doClearOutput(arg)
                self.doPrintIncorrectName(arg)
                self.doUpdate(arg)
            elif event == 'print' :
                self.doPrint(arg)
                self.doUpdate(arg)
        #---LOAD_KEY---
        elif self.state is 'LOAD_KEY':
            if event == 'back' :
                self.state = 'WHAT_TO_DO?'
                self.doClearOutput(arg)
                self.doUpdate(arg)
            elif event == 'load-from-file' :
                self.doReadKey(arg)
                self.doUpdate(arg)
            elif event == 'paste-from-clipboard' :
                self.doPasteKey(arg)
                self.doUpdate(arg)
            elif event == 'restore-start' :
                self.state = 'RECOVER'
                self.doClearOutput(arg)
                identity_restorer.A('start', arg)
                self.doUpdate(arg)
            elif event == 'print' :
                self.doPrint(arg)
                self.doUpdate(arg)
        #---REGISTER---
        elif self.state is 'REGISTER':
            if event == 'print' :
                self.doPrint(arg)
                self.doUpdate(arg)
            elif ( event == 'identity_registrator.state' and arg is 'READY' ) and not self.flagCmdLine :
                self.state = 'INPUT_NAME'
                self.doUpdate(arg)
            elif ( event == 'identity_registrator.state' and arg in [ 'READY' , 'REGISTERED' ] ) and self.flagCmdLine :
                self.state = 'DONE'
                self.doUpdate(arg)
            elif ( event == 'identity_registrator.state' and arg is 'REGISTERED' ) and not self.flagCmdLine :
                self.state = 'AUTHORIZED'
                self.doUpdate(arg)
        #---AUTHORIZED---
        elif self.state is 'AUTHORIZED':
            if event == 'next' :
                self.state = 'WIZARD'
                self.doUpdate(arg)
            elif event == 'print' :
                self.doPrint(arg)
                self.doUpdate(arg)
        #---RECOVER---
        elif self.state is 'RECOVER':
            if event == 'print' :
                self.doPrint(arg)
                self.doUpdate(arg)
            elif ( event == 'identity_restorer.state' and arg is 'READY' ) and not self.flagCmdLine :
                self.state = 'LOAD_KEY'
                self.doUpdate(arg)
            elif ( event == 'identity_restorer.state' and arg is 'DONE' ) or ( ( event == 'identity_restorer.state' and arg in [ 'RESTORED!' , 'READY' ] ) and self.flagCmdLine ) :
                self.state = 'DONE'
                self.doUpdate(arg)
        #---DONE---
        elif self.state is 'DONE':
            if event == 'print' :
                self.doPrint(arg)
                self.doUpdate(arg)
        #---WIZARD---
        elif self.state is 'WIZARD':
            if ( event == 'install_wizard.state' and arg is 'DONE' ) :
                self.state = 'DONE'
                self.doUpdate(arg)
            elif event == 'print' :
                self.doPrint(arg)
                self.doUpdate(arg)

    def isNameValid(self, arg):
        if not misc.ValidUserName(arg):
            return False
        return True

    def doClearOutput(self, arg):
        # dhnio.Dprint(4, 'installer.doClearOutput')
        for state in self.output.keys():
            self.output[state] = {'data': [('', 'black')]}

    def doPrint(self, arg):
        dhnio.Dprint(8, 'installer.doPrint %s %s' % (self.state, str(arg)))
        if not self.output.has_key(self.state):
            self.output[self.state] = {'data': [('', 'black')]}
        if arg is None:
            self.output[self.state]['data'] = [('', 'black')]
        else:
            self.output[self.state]['data'].append(arg)
        if self.flagCmdLine:
            ch = '+'
            if arg[1] == 'red':
                ch = '!'
            dhnio.Dprint(0, '  %s %s' % (ch, arg[0]))

    def doPrintIncorrectName(self, arg):
        text, color = ('incorrect user name', 'red') 
        if not self.output.has_key(self.state):
            self.output[self.state] = {'data': [('', 'black')]}
        self.output[self.state]['data'].append((text, color))
        # dhnio.Dprint(0, '  [%s]' % text)

    def doUpdate(self, arg):
        # dhnio.Dprint(4, 'installer.doUpdate')
        reactor.callLater(0, webcontrol.OnUpdateInstallPage)

    def doReadKey(self, arg):
        dhnio.Dprint(2, 'installer.doReadKey arg=[%s]' % str(arg))
        src = dhnio.ReadBinaryFile(arg)
        if len(src) > 1024*10:
            self.doPrint(('file is too big for private key', 'red'))
            return

        try:
            lines = src.split('\n')
            idurl = lines[0]
            keysrc = '\n'.join(lines[1:])
            if idurl != nameurl.FilenameUrl(nameurl.UrlFilename(idurl)):
                idurl = ''
                keysrc = src
        except:
            dhnio.DprintException()
            idurl = ''
            keysrc = src

        if not self.output.has_key(self.state):
            self.output[self.state] = {'data': [('', 'black')]}
        self.output[self.state]['idurl'] = idurl
        self.output[self.state]['keysrc'] = keysrc
        
    def doPasteKey(self, arg):
        src = misc.getClipboardText()
        try:
            lines = src.split('\n')
            idurl = lines[0]
            keysrc = '\n'.join(lines[1:])
            if idurl != nameurl.FilenameUrl(nameurl.UrlFilename(idurl)):
                idurl = ''
                keysrc = src
        except:
            dhnio.DprintException()
            idurl = ''
            keysrc = src
        if not self.output.has_key(self.state):
            self.output[self.state] = {'data': [('', 'black')]}
        self.output[self.state]['idurl'] = idurl

    def doIncreaseDebugLevel(self, arg):
        if self.flagCmdLine:
            dhnio.SetDebug(0)
        else:
            dhnio.SetDebug(14)


