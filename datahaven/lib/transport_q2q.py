#!/usr/bin/python
#transport_q2q.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

import os
import sys
import time


if __name__ == '__main__':
    dirpath = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..')))
    import dhnio
    dhnio.SetDebug(20)
   

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in transport_q2q.py')


from zope.interface import implements
from twisted.internet import interfaces
from twisted.internet.defer import Deferred, succeed
from twisted.internet.base import DelayedCall
DelayedCall.debug = False


import misc
import dhnio
import settings
import tmpfile
import transport_control


if transport_control._TransportQ2QEnable:
    import dhnvertex


_State = ''
_Listener = None
NEW_USER_PASSWORD_LENGTH = 12

#------------------------------------------------------------------------------ 

def init(auto_start=True):
    global _State
    if _State != '':
        dhnio.Dprint(4, 'transport_q2q.init WARNING already called and current _State is '+_State)
        return succeed(_State)

    _State = 'init'
        
    dhnio.Dprint(4, 'transport_q2q.init')

    resultDefer = Deferred()

    if settings.getQ2Qusername().strip() == '' or settings.getQ2Qhost().strip() == '':
        dhnio.Dprint(6, 'transport_q2q.init  want to erase local data base in ' + settings.Q2QDir())
        clear_local_db(settings.Q2QDir())

    dhnvertex.init(q2qdir = settings.Q2QDir(),
                   logFunc = dhnio.Dprint,
                   receiveNotifyFunc = receive_status_func,
                   sentNotifyFunc = sent_status_func,
                   tempFileFunc = tmpfile.make,)

    if auto_start:
        _State = 'auto'
        auto(resultDefer)
    else:
        resultDefer.callback(_State)
       
    return resultDefer


def register(user, password):
    return dhnvertex.register(user, password)

def clear_local_db(local_db_dir):
    dhnvertex.clear_local_db(local_db_dir)

def receive():
    return dhnvertex.receive()

def send(to_user, filename):
    def failed(reason, to_user, filename):
        sent_status_func(to_user, filename, 'failed', reason)
        return reason        
    d = dhnvertex.send(to_user, filename)
    d.addErrback(failed, to_user, filename)
    return d

def isReceiving():
    global _State
    return _State == 'ready'

class PseudoListener:
    implements(interfaces.IListeningPort)
    def startListening(self):
        global _State
        if _State == '':
            return init()
        return succeed(_State) 

    def stopListening(self):
        global _State
        if _State != '':
            return shutdown()
        return succeed(_State)

    def getHost(self):
        return str(dhnvertex.getFrom())

def getListener():
    global _Listener
    if _Listener is None:
        _Listener = PseudoListener()
    return _Listener


def receive_status_func(fromUser, filename, status, reason):
    transport_control.receiveStatusReport(filename, status, 'q2q', fromUser, reason)

def sent_status_func(toUser, filename, status, reason):
    transport_control.sendStatusReport(toUser, filename, status, 'q2q', reason)

def auto(resultDefer):
    dhnio.Dprint(4, 'transport_q2q.auto')
    
    def receive_started(resultDefer):
        global _State
        _State = 'ready'
        resultDefer.callback(x)
    
    def do_receive(resultDefer):
        global _State
        _State = 'receive'
        d = dhnvertex.receive()
        d.addCallback(lambda x: receive_started(resultDefer))
        d.addErrback(resultDefer.errback)
        
    def do_register(resultDefer):
        global _State
        _State = 'register'
        
        d = install()
        d.addCallback(lambda x: do_receive(resultDefer))
        d.addErrback(resultDefer.errback)
        
    if settings.getQ2Qusername().strip() == '' or settings.getQ2Qhost().strip() == '':
        do_register(resultDefer)
    else:
        do_receive(resultDefer)
        
    return resultDefer
    

def shutdown():
    global _State
    dhnio.Dprint(4, 'transport_q2q.init')
    _State = ''
    return dhnvertex.shutdown()


def install():
    dhnio.Dprint(4, 'transport_q2q.install')
       
    def done(x, resultDefer): 
        dhnio.Dprint(4, 'transport_q2q.install.done')
        settings.setQ2Quserathost(str(dhnvertex.getFrom()))
        resultDefer.callback(x)
        return x
        
    def failed(x, resultDefer):
        dhnio.Dprint(4, 'transport_q2q.install.failed: ' + x.getErrorMessage())
        resultDefer.errback(x)
        return x

    result = Deferred()
    username = misc.getIDName() + time.strftime('%Y%m%d%H%M%S') + '@' + settings.DefaultQ2QServer()
    password = settings.getQ2Qpassword()
    if password.strip() == '':
        password = misc.rndstr(NEW_USER_PASSWORD_LENGTH)
        settings.setQ2Qpassword(password)

    d = dhnvertex.register(username, password)
    d.addCallback(done, result)
    d.addErrback(failed, result)

    return result


#------------------------------------------------------------------------------ 


def usage():
    print '''
usage:
    transport_q2q.py send <user@server> <filename>
    transport_q2q.py receive
    transport_q2q.py install
'''


def main(argv=sys.argv):
    if argv.count('install'):
        settings.setQ2Qusername('')
        settings.setQ2Qpassword('')
        #init(False).addCallback(
        init(True).addBoth(
                lambda x: reactor.stop())
#        install().addBoth(
#                lambda x: reactor.stop())
        reactor.run()
        
    elif argv.count('receive'):
        init(False).addCallback(
            lambda x: receive())
        reactor.run()
        
    elif argv.count('send'):
        def doSend(x):
            def sent(x):
                print 'CONNECTED!'
            def fail(x):
                print 'fail'
                reactor.stop()
            send(argv[2], argv[3]).addCallbacks(sent, fail)
        init(False).addCallback(doSend)
        reactor.run()
        
    else:
        usage()
        

if __name__ == '__main__':
    dhnio.SetDebug(20)
    main()


