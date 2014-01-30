#!/usr/bin/python
#summary.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#


import os
import sys
import time


try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in summary.py')


import lib.settings as settings
import lib.misc as misc
import lib.diskspace as diskspace
import lib.transport_control as transport_control
import lib.contacts as contacts
import lib.dhnio as dhnio


import backup_db


class _SummaryInfo:
    def __init__(self, guiSummaryCall=None):
        self._guiSummaryCall = guiSummaryCall
        self.identity = misc.getIDName() # going to leave in for people running from command line
        self.balance = ''
        self.burnRate = ''
        self.ds = diskspace.DiskSpace()

    def GetActiveCount(self):
        activeCount = 0
        for idurl in contacts.getSupplierIDs():
            if idurl:
                if transport_control.ContactIsAlive(idurl):
                    activeCount += 1
        return activeCount

    def SetGUISummaryCall(self, guiSummaryCall):
        dhnio.Dprint(14, 'summary.SetGUISummaryCall')
        self._guiSummaryCall = guiSummaryCall

    def UpdateStatusInfo(self, doPoll = False):
        try:
            supplierStatus = str(self.GetActiveCount()) + "/" + str(settings.getCentralNumSuppliers()) + " online"
            spaceStatus = self.ds.getValueBest(backup_db.GetTotalBackupsSize() * 2) + "/" + settings.getCentralMegabytesNeeded()
            daysAtBurnRate = "pos cash flow"
            balanceStatus = ''
            if self.balance != '' and self.burnRate != '':
                if self.burnRate < 0.0:
                    daysAtBurnRate = self.balance / (-self.burnRate)
                    if daysAtBurnRate > 365:
                        daysAtBurnRate = str(int(daysAtBurnRate/365)) + " years"
                    elif daysAtBurnRate > 30:
                        daysAtBurnRate = str(int(daysAtBurnRate/30)) + " months"
                    else:
                        daysAtBurnRate = str(int(daysAtBurnRate)) + " days"
                balanceStatus = '$' + ("%.2f" % self.balance) + " (" + daysAtBurnRate + ")"

            if self._guiSummaryCall is not None:
                dhnio.Dprint(14, 'summary.UpdateStatusInfo about to do guisummarycall')
                self._guiSummaryCall(supplierStatus, spaceStatus, balanceStatus)
            else:
                dhnio.Dprint(14, "Identity:  " + self.identity)
                dhnio.Dprint(14, "Suppliers: " + supplierStatus)
                dhnio.Dprint(14, "Space:     " + spaceStatus)
                dhnio.Dprint(14, "Balance:   " + balanceStatus)
        except:
            dhnio.DprintException()

        if doPoll:
            reactor.callLater(900, self.UpdateStatusInfo, doPoll)
        #things that can change the summary, change in space or suppliers (on save in settings), change in space used, online suppliers ...

    def SetBalanceAndBurnRate(self, balance, burnRate):
        dhnio.Dprint(14, 'summary.SetBalanceAndBurnRate ' + str(balance) + ", " + str(burnRate))
        self.balance = balance
        self.burnRate = burnRate
        self.UpdateStatusInfo()


# Veselin, please ask me before making changes to this, summary.init gets called before anything calling calling summary
SetBalanceAndBurnRate = None
SetGUISummaryCall = None
UpdateStatusInfo = None

def init(callback=None):
    dhnio.Dprint(4, 'summary.init')
    global SetBalanceAndBurnRate
    global SetGUISummaryCall
    global UpdateStatusInfo

    _Summary = _SummaryInfo(callback)

    SetBalanceAndBurnRate = _Summary.SetBalanceAndBurnRate
    SetGUISummaryCall = _Summary.SetGUISummaryCall
    UpdateStatusInfo = _Summary.UpdateStatusInfo

    UpdateStatusInfo(True) # start off the one loop
    
    
    