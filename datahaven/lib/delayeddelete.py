#!/usr/bin/python
#delayeddelete.py
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
import time


try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in delayeddelete.py')


import dhnio
import tmpfile

_Queue = []
_QueueTask = None

#------------------------------------------------------------------------------ 

class filetodelete:
    filename = ""     # name of file we are going to soon delete
    timetodelete = 0  # time after which we should delte this file
    def __init__ (self, filename, timetodelete):
        self.filename = filename
        self.timetodelete = timetodelete


def init():
    global _Queue
    _Queue = []


def DeleteAfterTime(filename, delay):
    global _Queue
    now = time.time()
    timetodelete = now + delay
    newjob = filetodelete(filename, timetodelete)
    _Queue.append(newjob)
    CallIfNeeded()


def CheckQueue():
    global _Queue
    global _QueueTask
    
    now = time.time()
    removeditems = []
    
    for item in _Queue:
        if (item.timetodelete <= now and os.access(item.filename, os.W_OK)):
            tmpfile.throw_out(item.filename, 'delayeddelete')
            removeditems.append(item)

    if len(removeditems) > 0:
        for item in removeditems:
            _Queue.remove(item)
    del removeditems

    _QueueTask = None
    CallIfNeeded()


def CallIfNeeded():
    global _Queue
    global _QueueTask
    if _QueueTask is not None:
        return 
    if len(_Queue) > 0:
        _QueueTask = reactor.callLater(10, CheckQueue)

