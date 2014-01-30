#!/usr/bin/python
#sweeptemp.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#
#Temp directory:
#earlier today I had over 30000, 3GB of DHN related files in temp.
#Something to keep an eye on this, clean up after ourselves over time.

import os
import sys
import time

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in sweeptemp.py')

from twisted.internet.defer import Deferred


import datahaven.lib.dhnio as dhnio
import datahaven.lib.settings as settings


_LoopObject = None
#will scan Temp folder each N minutes
_DefaultDelay = 60 * 60 # 1 hour sufficient, maybe even just once a day, temp directory could be 1000's of files, don't want to scan often

#will remove only files with listed below extensions and intervals
_ExtensionsToDelete = {
'.controloutbox':60*60*24*1, # hold onto outbox files 1 day so we can handle resends if contact offline
'.dhn-tcp-in':   60*10,      # 10 minutes for incoming files
'.dhn-http-in':  60*30,
'.dhn-q2q-in':   60*10,      # 10 minutes for incoming files
'.dhn-cspace-in':60*10,      # 10 minutes for incoming files
'.dhn-version':  60*10,
'.dhn-info':     60*10,
'-dhn.bat':      60*10,
#'.dhn-tcp-out':  60*60*24*1, # hold on 1 day to outgoing tcp
'.propagate':    60*10,      # propagate happens often enough, 10 minutes should be enough
'.backup':       60*10,
'-data':         60*60*24*1, # hold onto data for rebuilding for a day, can rebuild parity as needed
'-parity':       60*60,      # hold onto parity for an hour
}
#we do not want to remove some files. keep it in this list.
#just filenames here
_ExculdedFiles = set()

def exclude(filename, exclude_off=False):
    global _ExculdedFiles
    fn = os.path.basename(filename)
    if not exclude_off:
        _ExculdedFiles.add(fn)
    else:
        _ExculdedFiles.discard(fn)

def delete(filepath):
    dhnio.Dprint(8, 'sweeptemp.delete ' + os.path.basename(str(filepath)))
    try:
        os.remove(filepath)
    except:
        dhnio.DprintException()

def run():
    global _ExtensionsToDelete
    global _ExculdedFiles
    dhnio.Dprint(6, 'sweeptemp.run')

    deleteCount = 0
    tempdir = os.path.abspath(settings.TempDir())
    for filename in os.listdir(tempdir):
        if filename in _ExculdedFiles:
            continue
        filepath = os.path.abspath(os.path.join(tempdir, filename))

#        if not os.path.isfile(filepath):
#            continue
#        if not os.access(filepath, os.R_OK):
#            continue
#        if not os.access(filepath, os.W_OK):
#            continue
#        extension_interest = False

        for ext in _ExtensionsToDelete.keys():
            if filename.lower().endswith(ext):
                dhnio.Dprint(10, 'sweeptemp.run   %s' % filename)
                try:
                    tm = os.path.getatime(filepath)
                    if (time.time() - tm) > _ExtensionsToDelete[ext]:
                        delete(filepath)
                        deleteCount += 1
                        if deleteCount > 100:
                            return True
                except:
                    dhnio.DprintException()

                break

    return False


def loop():
    global _LoopObject
    #reactor.callInThread(run) # if we run in another thread, if we're deleting stuff and looking to shutdown, it won't let us exit
    if run(): # if we delete found 100 files to delete, potentially more
        _LoopObject = reactor.callLater(30, loop)
    else:
        _LoopObject = reactor.callLater(_DefaultDelay, loop)

def init():
    dhnio.Dprint(4, 'sweeptemp.init')
    loop()


if __name__ == '__main__':
    dhnio.SetDebug(18)
    init()
    reactor.run()
    
    