#!/usr/bin/python
#transport_http.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#

"""
This module allow you to send files over plain HTTP.
One user (with opened IP) starts a server and listen for others.
Second user connect to him when need to send.
To receive packets ( from the first user ) - second user will request HTTP server periodically
to check for incoming files. First user will cache last 10 outgoing files. 
This is very old and not used any more.
"""

import os
import sys
import base64
import tempfile
import time

if __name__ == '__main__':
    dirpath = os.path.dirname(os.path.abspath(sys.argv[0]))
    sys.path.insert(0, os.path.abspath('datahaven'))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..')))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..', '..')))

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in transport_http.py')

from twisted.internet.defer import Deferred, succeed
from twisted.web import server, resource
from twisted.web.client import HTTPClientFactory


import misc
import dhnio
import dhnnet
import transport_control
import contacts
import nameurl
import settings
import identitycache
import tmpfile


_Outbox = {}
_Contacts = {}
_ReceivingLoop = None
_ServerListener = None
_LastPingTimeDict = {}
_PingDelayDict = {}
_ConnectionsDict = {}
_CurrentDelay = 5

#-------------------------------------------------------------------------------

def send(idurl, filename):
    dhnio.Dprint(12, 'transport_http.send to %s %s' % (idurl, filename))
    global _Outbox
    if not _Outbox.has_key(idurl):
        _Outbox[idurl] = []
    _Outbox[idurl].append(filename)
    #we want to keep only 10 last files.
    if len(_Outbox[idurl]) > 10:
        lostedfilename = _Outbox[idurl].pop(0)
        transport_control.sendStatusReport(
            'unknown',
            lostedfilename,
            'failed',
            'http',)

class SenderServer(resource.Resource):
    isLeaf = True
    def render_POST(self, request):
        global _Outbox
        idurl = request.getHeader('idurl')
        if idurl is None:
            return ''
        dhnio.Dprint(14, 'transport_http.SenderServer.render connection from ' + idurl)
        if not idurl in _Outbox.keys():
            return ''
        r = ''
        for filename in _Outbox[idurl]:
            if not os.path.isfile(filename):
                continue
            if not os.access(filename, os.R_OK):
                continue
            src = dhnio.ReadBinaryFile(filename)
            if src == '':
                continue
            src64 = base64.b64encode(src)
            r += src64 + '\n'
            dhnio.Dprint(12, 'transport_http.SenderServer.render sent %s to %s' % (filename, idurl))
            #TODO request.getPeer()
            transport_control.sendStatusReport(
                request.getClient(),
                filename,
                'finished',
                'http',)
        _Outbox.pop(idurl, None)
        return r

def start_http_server(port):
    global _ServerListener
    dhnio.Dprint(6, 'transport_http.start_http_server going to listen on port ' + str(port))
    if _ServerListener is not None:
        dhnio.Dprint(8, 'transport_http.start_http_server is already started')
#        return _ServerListener
        return succeed(_ServerListener)

    def _try_listening(port, count):
        global _ServerListener
        dhnio.Dprint(12, "transport_http.start_http_server count=%d" % count)
        site = server.Site(SenderServer())
        try:
            _ServerListener = reactor.listenTCP(int(port), site)
        except:
            _ServerListener = None
        return _ServerListener

    def _loop(port, result, count):
        l = _try_listening(port, count)
        if l is not None:
            dhnio.Dprint(8, "transport_http.start_http_server started on port "+ str(port))
            result.callback(l)
            return
        if count > 10:
            dhnio.Dprint(1, "transport_http.start_http_server WARNING port %s is busy!" % str(port))
            result.errback(None)
            return
        reactor.callLater(10, _loop, port, result, count+1)

    res = Deferred()
    _loop(port, res, 0)
    return res


def stop_http_server():
    global _ServerListener
    dhnio.Dprint(6, 'transport_http.stop_http_server')
    if _ServerListener is None:
        dhnio.Dprint(8, 'transport_http.stop_http_server _ServerListener is None')
        d = Deferred()
        d.callback('')
        return d
    d = _ServerListener.stopListening()
    _ServerListener = None
    return d

class TransportHTTPClientFactory(HTTPClientFactory):
    pass

class TransportHTTPProxyClientFactory(HTTPClientFactory):
    def setURL(self, url):
        HTTPClientFactory.setURL(self, url)
        self.path = url

def receive():
    global _ReceivingLoop
    dhnio.Dprint(6, 'transport_http.receive')

    if _ReceivingLoop is not None:
        return _ReceivingLoop


    def success(src, idurl, host, port, conn):
        global _LastPingTimeDict
        global _ConnectionsDict

        if len(src) == 0:
            increase_receiving_delay(idurl)

        else:
            parts = src.splitlines()
            dhnio.Dprint(14, 'transport_http.receive.success %d bytes in %d parts from %s (%s:%s)' % (len(src), len(parts), idurl, host, port))
            for part64 in parts:
                try:
                    part = base64.b64decode(part64.strip())
                except:
                    dhnio.Dprint(14, 'transport_http.receive.success ERROR in base64.b64decode()')
#                    dhnio.Dprint(1, 'len(part64)=%d' % len(part64))
#                    dhnio.Dprint(1, 'len(part64.strip())=%d' % len(part64.strip()))
#                    dhnio.Dprint(1, 'part64=[%s]' % part64)
                    decrease_receiving_delay(idurl)
                    continue
#                fd, filename = tempfile.mkstemp(".dhn-http-in")
                fd, filename = tmpfile.make("http-in")
                os.write(fd, part)
                os.close(fd)
                decrease_receiving_delay(idurl)
                transport_control.receiveStatusReport(
                    filename,
                    'finished',
                    'http',
                    host+':'+port,)
            transport_control.log('http', 'finish connection with %s:%s ' % (host, port))

        conn.disconnect()
        _ConnectionsDict.pop(idurl, None)


    def fail(x, idurl, host, port, conn):
        global _LastPingTimeDict
        global _ConnectionsDict
        increase_receiving_delay(idurl)
        conn.disconnect()
        _ConnectionsDict.pop(idurl, None)


    def ping(idurl, host, port):
        dhnio.Dprint(14, 'transport_http.receive.ping     %s (%s:%s)' % (idurl, host, port))
        url = 'http://' + str(host) + ':' + str(port)

        if dhnnet.proxy_is_on():
            f = TransportHTTPProxyClientFactory(url, method='POST', headers={
                'User-Agent': 'DataHaven.NET transport_http', 'idurl': misc.getLocalID(), } )
            conn = reactor.connectTCP(dhnnet.get_proxy_host(), int(dhnnet.get_proxy_port()), f)
        else:
            f = TransportHTTPClientFactory(url, method='POST', headers={
                'User-Agent': 'DataHaven.NET transport_http', 'idurl': misc.getLocalID(), } )
            conn = reactor.connectTCP(host, int(port), f)

#        f = HTTPClientFactory(url, method='POST', headers={
#            'User-Agent': 'DataHaven.NET transport_http',
#            'idurl': misc.getLocalID(), } )
#        conn = reactor.connectTCP(host, int(port), f)

        f.deferred.addCallback(success, idurl, host, port, conn)
        f.deferred.addErrback(fail, idurl, host, port, conn)
        return conn

    def loop():
        global _ReceivingLoop
        global _Contacts
        global _ToIncreaseDelay
        global _LastPingTimeDict
        global _PingDelayDict
        global _ConnectionsDict
        global _CurrentDelay
        _ReceivingLoop = reactor.callLater(1, loop)
        _CurrentDelay = settings.getHTTPDelay()

        for idurl, hostport in _Contacts.items():
            if _ConnectionsDict.has_key(idurl):
                continue

            lasttm = _LastPingTimeDict.get(idurl, 0)
            delay = _PingDelayDict.get(idurl, _CurrentDelay)
            dt = time.time() - lasttm

            if dt < delay:
                continue

            _ConnectionsDict[idurl] = ping(idurl, hostport[0], hostport[1])
            _LastPingTimeDict[idurl] = time.time()

        return _ReceivingLoop

    return loop()

def decrease_receiving_delay(idurl):
    global _PingDelayDict
    global _CurrentDelay
    dhnio.Dprint(14, 'transport_http.decrease_receiving_delay ' + idurl)
    _PingDelayDict[idurl] = _CurrentDelay

def increase_receiving_delay(idurl):
    global _PingDelayDict
    global _CurrentDelay
    if not _PingDelayDict.has_key(idurl):
        _PingDelayDict[idurl] = _CurrentDelay
    d = _PingDelayDict[idurl]
    if d < settings.DefaultSendTimeOutHTTP() / 2:
        dhnio.Dprint(14, 'transport_http.increase_receiving_delay   %s for %s' % (str(d), idurl))
        _PingDelayDict[idurl] *= 2

def stop_receiving():
    global _ReceivingLoop
    dhnio.Dprint(6, 'transport_http.stop_receiving')
    if _ReceivingLoop is None:
        dhnio.Dprint(8, 'transport_http.stop_receiving _ReceivingLoop is None')
        return
    _ReceivingLoop.cancel()
    del _ReceivingLoop
    _ReceivingLoop = None

def add_contact(idurl):
    global _Contacts
    global _PingDelayDict
    global _CurrentDelay
    dhnio.Dprint(14, 'transport_http.add_contact want to add %s' % idurl)
    ident = contacts.getContact(idurl)
    if ident is None:
        dhnio.Dprint(6, 'transport_http.add_contact WARNING %s not in contacts' % idurl)
        return
    http_contact = ident.getProtoContact('http')
    if http_contact is None:
        dhnio.Dprint(12, 'transport_http.add_contact %s have no http contact. skip.' % idurl)
        return
    proto, host, port, filename = nameurl.UrlParse(http_contact)
    _Contacts[idurl] = (host, port)
    _PingDelayDict[idurl] = _CurrentDelay
    dhnio.Dprint(10, 'transport_http.add_contact %s on %s:%s' % (idurl, host, port))

def update_contacts():
    dhnio.Dprint(10, 'transport_http.update_contacts ')
    global _Contacts
    _Contacts.clear()

    def update_contact(x, idurl):
        add_contact(idurl)

    def failed(x, idurl):
        dhnio.Dprint(10, 'transport_http.update_contacts.failed   NETERROR ' + idurl)

    contacts_list = contacts.getContactIDs()
    contacts_list.append(settings.CentralID())
    contacts_list.append(settings.MoneyServerID())
    contacts_list.append(settings.MarketServerID())
    for idurl in contacts_list:
        dhnio.Dprint(10, 'transport_http.update_contacts want ' + idurl)
        if idurl == misc.getLocalID():
            continue
        ident = contacts.getContact(idurl)
        if ident is None:
            d = identitycache.immediatelyCaching(idurl)
            d.addCallback(update_contact, idurl)
            d.addErrback(failed, idurl)
            continue

        update_contact('', idurl)

def contacts_changed_callback(oldlist, newlist):
    update_contacts()

def init():
    dhnio.Dprint(4, 'transport_http.init')
    contacts.SetContactsChangedCallback(contacts_changed_callback)
    update_contacts()

def shutdown():
    global _ReceivingLoop
    global _ServerListener
    if _ReceivingLoop is not None:
        _ReceivingLoop.cancel()
        _ReceivingLoop = None
    if _ServerListener is not None:
        _ServerListener.stopListening()
        _ServerListener = None

#-------------------------------------------------------------------------------

def usage():
    print '''usage:
transport_http.py send [server_port] [to idurl] [filename]
transport_http.py receive
'''

def main():
    if sys.argv.count('receive'):
##        log.startLogging(sys.stdout)
        settings.init()
        settings.update_proxy_settings()
        contacts.init()
        init()
        receive()
        reactor.run()
    elif sys.argv.count('send'):
##        log.startLogging(sys.stdout)
        settings.init()
        settings.update_proxy_settings()
        contacts.init()
        init()
        start_http_server(int(sys.argv[2]))
        send(sys.argv[3], sys.argv[4])
        reactor.run()
    else:
        usage()

if __name__ == "__main__":
    main()






