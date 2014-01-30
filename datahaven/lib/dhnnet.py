#!/usr/bin/python
#dhnnet.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#    some network routines
# 

import os
import sys
import subprocess
import types
import socket
import urllib
import urllib2
import urlparse
import mimetypes

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in dhnnet.py')

from twisted.internet.defer import Deferred, DeferredList, succeed, fail
from twisted.internet import ssl
from twisted.internet import protocol
# from twisted.internet.utils import getProcessOutput
from twisted.protocols import basic
from twisted.web import iweb
from twisted.web import client
from twisted.web import http_headers
from twisted.web import http
from twisted.web.client import getPage
from twisted.web.client import downloadPage
from twisted.web.client import HTTPClientFactory
from twisted.web.client import HTTPDownloader

from zope.interface import implements

from OpenSSL import SSL


_ConnectionDoneCallbackFunc = None
_ConnectionFailedCallbackFunc = None

#------------------------------------------------------------------------------ 

_UserAgentString = "DataHaven.NET-http-agent"
_ProxySettings = {
    'host': '',
    'port': '',
    'ssl': 'False',
    'username':'',
    'password': ''
    }

#------------------------------------------------------------------------------

def init():
    pass

def SetConnectionDoneCallbackFunc(f):
    global _ConnectionDoneCallbackFunc
    _ConnectionDoneCallbackFunc = f
    
def SetConnectionFailedCallbackFunc(f):
    global _ConnectionFailedCallbackFunc
    _ConnectionFailedCallbackFunc = f

def ConnectionDone(param=None, proto=None, info=None):
    global _ConnectionDoneCallbackFunc
    if _ConnectionDoneCallbackFunc is not None:
        _ConnectionDoneCallbackFunc(proto, info, param)
    return param

def ConnectionFailed(param=None, proto=None, info=None):
    global _ConnectionFailedCallbackFunc
    if _ConnectionFailedCallbackFunc is not None:
        _ConnectionFailedCallbackFunc(proto, info, param)
    return param

#------------------------------------------------------------------------------ 

def parseurl(url, defaultPort=None):
    """Split the given URL into the scheme, host, port, and path."""
    url = url.strip()
    parsed = urlparse.urlparse(url)
    scheme = parsed[0]
    path = urlparse.urlunparse(('', '') + parsed[2:])
    if defaultPort is None:
        if scheme == 'https':
            defaultPort = 443
        else:
            defaultPort = 80
    host, port = parsed[1], defaultPort
    if ':' in host:
        host, port = host.split(':')
        try:
            port = int(port)
        except ValueError:
            port = defaultPort
    if path == '':
        path = '/'
    return scheme, host, port, path

#------------------------------------------------------------------------------ 

def detect_proxy_settings():
    d = {
        'host':'',
        'port':'',
        'username':'',
        'password':'',
        'ssl': 'False'}
    httpproxy = urllib2.getproxies().get('http', None)
    httpsproxy = urllib2.getproxies().get('https', None)

    if httpproxy is not None:
        try:
            scheme, host, port, path = parseurl(httpproxy)
        except:
            return d
        d['ssl'] = 'False'
        d['host'] = host
        d['port'] = port

    if httpsproxy is not None:
        try:
            scheme, host, port, path = parseurl(httpsproxy)
        except:
            return d
        d['ssl'] = 'True'
        d['host'] = host
        d['port'] = port

    return d

def set_proxy_settings(settings_dict):
    global _ProxySettings
    _ProxySettings = settings_dict

def get_proxy_settings():
    global _ProxySettings
    return _ProxySettings

def get_proxy_host():
    global _ProxySettings
    return _ProxySettings.get('host', '')

def get_proxy_port():
    global _ProxySettings
    try:
        return int(_ProxySettings.get('port', '8080'))
    except:
        return 8080

def get_proxy_username():
    global _ProxySettings
    return _ProxySettings.get('username', '')

def get_proxy_password():
    global _ProxySettings
    return _ProxySettings.get('password', '')

def get_proxy_ssl():
    global _ProxySettings
    return _ProxySettings.get('ssl', '')

def proxy_is_on():
    return get_proxy_host() != ''

#-------------------------------------------------------------------------------

class MyHTTPClientFactory(HTTPClientFactory):
    def page(self, page):
        if self.waiting:
            self.waiting = 0
            self.deferred.callback(page)

    def noPage(self, reason):
        if self.waiting:
            self.waiting = 0
            self.deferred.errback(reason)

    def clientConnectionFailed(self, _, reason):
        if self.waiting:
            self.waiting = 0
            self.deferred.errback(reason)


def getPageTwistedOld(url):
    global _UserAgentString
    scheme, host, port, path = parseurl(url)
    factory = MyHTTPClientFactory(url, agent=_UserAgentString)
    reactor.connectTCP(host, port, factory)
    return factory.deferred

#------------------------------------------------------------------------------


def downloadPageTwisted(url, filename):
    global _UserAgentString
    return downloadPage(url, filename, agent=_UserAgentString)

#-------------------------------------------------------------------------------

#http://schwerkraft.elitedvb.net/plugins/scmcvs/cvsweb.php/enigma2-plugins/mediadownloader/src/HTTPProgressDownloader.py?rev=1.1;cvsroot=enigma2-plugins;only_with_tag=HEAD
class HTTPProgressDownloader(HTTPDownloader):
    """Download to a file and keep track of progress."""

    def __init__(self, url, fileOrName, writeProgress = None, *args, **kwargs):
        HTTPDownloader.__init__(self, url, fileOrName, supportPartial=0, *args, **kwargs)
        # Save callback(s) locally
        if writeProgress and type(writeProgress) is not list:
            writeProgress = [ writeProgress ]
        self.writeProgress = writeProgress

        # Initialize
        self.currentlength = 0
        self.totallength = None

    def gotHeaders(self, headers):
        HTTPDownloader.gotHeaders(self, headers)

        # If we have a callback and 'OK' from Server try to get length
        if self.writeProgress and self.status == '200':
            if headers.has_key('content-length'):
                self.totallength = int(headers['content-length'][0])
                for cb in self.writeProgress:
                    if cb:
                        cb(0, self.totallength)


    def pagePart(self, data):
        HTTPDownloader.pagePart(self, data)

        # If we have a callback and 'OK' from server increment pos
        if self.writeProgress and self.status == '200':
            self.currentlength += len(data)
            for cb in self.writeProgress:
                if cb:
                    cb(self.currentlength, self.totallength)




def downloadWithProgressTwisted(url, file, progress_func):
    global _UserAgentString
    scheme, host, port, path = parseurl(url)
    factory = HTTPProgressDownloader(url, file, progress_func, agent=_UserAgentString)
    if scheme == 'https':
        contextFactory = ssl.ClientContextFactory()
        reactor.connectSSL(host, port, factory, contextFactory)
    else:
        reactor.connectTCP(host, port, factory)
    return factory.deferred

#-------------------------------------------------------------------------------


def downloadSSLWithProgressTwisted(url, file, progress_func, privateKeyFileName, certificateFileName):
    global _UserAgentString
    scheme, host, port, path = parseurl(url)
    factory = HTTPProgressDownloader(url, file, progress_func, agent=_UserAgentString)
    if scheme != 'https':
        return None
    contextFactory = ssl.DefaultOpenSSLContextFactory(privateKeyFileName, certificateFileName)
    reactor.connectSSL(host, port, factory, contextFactory)
    return factory.deferred


#-------------------------------------------------------------------------------


class MyClientContextFactory(ssl.ClientContextFactory):
    def __init__(self, certificates_filenames):
        self.certificates_filenames = list(certificates_filenames)

    def verify(self, connection, x509, errnum, errdepth, ok):
        return ok

    def getContext(self):
        ctx = ssl.ClientContextFactory.getContext(self)
        for cert in self.certificates_filenames:
            try:
                ctx.load_verify_locations(cert)
            except:
                pass
        ctx.set_verify(SSL.VERIFY_PEER | SSL.VERIFY_FAIL_IF_NO_PEER_CERT , self.verify)
        return ctx


def downloadSSL(url, fileOrName, progress_func, certificates_filenames):
    global _UserAgentString
    scheme, host, port, path = parseurl(url)
    if not isinstance(certificates_filenames, types.ListType):
        certificates_filenames = [certificates_filenames, ]
    cert_found = False
    for cert in certificates_filenames:
        if os.path.isfile(cert) and os.access(cert, os.R_OK):
            cert_found = True
            break
    if not cert_found:
        return fail('no one ssl certificate found')
    factory = HTTPDownloader(url, fileOrName, agent=_UserAgentString)
    contextFactory = MyClientContextFactory(certificates_filenames)
    reactor.connectSSL(host, port, factory, contextFactory)
    return factory.deferred

#------------------------------------------------------------------------------

class NoVerifyClientContextFactory:
    isClient = 1
    method = SSL.SSLv3_METHOD
    def getContext(self):
        def x(*args):
            return True
        ctx = SSL.Context(self.method)
        #print dir(ctx)
        ctx.set_verify(SSL.VERIFY_NONE,x)
        return ctx

def downloadSSL2(url, fileOrName, progress_func, certificates_filenames=[]):
    global _UserAgentString
    factory = HTTPDownloader(url, fileOrName, agent=_UserAgentString)

    if proxy_is_on():
        factory.path = url
        # TODO
        # need to check certificate too
        contextFactory = MyClientContextFactory(certificates_filenames)
        reactor.connectSSL(get_proxy_host(), get_proxy_port(), factory, contextFactory)

    else:
        scheme, host, port, path = parseurl(url)
        if not isinstance(certificates_filenames, types.ListType):
            certificates_filenames = [certificates_filenames, ]
        cert_found = False
        for cert in certificates_filenames:
            if os.path.isfile(cert) and os.access(cert, os.R_OK):
                cert_found = True
                break
        if not cert_found:
            return fail('no one ssl certificate found')
        contextFactory = MyClientContextFactory(certificates_filenames)
        reactor.connectSSL(host, port, factory, contextFactory)

    return factory.deferred

#-------------------------------------------------------------------------------

class ProxyClientFactory(client.HTTPClientFactory):
    def setURL(self, url):
        client.HTTPClientFactory.setURL(self, url)
        self.path = url

def getPageTwisted(url, timeout=0):
    global _UserAgentString
    if proxy_is_on():
        factory = ProxyClientFactory(url, agent=_UserAgentString, timeout=timeout)
        reactor.connectTCP(get_proxy_host(), get_proxy_port(), factory)
        factory.deferred.addCallback(ConnectionDone, 'http', 'getPageTwisted proxy %s' % (url))
        factory.deferred.addErrback(ConnectionFailed, 'http', 'getPageTwisted proxy %s' % (url))
        return factory.deferred
    else:
        d = getPage(url, agent=_UserAgentString, timeout=timeout)
        d.addCallback(ConnectionDone, 'http', 'getPageTwisted %s' % url)
        d.addErrback(ConnectionFailed, 'http', 'getPageTwisted %s' % url)
        return d

#------------------------------------------------------------------------------

def downloadHTTP(url, fileOrName):
    global _UserAgentString
    scheme, host, port, path = parseurl(url)
    factory = HTTPDownloader(url, fileOrName, agent=_UserAgentString)
    if proxy_is_on():
        host = get_proxy_host()
        port = get_proxy_port()
        factory.path = url
    reactor.connectTCP(host, port, factory)
    return factory.deferred

#-------------------------------------------------------------------------------

def IpIsLocal(ip):
    if ip == '':
        return True
    if ip == '0.0.0.0':
        return True
    if ip.startswith('192.168.'):
        return True
    if ip.startswith('10.'):
        return True
    if ip.startswith('127.'):
        return True
    if ip.startswith('172.'):
        try:
            secondByte = int(ip.split('.')[1])
        except:
            raise Exception('wrong ip address ' + str(ip))
            return True
        if secondByte >= 16 and secondByte <= 31:
            return True
    return False

#-------------------------------------------------------------------------------

def getLocalIpError():
    import socket
    addr = socket.gethostbyname(socket.gethostname())
    if addr == "127.0.0.1" and os.name == 'posix':
        import commands
        output = commands.getoutput("/sbin/ifconfig")
        #TODO parseaddress not done yet
        addr = parseaddress(output)
    return addr


#http://ubuntuforums.org/showthread.php?t=1215042
def getLocalIp(): # had this in p2p/stun.py
    import socket
    # 1: Use the gethostname method

    try:
        ipaddr = socket.gethostbyname(socket.gethostname())
        if not( ipaddr.startswith('127') ) :
            #print('Can use Method 1: ' + ipaddr)
            return ipaddr
    except:
        pass

    # 2: Use outside connection
    '''
    Source:
    http://commandline.org.uk/python/how-to-find-out-ip-address-in-python/
    '''

    ipaddr=''
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('google.com', 0))
        ipaddr=s.getsockname()[0]
        #print('Can used Method 2: ' + ipaddr)
        return ipaddr
    except:
        pass


    # 3: Use OS specific command
    import subprocess , platform
    ipaddr=''
    os_str=platform.system().upper()

    if os_str=='LINUX' :

        # Linux:
        arg='ip route list'
        p=subprocess.Popen(arg,shell=True,stdout=subprocess.PIPE)
        data = p.communicate()
        sdata = data[0].split()
        ipaddr = sdata[ sdata.index('src')+1 ]
        #netdev = sdata[ sdata.index('dev')+1 ]
        #print('Can used Method 3: ' + ipaddr)
        return ipaddr

    elif os_str=='WINDOWS' :

        # Windows:
        arg='route print 0.0.0.0'
        p=subprocess.Popen(arg,shell=True,stdout=subprocess.PIPE)
        data = p.communicate()
        strdata=data[0].decode()
        sdata = strdata.split()

        while len(sdata)>0:
            if sdata.pop(0)=='Netmask' :
                if sdata[0]=='Gateway' and sdata[1]=='Interface' :
                    ipaddr=sdata[6]
                    break
        #print('Can used Method 4: ' + ipaddr)
        return ipaddr

    return '127.0.0.1' # uh oh, we're in trouble, but don't want to return none

#-------------------------------------------------------------------------------

def TestInternetConnectionOld(remote_host='www.google.com'): # 74.125.113.99
#    return True

    try:
        (family, socktype, proto, garbage, address) = socket.getaddrinfo(remote_host, "http")[0]
    except Exception, e:
        return False

    s = socket.socket(family, socktype, proto)

    try:
        result = s.connect(address)
    except Exception, e:
        return False

    return result is None or result == 0

#------------------------------------------------------------------------------ 

def TestInternetConnectionOld2(remote_hosts=None, timeout=10):
    if remote_hosts is None:
        remote_hosts = []
        remote_hosts.append('www.google.com')
        remote_hosts.append('www.facebook.com')
        remote_hosts.append('www.youtube.com')
        # remote_hosts.append('www.yahoo.com')
        # remote_hosts.append('www.baidu.com')
    def _response(src, result):
        print '_response', err, hosts, index
        result.callback(None)
    def _fail(err, hosts, index, result):
        print 'fail', hosts, index
        reactor.callLater(0, _call, hosts, index+1, result)
    def _call(hosts, index, result):
        print 'call' , hosts, index, result
        if index >= len(hosts):
            result.errback(None)
            return
        print '    ', hosts[index]
        d = getPageTwisted(hosts[index])
        d.addCallback(_response, result)
        d.addErrback(_fail, hosts, index, result)
    result = Deferred()
    reactor.callLater(0, _call, remote_hosts, 0, result)
    return result
        
#------------------------------------------------------------------------------  

def TestInternetConnection(remote_hosts=None, timeout=10):
    if remote_hosts is None:
        remote_hosts = []
        remote_hosts.append('http://www.google.com')
        remote_hosts.append('http://www.facebook.com')
        remote_hosts.append('http://www.youtube.com')
        # remote_hosts.append('www.yahoo.com')
        # remote_hosts.append('www.baidu.com')
    dl = []
    for host in remote_hosts:
        dl.append(getPageTwisted(host, timeout))
    return DeferredList(dl, fireOnOneCallback=True, fireOnOneErrback=False, consumeErrors=True)
        
#------------------------------------------------------------------------------ 

def SendEmail(TO, FROM, HOST, PORT, LOGIN, PASSWORD, SUBJECT, BODY, FILES):
#    try:
        import smtplib
        from email import Encoders
        from email.MIMEText import MIMEText
        from email.MIMEBase import MIMEBase
        from email.MIMEMultipart import MIMEMultipart
        from email.Utils import formatdate

        msg = MIMEMultipart()
        msg["From"] = FROM
        msg["To"] = TO
        msg["Subject"] = SUBJECT
        msg["Date"]    = formatdate(localtime=True)
        msg.attach(MIMEText(BODY))

        # attach a file
        for filePath in FILES:
            if not os.path.isfile(filePath):
                continue
            part = MIMEBase('application', "octet-stream")
            part.set_payload( open(filePath,"rb").read() )
            Encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(filePath))
            msg.attach(part)

        s = smtplib.SMTP(HOST, PORT)

        #s.set_debuglevel(True) # It's nice to see what's going on

        s.ehlo() # identify ourselves, prompting server for supported features

        if s.has_extn('STARTTLS'):
            s.starttls()
            s.ehlo() # re-identify ourse

        s.login(LOGIN, PASSWORD)  # optional

        failed = s.sendmail(FROM, TO, msg.as_string())

        s.close()

#    except:
#        dhnio.DprintException()


#-------------------------------------------------------------------------------

# Great Thanks to Mariano!
# http://marianoiglesias.com.ar/python/file-uploading-with-multi-part-encoding-using-twisted/

class StringReceiver(protocol.Protocol):
    buffer = ""

    def __init__(self, deferred=None):
        self._deferred = deferred

    def dataReceived(self, data):
        self.buffer += data

    def connectionLost(self, reason):
        if self._deferred and reason.check(client.ResponseDone):
            self._deferred.callback(self.buffer)
        else:
            self._deferred.errback(Exception(self.buffer))
            
class MultiPartProducer:
    implements(iweb.IBodyProducer)
    CHUNK_SIZE = 2 ** 8
    def __init__(self, files={}, data={}, callback=None, deferred=None):
        self._files = files
        self._file_lengths = {}
        self._data = data
        self._callback = callback
        self._deferred = deferred
        self.boundary = self._boundary()
        self.length = self._length()
        
    def startProducing(self, consumer):
        self._consumer = consumer
        self._current_deferred = Deferred()
        self._sent = 0
        self._paused = False
        if not hasattr(self, "_chunk_headers"):
            self._build_chunk_headers()
        if self._data:
            block = ""
            for field in self._data:
                block += self._chunk_headers[field]
                block += self._data[field]
                block += "\r\n"
            self._send_to_consumer(block)
        if self._files:
            self._files_iterator = self._files.iterkeys()
            self._files_sent = 0
            self._files_length = len(self._files)
            self._current_file_path = None
            self._current_file_handle = None
            self._current_file_length = None
            self._current_file_sent = 0
            result = self._produce()
            if result:
                return result
        else:
            return succeed(None)
        return self._current_deferred
    
    def resumeProducing(self):
        self._paused = False
        result = self._produce()
        if result:
            return result
        
    def pauseProducing(self):
        self._paused = True
        
    def stopProducing(self):
        self._finish(True)
        if self._deferred and self._sent < self.length:
            self._deferred.errback(Exception("Consumer asked to stop production of request body (%d sent out of %d)" % (self._sent, self.length)))
            
    def _produce(self):
        if self._paused:
            return
        done = False
        while not done and not self._paused:
            if not self._current_file_handle:
                field = self._files_iterator.next()
                self._current_file_path = self._files[field]
                self._current_file_sent = 0
                self._current_file_length = self._file_lengths[field]
                self._current_file_handle = open(self._current_file_path, "rb")
                self._send_to_consumer(self._chunk_headers[field])
            chunk = self._current_file_handle.read(self.CHUNK_SIZE)
            if chunk:
                self._send_to_consumer(chunk)
                self._current_file_sent += len(chunk)
            if not chunk or self._current_file_sent == self._current_file_length:
                self._send_to_consumer("\r\n")
                self._current_file_handle.close()
                self._current_file_handle = None
                self._current_file_sent = 0
                self._current_file_path = None
                self._files_sent += 1
            if self._files_sent == self._files_length:
                done = True
        if done:
            self._send_to_consumer("--%s--\r\n" % self.boundary)
            self._finish()
            return succeed(None)
        
    def _finish(self, forced=False):
        if hasattr(self, "_current_file_handle") and self._current_file_handle:
            self._current_file_handle.close()
        if self._current_deferred:
            self._current_deferred.callback(self._sent)
            self._current_deferred = None
        if not forced and self._deferred:
            self._deferred.callback(self._sent)
            
    def _send_to_consumer(self, block):
        self._consumer.write(block)
        self._sent += len(block)
        if self._callback:
            self._callback(self._sent, self.length)
            
    def _length(self):
        self._build_chunk_headers()
        length = 0
        if self._data:
            for field in self._data:
                length += len(self._chunk_headers[field])
                length += len(self._data[field])
                length += 2
        if self._files:
            for field in self._files:
                length += len(self._chunk_headers[field])
                length += self._file_size(field)
                length += 2
        length += len(self.boundary)
        length += 6
        return length
    
    def _build_chunk_headers(self):
        if hasattr(self, "_chunk_headers") and self._chunk_headers:
            return
        self._chunk_headers = {}
        for field in self._files:
            self._chunk_headers[field] = self._headers(field, True)
        for field in self._data:
            self._chunk_headers[field] = self._headers(field)
            
    def _headers(self, name, is_file=False):
        value = self._files[name] if is_file else self._data[name]
        _boundary = self.boundary.encode("utf-8") if isinstance(self.boundary, unicode) else urllib.quote_plus(self.boundary)
        headers = ["--%s" % _boundary]
        if is_file:
            disposition = 'form-data; name="%s"; filename="%s"' % (name, os.path.basename(value))
        else:
            disposition = 'form-data; name="%s"' % name
        headers.append("Content-Disposition: %s" % disposition)
        if is_file:
            file_type = self._file_type(name)
        else:
            file_type = "text/plain; charset=utf-8"
        headers.append("Content-Type: %s" % file_type)
        if is_file:
            headers.append("Content-Length: %i" % self._file_size(name))
        else:
            headers.append("Content-Length: %i" % len(value))
        headers.append("")
        headers.append("")
        return "\r\n".join(headers)
    
    def _boundary(self):
        boundary = None
        try:
            import uuid
            boundary = uuid.uuid4().hex
        except ImportError:
            import random, sha
            bits = random.getrandbits(160)
            boundary = sha.new(str(bits)).hexdigest()
        return boundary
    
    def _file_type(self, field):
        type = mimetypes.guess_type(self._files[field])[0]
        return type.encode("utf-8") if isinstance(type, unicode) else str(type)
    
    def _file_size(self, field):
        size = 0
        try:
            handle = open(self._files[field], "r")
            size = os.fstat(handle.fileno()).st_size
            handle.close()
        except:
            size = 0
        self._file_lengths[field] = size
        return self._file_lengths[field]
       
#------------------------------------------------------------------------------ 

def uploadHTTP(url, files, data, progress=None, receiverDeferred=None):
    # producerDeferred = Deferred()
    receiverDeferred = Deferred()
    
    myProducer = MultiPartProducer(files, data, progress) #, producerDeferred)
    myReceiver = StringReceiver(receiverDeferred)
    
    headers = http_headers.Headers()
    headers.addRawHeader("Content-Type", "multipart/form-data; boundary=%s" % myProducer.boundary)
    
    agent = client.Agent(reactor)
    request = agent.request("POST", url, headers, myProducer)
    request.addCallback(lambda response: response.deliverBody(myReceiver))
    
#------------------------------------------------------------------------------ 

# return a list of IPs for current active network interfaces 
def getNetworkInterfaces():
    import platform
    plat = platform.uname()[0]
    
    if plat == 'Windows':
        import re
        dirs = ['', r'c:\windows\system32', r'c:\winnt\system32']
        try:
            import ctypes
            buffer = ctypes.create_string_buffer(300)
            ctypes.windll.kernel32.GetSystemDirectoryA(buffer, 300)
            dirs.insert(0, buffer.value.decode('mbcs'))
        except:
            return []
        for dir in dirs:
            try:
                pipe = os.popen(os.path.join(dir, 'ipconfig') + ' /all')
            except IOError:
                return []
            rawtxt = unicode(pipe.read())
            ips_unicode = re.findall(u'^.*?IP.*?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}).*$', rawtxt, re.U | re.M)
            ips = []
            for ip in ips_unicode:
                ips.append(str(ip))
            del ips_unicode
            return ips
        
#    elif plat == 'Linux':
#        try:
#            pipe = os.popen("/bin/ip -f inet a")
#        except IOError:
#            return []
#        print 'getNetworkInterfaces', pipe
#        try:
#            rawtxt = unicode(pipe.read())
#            lines = rawtxt.splitlines()
#        except:
#            return []
#        print 'getNetworkInterfaces:\n', rawtext
#        ips = set()
#        # ifaces = {}
#        for line in lines:
#            check = line.strip('\n').strip().split(' ')
#            if check[0] == "inet":
#                if check[2] == "brd":
#                    check.pop(2)
#                    check.pop(2)
#                # if not ifaces.has_key(check[4]):
#                #     ifaces[check[4]] = []
#                ipaddress = check[1].split("/")[0]
#                # ifaces[check[4]].append(ipaddress)
#                ips.add(ipaddress)
#        print 'getNetworkInterfaces', ips
#        return list(ips)
    
    elif plat == 'Linux':
        import re
        ips = []
        output = subprocess.Popen(['ifconfig',], stdout=subprocess.PIPE).communicate()[0]
        # print 'getNetworkInterfaces:\n', output
        for interface in output.split('\n\n'):
            if interface.strip():
                ipaddr = re.search(r'inet addr:(\S+)', interface)
                if ipaddr:
                    ips.append(ipaddr.group(1))
        return ips
    
    else:
        return []

#------------------------------------------------------------------------------ 


def test1():
    def done(x, filen):
        print 'done'
        print x
        print open(filen).read()
    def fail(x):
        print 'fail'
        print x.getErrorMessage()

    url = 'https://downloads.datahaven.net/info.txt'
    fn = '123'
    d = downloadSSL1(url, fn, None, 'dhn.cer')
    d.addCallback(done, fn)
    d.addErrback(fail)

def test2():
    def done(x):
        #print 'done!!!!!!!!!!!!!!!!!!!!!!!!!!!'
        print x
    def fail(x):
        print 'fail'
        print x
        print x.getErrorMessage()
    url = 'http://identity.datahaven.net/veselin.xml'
    d = getPageTwisted(url)
    d.addCallback(done)
    d.addErrback(fail)

def test3():
    d = detect_proxy_settings()
    print d

def test4():
    def done(x, filen):
        print 'done'
        print x
        print open(filen).read()
    def fail(x):
        print 'fail'
        print x.getErrorMessage()

#    import settings
#    url = settings.UpdateLocationURL() + settings.CurrentVersionDigestsFilename()
    url = 'http://identity.datahaven.net/downloads/version.txt'
    fn = '123'
    d = downloadHTTP(url, fn)
    d.addCallback(done, fn)
    d.addErrback(fail)

def test5():
    SendEmail('to.datahaven@gmail.com',
              'dhnemail1@mail.offshore.ai',
              'smtp.gmail.com',
              587,
              'datahaven.net.mail@gmail.com',
              'datahaven.net.mail',
              'subj',
              'some body \n\n body',
              ['__init__.pyc'],)


def test6():
    import dhnio
    dhnio.init()
    print getNetworkInterfaces()
    
    
def test7():
    import dhnio
    dhnio.init()
    def _ok(x):
        print x
        reactor.stop()
    def _fail(x):
        print x
        reactor.stop()
    TestInternetConnection().addCallbacks(_ok, _fail)
    reactor.run()

#------------------------------------------------------------------------------ 

if __name__ == '__main__':
    #init()
    test7()
    #reactor.run()


