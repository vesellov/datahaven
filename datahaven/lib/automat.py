#!/usr/bin/python
#automat.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

"""
  This is the base class for State Machine.
  The DataHaven.NET project is developing in principles of 
  `Automata-based programming <http://en.wikipedia.org/wiki/Automata-based_programming>`_.
 
  This is a programming paradigm in which the program or its part is thought of as a model of a 
  `finite state machine <http://en.wikipedia.org/wiki/Finite_state_machine>`_ or any other formal automaton.   
 
  Its defining characteristic is the use of finite state machines to 
  `describe program behavior <http://en.wikipedia.org/wiki/State_diagram>`_.
          
  The transition graphs of state machines are used in all stages of software development: 
  - specification, 
  - implementation, 
  - debugging and 
  - documentation.

  You can see Transition graph for all DataHaven.NET state machines in the file  
  `automats.pdf <http://datahaven.net/automats.pdf>`_, MS Visio, 'editable' version: 
  `automats.vsd <http://datahaven.net/automats.vsd>`_, stencils is here: `automats.vss <http://datahaven.net/automats.vss>`_

  A small tool called `visio2python <http://code.google.com/p/visio2python/>`_ 
  was written to simplify working with the DataHaven.NET project. 
    
  It can translate transition graphs created in Microsoft Visio into Python code.
 
  Automata-Based Programming technology was introduced by Anatoly Shalyto in 1991 and Switch-technology was 
  developed to support automata-based programming.
  Automata-Based Programming is considered to be rather general purpose program development methodology 
  than just another one finite state machine implementation.
  Anatoly Shalyto is the former of 
  `Foundation for Open Project Documentation <http://en.wikipedia.org/wiki/Foundation_for_Open_Project_Documentation>`_. 
 
  Read more about Switch-technology on the Saint-Petersburg National Research University 
  of Information Technologies, Mechanics and Optics, Programming Technologies Department 
  `Page <http://is.ifmo.ru/english>`_.
     
"""

import os
import sys
import time

from twisted.internet import reactor
from twisted.internet.task import LoopingCall

#------------------------------------------------------------------------------ 

_Counter = 0 #: Increment by one for every new object, the idea is to keep unique ID's in the index
_Index = {} #: Index dictionary, unique id (string) to index (int)
_Objects = {} #: Objects dictionary to store all state machines objects
_StateChangedCallback = None #: Called when some state were changed
_LogFile = None #: This is to have a separated Log file for state machines logs
_LogFilename = None
_LogsCount = 0 #: If not zero - it will print time since that value, not system time 
_LifeBeginsTime = 0

#------------------------------------------------------------------------------ 

class Automat(object):
    """
    Base class of the State Machine Object.
    You need to subclass this class and override the method `A(event, arg)`.
    Constructor needs the `name` of the state machine and the beginning `state`.
    At first it generate an unique `id` and new `index` value.  
    You can use 'init()' method in the subclass to call some code at start.
    Finally put the new object into the memory with given index.  
    """
    
    state = 'NOT_EXIST'
    """
    This is a string representing current Machine state, must be set in the constructor.
    """
    
    timers = {}
    """
    A dictionary of timer events fired at specified intervals when machine rich given states:
          timers = {'timer-60sec':     (60,     ['PING',]),
                    'timer-3min':      (60*10,  ['PING',]), }
    """
     
    fast = False
    """
    By default, a state machine is called this way:
          reactor.callLater(0, self.event, 'event-01', arg1, arg2, ... )
    If fast=True it will use `reactor.callWhenRunning` - call with no delays, default is False.
    """
          
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
        """
        Will print something like: "network_connector[CONNECTED]"
        """
        return '%s[%s]' % (self.id, self.state)

    def init(self):
        """
        Define this method in subclass to execute some code when creating an object. 
        """

    def state_changed(self, oldstate, newstate):
        """
        Define this method in subclass to be able to catch the moment when the state were changed .
        """        

    def A(self, event, arg):
        """
        Must define this method in subclass. 
        This is the core method of the SWITCH-technology.
        """
        raise NotImplementedError

    def automat(self, event, arg=None):
        """
        Call it like this:
            machineA.automat('init')
        to send some `event` to the State Machine Object.
        If `self.fast=False` - the self.A() method will be executed in delayed call.
        """ 
        if self.fast:
            reactor.callWhenRunning(self.event, event, arg)
            # self.event(event, arg)
        else:
            reactor.callLater(0, self.event, event, arg)
            # reactor.callWhenRunning(self.event, event, arg)

    def event(self, event, arg=None):
        """
        You can call event directly to execute self.A() immediately. 
        """
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
        """
        This method fires the timer events.
        """
        if self.timers.has_key(name) and self.state in self.timers[name][1]:
            self.automat(name)
        else:
            self.log(self.debug_level, '%s.timer_event ERROR timer %s not found in self.timers' % (str(self), name))

    def stopTimers(self):
        """
        Stop all state machine timers.
        """
        for name, timer in self._timers.items():
            if timer.running:
                timer.stop()
                # self.log(self.debug_level * 4, '%s.stopTimers timer %s stopped' % (self, name))
        self._timers.clear()

    def startTimers(self):
        """
        Start all state machine timers.
        """
        for name, (interval, states) in self.timers.items():
            if len(states) > 0 and self.state not in states:
                continue
            self._timers[name] = LoopingCall(self.timer_event, name, interval)
            self._timers[name].start(interval, False)
            # self.log(self.debug_level * 4, '%s.startTimers timer %s started' % (self, name))

    def restartTimers(self):
        """
        Restart all state machine timers.
        When state is changed - all internal timers is restarted.
        You can use external timers if you do not need that, call 
            machineA.automat('timer-1sec')
        to fire timer event from outside. 
        """
        self.stopTimers()
        self.startTimers()

    def log(self, level, text):
        """
        Print log message. See `OpenLogFile` and `OpenLogFile`.
        """
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

def get_new_index():
    """
    Just get the current index and increase by one
    """
    global _Counter
    _Counter += 1
    return _Counter - 1


def create_index(name):
    """
    Generate unique ID, and put it into Index dict, increment counter 
    """
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
    """
    Put object for that index into memory
    """
    global _Objects
    _Objects[index] = obj
   
def clear_object(index):
    """
    Clear object with given index from memory
    """
    global _Objects
    if _Objects is None:
        return
    if _Objects.has_key(index):
        del _Objects[index]

def objects():
    """
    Get all state machines stored in memory
    """
    global _Objects
    return _Objects

#------------------------------------------------------------------------------ 

def SetStateChangedCallback(cb):
    """
    Set callback to be fired when any state machine in the index changes its state 
    Callback parameters are:
        `index`, `id`, `name`, `new state`
    """
    global _StateChangedCallback
    _StateChangedCallback = cb


def OpenLogFile(filename):
    """
    Open a file to write logs from all state machines. Very useful during debug.
    """
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
    """
    Close the current log file, you can than open it again.
    """
    global _LogFile
    if not _LogFile:
        return
    _LogFile.flush()
    _LogFile.close()
    _LogFile = None
    _LogFilename = None


def LifeBegins(when=None):
    """
    Call that function during program start up to print relative time in the logs, not absolute. 
    """
    global _LifeBeginsTime
    if when:
        _LifeBeginsTime = when
    else:
        _LifeBeginsTime = time.time()
    