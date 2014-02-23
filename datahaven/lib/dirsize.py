#!/usr/bin/python
#dirsize.py
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
    sys.exit('Error initializing twisted.internet.reactor in dirsize.py')

from twisted.internet import threads

import dhnio
import diskspace

#------------------------------------------------------------------------------ 

_Jobs = {}
_Dirs = {}

#------------------------------------------------------------------------------ 

def ask(dirpath, callback=None, arg=None):
    global _Jobs
    global _Dirs
    dhnio.Dprint(6, 'dirsize.ask %s' % dirpath)
    if _Jobs.has_key(dirpath):
        return 'counting size'
    if not os.path.isdir(dirpath):
        _Dirs[dirpath] = 'not exist'
        if callback:
            reactor.callLater(0, callback, 'not exist', arg)
        return 'not exist'
    d = threads.deferToThread(dhnio.getDirectorySize, dirpath)
    d.addCallback(done, dirpath)
    _Jobs[dirpath] = (d, callback, arg)
    _Dirs[dirpath] = 'counting size'
    return 'counting size'
    
def done(size, dirpath):
    global _Dirs
    global _Jobs
    dhnio.Dprint(6, 'dirsize.done %s %s' % (str(size), dirpath.decode(),))
    _Dirs[dirpath] = str(size)
    try:
        (d, cb, arg) = _Jobs.pop(dirpath, (None, None, None))
        if cb:
            cb(dirpath, size, arg)
    except:
        dhnio.DprintException()
    
def get(dirpath, default=''):
    global _Dirs
    return _Dirs.get(dirpath, default)
    
def isjob(dirpath):
    global _Jobs
    return _Jobs.has_key(dirpath)

def getLabel(dirpath):
    global _Dirs
    s = _Dirs.get(dirpath, '')
    if s not in ['counting size', 'not exist']:
        try:
            return diskspace.MakeStringFromBytes(int(s))
        except:
            return str(s)
    return str(s)
    
def getInBytes(dirpath, default=-1):
    return diskspace.GetBytesFromString(get(dirpath), default)     
        
#------------------------------------------------------------------------------ 

def main():
    def _done(path, sz, arg):
        print path, sz
        reactor.stop()
    dhnio.init()
    ask(sys.argv[1], _done)
    reactor.run()

if __name__ == "__main__":
    main()
    
    