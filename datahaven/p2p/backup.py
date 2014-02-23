#!/usr/bin/python
#backup.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#
#  This interfaces between a pipe from something like tar and the twisted code
#    for rest of DataHaven.NET
#  We see how many packets are waiting to be sent,
#    and if it is not too many, and we can make more, we make some more.
#
#  Main idea:
#     1) When a backup is started a backup object is created
#     2) We get a file descriptor for the process creating the tar archive
#     3) We always use select/poll before reading so we never block
#     4) We also poll to see if more needed.
#     5) We number/name blocks so can be sure what is what when we read back later
#     6) We call raidmake to split block and make parities
#     7) We put parts into dhnpackets and give these to transport_control


import os
import sys
import time
import cStringIO
import gc


try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in backup.py')

from twisted.internet import threads
from twisted.internet.defer import Deferred, maybeDeferred


import lib.dhnio as dhnio
import lib.misc as misc
import lib.dhnpacket as dhnpacket
import lib.contacts as contacts
import lib.commands as commands
import lib.settings as settings
import lib.packetid as packetid
import lib.nonblocking as nonblocking
import lib.eccmap as eccmap
import lib.dhncrypto as dhncrypto
import lib.tmpfile as tmpfile
import lib.automat as automat
# import lib.automats as automats


import data_sender

import raidmake
import dhnblock
import events
# import backup_matrix


#-------------------------------------------------------------------------------

class backup(automat.Automat):
    timers = {'timer-01sec':    (0.1, ['RUN', 'READ']),} 
    
    def __init__(self, backupID, pipe, finishCallback=None, blockResultCallback=None, blockSize=None,): #  resultDeferred=None
        self.backupID = backupID
        self.eccmap = eccmap.Current()
        self.pipe = pipe
        self.blockSize = blockSize
        if self.blockSize is None:
            self.blockSize = settings.getBackupBlockSize()
        self.ask4abort = False
        self.stateEOF = False
        self.stateReading = False
        self.currentBlockData = cStringIO.StringIO()
        self.currentBlockSize = 0
        self.blockNumber = 0
        self.dataSent = 0
        self.blocksSent = 0
        self.closed = False
        self.finishCallback = finishCallback
        self.blockResultCallback = blockResultCallback
        automat.Automat.__init__(self, 'backup', 'AT_STARTUP', 14)
        self.automat('init')
        events.info('backup', '%s started' % self.backupID)
        # dhnio.Dprint(6, 'backup.__init__ %s %s %d' % (self.backupID, self.eccmap, self.blockSize,))

    def abort(self):
        dhnio.Dprint(4, 'backup.abort id='+str(self.backupID))
        self.ask4abort = True
        try:
            self.pipe.kill()
        except:
            pass
        
    #------------------------------------------------------------------------------ 
        
    def A(self, event, arg):
        #---AT_STARTUP---
        if self.state is 'AT_STARTUP':
            if event == 'init' :
                self.state = 'RUN'
        #---RUN---
        elif self.state is 'RUN':
            if event == 'timer-01sec' and self.isAborted(arg) :
                self.state = 'ABORTED'
                self.doClose(arg)
                self.doReport(arg)
                self.doDestroyMe(arg)
            elif event == 'timer-01sec' and not self.isAborted(arg) :
                self.state = 'READ'
        #---READ---
        elif self.state is 'READ':
            if event == 'timer-01sec' and self.isPipeReady(arg) and not self.isEOF(arg) and not self.isReadingNow(arg) and not self.isBlockReady(arg) :
                self.doRead(arg)
            elif event == 'timer-01sec' and not self.isReadingNow(arg) and ( self.isBlockReady(arg) or self.isEOF(arg) ) :
                self.state = 'BLOCK'
                self.doBlock(arg)
        #---BLOCK---
        elif self.state is 'BLOCK':
            if event == 'block-ready' :
                self.state = 'RAID'
                self.doRaid(arg)
        #---RAID---
        elif self.state is 'RAID':
            if event == 'raid-done' and not self.isEOF(arg) :
                self.state = 'RUN'
                self.doBlockReport(arg)
                data_sender.A('new-data')
                self.doNewBlock(arg)
            elif event == 'raid-done' and self.isEOF(arg) :
                self.state = 'DONE'
                self.doBlockReport(arg)
                data_sender.A('new-data')
                self.doClose(arg)
                self.doReport(arg)
                self.doDestroyMe(arg)
        #---DONE---
        elif self.state is 'DONE':
            pass
        #---ABORTED---
        elif self.state is 'ABORTED':
            pass

    def isAborted(self, arg):
        return self.ask4abort
         
    def isPipeReady(self, arg):
        return self.pipe is not None and self.pipe.state() in [nonblocking.PIPE_CLOSED, nonblocking.PIPE_READY2READ]
    
    def isBlockReady(self, arg):
        return self.currentBlockSize >= self.blockSize
    
    def isEOF(self, arg):
        return self.stateEOF
    
    def isReadingNow(self, arg):
        return self.stateReading

    def doClose(self, arg):
        self.closed = True
        
    def doDestroyMe(self, arg):
        self.currentBlockData.close()
        del self.currentBlockData
        automat.objects().pop(self.index)
        collected = gc.collect()
        dhnio.Dprint(10, 'backup.doDestroyMe [%s] collected %d objects' % (self.backupID, collected))

    def doReport(self, arg):
        if self.ask4abort:
            if self.finishCallback:
                self.finishCallback(self.backupID, 'abort')
            events.info('backup', '%s aborted' % self.backupID)
        else:  
            if self.finishCallback:
                self.finishCallback(self.backupID, 'done')
            events.info('backup', '%s done successfully' % self.backupID)

    def doRead(self, arg):
        def readChunk():
            size = self.blockSize - self.currentBlockSize
            if size < 0:
                dhnio.Dprint(1, "backup.readChunk ERROR eccmap.nodes=" + str(self.eccmap.nodes()))
                dhnio.Dprint(1, "backup.readChunk ERROR blockSize=" + str(self.blockSize))
                dhnio.Dprint(1, "backup.readChunk ERROR currentBlockSize=" + str(self.currentBlockSize))
                raise Exception('size < 0, blockSize=%s, currentBlockSize=%s' % (self.blockSize, self.currentBlockSize))
                return ''
            elif size == 0:
                return ''
            if self.pipe is None:
                raise Exception('backup.pipe is None')
                return ''
            if self.pipe.state() == nonblocking.PIPE_CLOSED:
                dhnio.Dprint(10, 'backup.readChunk the state is PIPE_CLOSED !!!!!!!!!!!!!!!!!!!!!!!!')
                return ''
            if self.pipe.state() == nonblocking.PIPE_READY2READ:
                newchunk = self.pipe.recv(size)
                if newchunk == '':
                    dhnio.Dprint(10, 'backup.readChunk pipe.recv() returned empty string')
                return newchunk
            dhnio.Dprint(1, "backup.readChunk ERROR pipe.state=" + str(self.pipe.state()))
            raise Exception('backup.pipe.state is ' + str(self.pipe.state()))
            return ''
        def readDone(data):
            self.currentBlockData.write(data)
            self.currentBlockSize += len(data)
            self.stateReading = False
            if data == '':
                self.stateEOF = True
            #dhnio.Dprint(12, 'backup.readDone %d bytes' % len(data))
        self.stateReading = True
        maybeDeferred(readChunk).addCallback(readDone)

    def doBlock(self, arg):
        def _doBlock():
            dt = time.time()
            src = self.currentBlockData.getvalue()
            block = dhnblock.dhnblock(
                misc.getLocalID(),
                self.backupID,
                self.blockNumber,
                dhncrypto.NewSessionKey(),
                dhncrypto.SessionKeyType(),
                self.stateEOF,
                src,)
            del src
            dhnio.Dprint(12, 'backup.doBlock blockNumber=%d size=%d atEOF=%s dt=%s' % (self.blockNumber, self.currentBlockSize, self.stateEOF, str(time.time()-dt)))
            return block
        maybeDeferred(_doBlock).addCallback(
            lambda block: self.automat('block-ready', block),)

    def doRaid(self, arg):
        newblock = arg
        fileno, filename = tmpfile.make('raid')
        serializedblock = newblock.Serialize()
        blocklen = len(serializedblock)
        os.write(fileno, str(blocklen) + ":" + serializedblock)
        os.close(fileno)
        dt = time.time()
        d = threads.deferToThread(raidmake.raidmake, 
                                  filename, 
                                  self.eccmap.name, 
                                  self.backupID, 
                                  self.blockNumber)
        d.addCallback(self._raidmakeCallback, newblock, dt)
        d.addErrback(self._raidmakeErrback)
        del serializedblock

    def doBlockReport(self, arg):
        if self.blockResultCallback:
            self.blockResultCallback(arg, self.eccmap.NumSuppliers())

    def doNewBlock(self, arg):
        self.dataSent += self.currentBlockSize
        self.blocksSent += 1
        self.currentBlockData.close()
        del self.currentBlockData
        self.currentBlockData = cStringIO.StringIO()
        self.currentBlockSize = 0
        self.blockNumber += 1

    def _raidmakeCallback(self, x, newblock, dt):
        dhnio.Dprint(12, 'backup._raidmakeCallback block=%d size=%d eof=%s dt=%s' % (
            self.blockNumber, self.currentBlockSize, str(self.stateEOF), str(time.time()-dt)))
        self.automat('raid-done', newblock)
        
    def _raidmakeErrback(self, x):
        dhnio.Dprint(2, 'backup.doRaid ERROR: %s' % str(x))
        self.automat('raid-done', None)


