#nameurl.py

import re
import urllib
import urlparse

#  We assume DHN URLs are of the form ssh://host.name.com:port/fooobar.xml  maybe no foobar.xml
#  Tried urlparse and urlsplit and they move the location from the second to the 3rd
#     argument if you have "http" vs "ssh" or "tcp".  This seems like trouble.
def UrlParse(url):
    o = urlparse.urlparse(url)
    proto = o.scheme.strip()
    base = o.netloc.lstrip(' /')
    filename = o.path.lstrip(' /')
    if base == '':
        base = o.path.lstrip(' /')
        filename = ''

    if base.find('/') < 0:
        if base.find(':') < 0:
            host = base
            port = ''
        else:
            host, port = base.split(':', 1)
    else:
        host, tail = base.split('/', 1)
        if host.find(':') < 0:
            port = ''
        else:
            host, port = host.split(':', 1)

        if filename == '':
            filename = tail

    return proto.strip(), host.strip(), port.strip(), filename.strip()


def UrlMake(protocol='', machine='', port='', filename='', parts=None):
    if parts is not None:
        protocol, machine, port, filename = parts
    url = protocol+'://'+machine
    if port != '':
        url += ':'+str(port)
    if filename != '':
        url += '/'+filename
    return url


legalchars="#.-_()ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
legalset= set(legalchars)

def UrlFilename(url):
    if url is None:
        return None
    result = url.replace("://","###")
    result = result.replace("/","#")
    result = re.sub('(\:)(\d+)', '(#\g<2>#)', result)
    result = result.lower()
#    global legalset
#    # SECURITY  Test that all characters are legal ones
#    for x in result:
#        if x not in legalset:
#            raise Exception("nameurl.UrlFilename ERROR illegal character: \n" + url)
    return result

def FilenameUrl(filename):
    src = filename.strip().lower()
    if not src.startswith('http###'):
        return None
    src = re.sub('\(#(\d+)#\)', ':\g<1>', src)
    src = 'http://' + src[7:].replace('#', '/')
    return str(src)

def UrlFilenameHTML(url):
    global legalset
    s = url.replace('http://', '')
    o = ''
    for x in s:
        if x not in legalset or x == '.' or x == ':' or x == '#':
            o += '_'
        else:
            o += x
    return o

# deal with the identities
# for http://identity.datahaven.net/kinggeorge.xml
# should return "kinggeorge"
def GetName(url):
    if url in [None, 'None', '',]:
        return ''
    #return url[url.rfind("/")+1:url.rfind(".")]
    return url[url.rfind("/")+1:-4]

def GetFileName(url):
    if url in [None, 'None', ]:
        return ''
    return url[url.rfind("/")+1:]

def Quote(s):
    return urllib.quote(s, '')

def UnQuote(s):
    return urllib.unquote(s)

def main():
#    url = 'http://identity.datahaven.net:565/sdfsdfsdf/veselin2.xml'
##    url = 'ssh://34.67.22.5: 5654 /gfgfg.sdfsdf/sdfsd'
##    url = 'q2q://d5wJMQRBYD72V6Zb5aZ1@work.offshore.ai'
##    print UrlParse(url)
#    print url
#    fn =  UrlFilename(url)
#    print fn
#    ur = FilenameUrl(fn)
#    print ur
##    print filenameurl
##    print FilenameUrl(filenameurl)
##    proto, machine, port, name = UrlParse(url)
##    url2 = UrlMake(proto, machine, 1234, name)
##    print url2
##    filenameurl2 = UrlFilename(url2)
##    print filenameurl2
##    print FilenameUrl(filenameurl2)
##    print UrlParse('q2q://d5wJMQRBYD72V6Zb5aZ1@work.offshore.ai')
    print GetName(str(None))

if __name__ == '__main__':
    main()










