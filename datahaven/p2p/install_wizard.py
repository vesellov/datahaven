#!/usr/bin/env python
#install_wizard.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#

import sys
try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in install_wizard.py')

import lib.dhnio as dhnio
import lib.settings as settings
from lib.automat import Automat

import installer
import webcontrol
import dhnupdate

_InstallWizard = None
def A(event=None, arg=None):
    global _InstallWizard
    if _InstallWizard is None:
        _InstallWizard = InstallWizard('install_wizard', 'READY', 2)
    if event is not None:
        _InstallWizard.automat(event, arg)
    return _InstallWizard

# DataHaven.NET install_wizard() Automat
class InstallWizard(Automat):
    role_args = None
    role = None

    def state_changed(self, oldstate, newstate):
        reactor.callLater(0, webcontrol.OnUpdateInstallPage)
        installer.A('install_wizard.state', newstate)

    def A(self, event, arg):
        #---READY---
        if self.state is 'READY':
            if event == 'select-donator' :
                self.state = 'DONATOR'
                self.doSaveRole(arg)
            elif event == 'select-free-backups' :
                self.state = 'FREE_BACKUPS'
                self.doSaveRole(arg)
            elif event == 'select-beta-test' :
                self.state = 'BETA_TEST'
                self.doSaveRole(arg)
            elif event == 'select-secure' :
                self.state = 'MOST_SECURE'
                self.doSaveRole(arg)
            elif event == 'select-try-it' :
                self.state = 'JUST_TRY_IT'
                self.doSaveRole(arg)
        #---MOST_SECURE---
        elif self.state is 'MOST_SECURE':
            if event == 'back' :
                self.state = 'READY'
            elif event == 'next' :
                self.state = 'STORAGE'
                self.doSaveParams(arg)
        #---FREE_BACKUPS---
        elif self.state is 'FREE_BACKUPS':
            if event == 'back' :
                self.state = 'READY'
            elif event == 'next' :
                self.state = 'STORAGE'
                self.doSaveParams(arg)
        #---BETA_TEST---
        elif self.state is 'BETA_TEST':
            if event == 'back' :
                self.state = 'READY'
            elif event == 'next' :
                self.state = 'STORAGE'
                self.doSaveParams(arg)
        #---DONATOR---
        elif self.state is 'DONATOR':
            if event == 'back' :
                self.state = 'READY'
            elif event == 'next' :
                self.state = 'STORAGE'
        #---JUST_TRY_IT---
        elif self.state is 'JUST_TRY_IT':
            if event == 'back' :
                self.state = 'READY'
            elif event == 'next' :
                self.state = 'LAST_PAGE'
        #---STORAGE---
        elif self.state is 'STORAGE':
            if event == 'next' :
                self.state = 'CONTACTS'
                self.doSaveStorage(arg)
            elif event == 'back' and self.isRoleSecure(arg) :
                self.state = 'MOST_SECURE'
            elif event == 'back' and self.isRoleDonator(arg) :
                self.state = 'DONATOR'
            elif event == 'back' and self.isRoleFreeBackups(arg) :
                self.state = 'FREE_BACKUPS'
            elif event == 'back' and self.isRoleBetaTest(arg) :
                self.state = 'BETA_TEST'
        #---CONTACTS---
        elif self.state is 'CONTACTS':
            if event == 'back' :
                self.state = 'STORAGE'
            elif event == 'next' :
                self.state = 'UPDATES'
                self.doSaveContacts(arg)
        #---UPDATES---
        elif self.state is 'UPDATES':
            if event == 'back' :
                self.state = 'CONTACTS'
            elif event == 'next' :
                self.state = 'LAST_PAGE'
                self.doSaveUpdates(arg)
        #---DONE---
        elif self.state is 'DONE':
            if event == 'back' :
                self.state = 'LAST_PAGE'
        #---LAST_PAGE---
        elif self.state is 'LAST_PAGE':
            if event == 'next' :
                self.state = 'DONE'

    def isRoleSecure(self, arg):
        return self.role == 'MOST_SECURE'

    def isRoleFreeBackups(self, arg):
        return self.role == 'FREE_BACKUPS'

    def isRoleBetaTest(self, arg):
        return self.role == 'BETA_TEST'

    def isRoleDonator(self, arg):
        return self.role == 'DONATOR'

    def doSaveRole(self, arg):
        self.role = self.state

    def doSaveParams(self, arg):
        self.role_args = arg

    def doSaveStorage(self, arg):
        needed = arg.get('needed', '')
        donated = arg.get('donated', '')
        customersdir = arg.get('customersdir', '')
        localbackupsdir = arg.get('localbackupsdir', '')
        restoredir = arg.get('restoredir', '')
        if needed:
            settings.uconfig().set('central-settings.needed-megabytes', needed+'MB')
        if donated:
            settings.uconfig().set('central-settings.shared-megabytes', donated+'MB')
        if customersdir:
            settings.uconfig().set('folder.folder-customers', customersdir)
        if localbackupsdir:
            settings.uconfig().set('folder.folder-backups', localbackupsdir)
        if restoredir:
            settings.uconfig().set('folder.folder-restore', restoredir)
        if self.role == 'MOST_SECURE':
            settings.uconfig().set('general.general-local-backups-enable', 'False')
        settings.uconfig().update()

    def doSaveContacts(self, arg):
        settings.uconfig().set('emergency.emergency-email', arg.get('email', '').strip())
        settings.uconfig().set('personal.personal-name', arg.get('name', ''))
        settings.uconfig().set('personal.personal-surname', arg.get('surname', ''))
        settings.uconfig().set('personal.personal-nickname', arg.get('nickname', ''))
        if self.role == 'BETA_TEST':
            settings.uconfig().set('personal.personal-betatester', 'True')
            if self.role_args and self.role_args.get('development', '').lower() == 'true':
                settings.uconfig().set("logs.debug-level", '10')
                settings.uconfig().set("logs.stream-enable", 'True')
                dhnio.SetDebug(10)
        settings.uconfig().update()

    def doSaveUpdates(self, arg):
        shedule = dhnupdate.blank_shedule(arg)
        settings.uconfig().set('updates.updates-shedule', dhnupdate.shedule_to_string(shedule))
        settings.uconfig().update()




