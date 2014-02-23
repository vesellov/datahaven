#!/usr/bin/python
#automat.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

import os
import sys

from twisted.internet import reactor
from twisted.internet.task import LoopingCall

#------------------------------------------------------------------------------ 

_Counter = 0
_Index = {}
_Objects = {}
_StateChangedCallback = None
_LogFile = None
_LogFilename = None
_LogsCount = 0
_LifeBeginsTime = 0

#------------------------------------------------------------------------------ 

def get_new_index():
    global _Counter
    _Counter += 1
    return _Counter - 1


def create_index(name):
    global _Index
    id = name
    if _Index.has_key(id):
        i = 1
        while _Index.has_key(id + '(' + str(i) + ')'):
            i += 1
        id = name + '(' + str(i) + ')'
    _Index[id] = get_new_index()
    return id, _Index[id]


def set_object(index, obj):
    global _Objects
    _Objects[index] = obj
   
    
def clear_object(index):
    global _Objects
    if _Objects is None:
        return
    if _Objects.has_key(index):
        del _Objects[index]


def objects():
    global _Objects
    return _Objects

#------------------------------------------------------------------------------ 

class Automat(object):
    timers = {}
    fast = False
    state = 'NOT_EXIST'
    def __init__(self, name, state, debug_level=18):
        self.id, self.index = create_index(name)
        self.name = name
        self.state = state
        self.debug_level = debug_level
        self._timers = {}
        self.init()
        self.startTimers()
        self.log(self.debug_level,  'NEW AUTOMAT %s CREATED with index %d' % (str(self), self.index))
        set_object(self.index, self)

    def __del__(self):
        global _Index
        global _StateChangedCallback
        if self is None:
            return
        id = self.id
        name = self.name
        debug_level = self.debug_level
        if _Index is None:
            self.log(debug_level, 'automat.__del__ Index is None')
            return
        index = _Index.get(id, None)
        if index is None:
            self.log(debug_level, 'automat.__del__ WARNING %s not found' % id)
            return
        del _Index[id]
        self.log(debug_level, 'AUTOMAT %s [%d] DESTROYED' % (id, index))
        if _StateChangedCallback is not None:
            _StateChangedCallback(index, id, name, '')

    def __repr__(self):
        return '%s[%s]' % (self.id, self.state)

    def init(self):
        pass

    def state_changed(self, oldstate, newstate):
        pass

    def A(self, event, arg):
        raise NotImplementedError

    def automat(self, event, arg=None):
        if self.fast:
            reactor.callWhenRunning(self.event, event, arg)
            # self.event(event, arg)
        else:
            reactor.callLater(0, self.event, event, arg)
            # reactor.callWhenRunning(self.event, event, arg)

    def event(self, event, arg=None):
        global _StateChangedCallback
        self.log(self.debug_level * 8, '%s fired with event "%s"' % (self, event))# , sys.getrefcount(Automat)))
        old_state = self.state
        self.A(event, arg)
        new_state = self.state
        if old_state != new_state:
            self.stopTimers()
            self.state_changed(old_state, new_state)
            self.log(self.debug_level, '%s(%s): [%s]->[%s]' % (self.id, event, old_state, new_state))
            self.startTimers()
            if _StateChangedCallback is not None:
                _StateChangedCallback(self.index, self.id, self.name, new_state)

    def timer_event(self, name, interval):
        if self.timers.has_key(name) and self.state in self.timers[name][1]:
            self.automat(name)
        else:
            self.log(self.debug_level, '%s.timer_event ERROR timer %s not found in self.timers' % (str(self), name))

    def stopTimers(self):
        for name, timer in self._timers.items():
            if timer.running:
                timer.stop()
                # self.log(self.debug_level * 4, '%s.stopTimers timer %s stopped' % (self, name))
        self._timers.clear()

    def startTimers(self):
        for name, (interval, states) in self.timers.items():
            if len(states) > 0 and self.state not in states:
                continue
            self._timers[name] = LoopingCall(self.timer_event, name, interval)
            self._timers[name].start(interval, False)
            # self.log(self.debug_level * 4, '%s.startTimers timer %s started' % (self, name))

    def restartTimers(self):
        self.stopTimers()
        self.startTimers()

    def log(self, level, text):
        global _LogFile
        global _LogFilename
        global _LogsCount
        global _LifeBeginsTime
        if _LogFile is not None:
            import time
            if _LogsCount > 10000:
                _LogFile.close()
                _LogFile = open(_LogFilename, 'w')
                _LogsCount = 0

            s = ' ' * level + text+'\n'
            if _LifeBeginsTime != 0:
                dt = time.time() - _LifeBeginsTime
                mn = dt // 60
                sc = dt - mn * 60
                s = ('%02d:%02d.%02d' % (mn, sc, (sc-int(sc))*100)) + s
            else:
                s = time.strftime('%H:%M:%S') + s

            _LogFile.write(s)
            _LogFile.flush()
            _LogsCount += 1
        else:
            try:
                from dhnio import Dprint
                Dprint(level, text)
            except:
                try:
                    from lib.dhnio import Dprint
                    Dprint(level, text)
                except:
                    pass

#------------------------------------------------------------------------------ 

def SetStateChangedCallback(cb):
    global _StateChangedCallback
    _StateChangedCallback = cb


def OpenLogFile(filename):
    global _LogFile
    global _LogFilename
    if _LogFile:
        return
    _LogFilename = filename
    try:
        _LogFile = open(_LogFilename, 'w')
    except:
        _LogFile = None


def CloseLogFile():
    global _LogFile
    if not _LogFile:
        return
    _LogFile.flush()
    _LogFile.close()
    _LogFile = None
    _LogFilename = None


def LifeBegins(when=None):
    global _LifeBeginsTime
    if when:
        _LifeBeginsTime = when
    else:
        _LifeBeginsTime = time.time()
    