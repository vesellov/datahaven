#!/usr/bin/python
#misc.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#


import os
import sys
import random
import time
import math
import hmac
import hashlib
import base64
import string
import subprocess
import re
import tempfile
import urllib
import locale


from twisted.spread import banana
from twisted.spread import jelly
from twisted.python.win32 import cmdLineQuote
from twisted.internet.defer import fail

import nonblocking
import dhnio
import settings
import identity
import dhnnet
import tmpfile
import dhnpacket
import packetid


#if __name__ == '__main__':
    #dirpath = os.path.dirname(os.path.abspath(__file__))
    #sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..', '..')))
    #print '\n'.join(sys.path)
    #sys.modules['datahaven.lib.dhnpacket'] = dhnpacket
    #sys.modules['datahaven.lib.dhnpacket'].dhnpacket = str #dhnpacket.dhnpacket
    #import datahaven.lib.dhnpacket as dhnpacket


#-------------------------------------------------------------------------------


_RemoveAfterSent = True

# Functions outside should use getLocalIdentity()
_LocalIdentity = None
_LocalIDURL = None
_LocalName = None

# if we come up with more valid transports,
# we'll need to add them here
# in the case we don't have any valid transports,
# we use this array as the default
# order is important!
# this is default order to be used for new users
# more stable transports must be higher
validTransports = [ 'http', 'cspace', 'q2q', 'tcp', 'ssh', 'email', 'skype', 'udp']

_AttenuationFactor = 1.1

#-------------------------------------------------------------------------------

def init():
    dhnio.Dprint(4, 'misc.init')

#-------------------------------------------------------------------------------

def isLocalIdentityReady():
    global _LocalIdentity
    return _LocalIdentity is not None

def setLocalIdentity(ident):
    global _LocalIdentity
    global _LocalIDURL
    global _LocalName
    _LocalIdentity = ident
    _LocalIDURL = _LocalIdentity.getIDURL()
    _LocalName = _LocalIdentity.getIDName()

def setLocalIdentityXML(idxml):
    global _LocalIdentity
    _LocalIdentity = identity.identity(xmlsrc=idxml)

def getLocalIdentity():
    """return my identity object"""
    global _LocalIdentity
    if not isLocalIdentityReady():
        loadLocalIdentity()
    return _LocalIdentity

def getLocalID():
    """return my IDURL""" 
    global _LocalIDURL
    if _LocalIDURL is None:
        localIdent = getLocalIdentity()
        if localIdent:
            _LocalIDURL = localIdent.getIDURL()
    return _LocalIDURL

def getIDName():
    """return my account name (without '.xml')"""
    global _LocalName
    if _LocalName is None:
        if isLocalIdentityReady():
            _LocalName = getLocalIdentity().getIDName()
    return _LocalName

def loadLocalIdentity():
    global _LocalIdentity
    global _LocalIDURL
    global _LocalName
    xmlid = ''
    filename = settings.LocalIdentityFilename()
    if os.path.exists(filename):
        xmlid = dhnio.ReadTextFile(filename)
        dhnio.Dprint(6, 'misc.loadLocalIdentity %d bytes read from %s' % (len(xmlid), filename))
    if xmlid == '':
        dhnio.Dprint(2, "misc.loadLocalIdentity ERROR reading local identity from " + filename)
        return
    lid = identity.identity(xmlsrc=xmlid)
    if not lid.Valid():
        dhnio.Dprint(2, "misc.loadLocalIdentity ERROR local identity is not Valid")
        return
    _LocalIdentity = lid
    _LocalIDURL = lid.getIDURL()
    _LocalName = lid.getIDName()
    setTransportOrder(getOrderFromContacts(_LocalIdentity))
    dhnio.Dprint(6, "misc.loadLocalIdentity my name is [%s]" % lid.getIDName())

def saveLocalIdentity():
    global _LocalIdentity
    if not isLocalIdentityReady():
        dhnio.Dprint(2, "misc.saveLocalIdentity ERROR localidentity not exist!")
        return
    dhnio.Dprint(6, "misc.saveLocalIdentity")
    _LocalIdentity.sign()
    xmlid = _LocalIdentity.serialize()
    filename = settings.LocalIdentityFilename()
    dhnio.WriteFile(filename, xmlid)

#------------------------------------------------------------------------------ 

def readLocalIP():
    return dhnio.ReadBinaryFile(settings.LocalIPFilename())

def readExternalIP():
    return dhnio.ReadBinaryFile(settings.ExternalIPFilename())

def readSupplierData(idurl, filename):
    path = settings.SupplierPath(idurl, filename)
    if not os.path.isfile(path):
        return ''
    return dhnio.ReadTextFile(path)

def writeSupplierData(idurl, filename, data):
    dirPath = settings.SupplierPath(idurl)
    if not os.path.isdir(dirPath):
        os.makedirs(dirPath)
    path = settings.SupplierPath(idurl, filename)
    return dhnio.WriteFile(path, data)

#-------------------------------------------------------------------------------

# let's try to make backupID as a filepath
# and keep files on remote suppliers into directory tree.
# so we will have something like remote-distributed file system
# some links to learn
# http://en.wikipedia.org/wiki/Filename 
# http://nedbatchelder.com/blog/201106/filenames_with_accents.html
# http://wiki.apache.org/subversion/NonNormalizingUnicodeCompositionAwareness
def NewBackupID(time_st=None):
    if time_st is None:
        time_st = time.localtime()
    ampm = time.strftime("%p", time_st)
    if ampm == '':
        dhnio.Dprint(2, 'misc.NewBackupID WARNING time.strftime("%p") returns empty string')
        ampm = 'AM' if time.time() % 86400 < 43200 else 'PM'
    result = "F" + time.strftime("%Y%m%d%I%M%S", time_st) + ampm
    # dhnio.Dprint(10, 'misc.NewBackupID ' + result)
    return result

def TimeFromBackupID(backupID):
    try:
        if backupID.endswith('AM') or backupID.endswith('PM'):
            ampm = backupID[-2:]
            st_time = list(time.strptime(backupID[1:-2], '%Y%m%d%I%M%S'))
        else:
            i = backupID.rfind('M')
            ampm = backupID[i-1:i+1]
            st_time = list(time.strptime(backupID[1:i-1], '%Y%m%d%I%M%S'))
        if ampm == 'PM':
            st_time[3] += 12
        return time.mktime(st_time)
    except:
        dhnio.DprintException()
        return None

# next functions are to come up with a sorted list of backup ids (dealing with AM/PM)
def modified_version(a):
    try:
        if a.endswith('AM') or a.endswith('PM'):
            int_a = int(a[1:-2])
            int_b = 0
        else:
            i = a.rfind('M')
            int_a = int(a[1:i-1])
            int_b = int(a[i+1:])
    except:
        dhnio.DprintException()
        return -1  
    hour = a[-8:-6]
    if a.endswith('PM') and hour != '12':
        int_a += 120000
    elif a.endswith('AM') and hour == '12':
        int_a -= 120000
    return int_a + int_b

def version_compare(version1, version2):
    return cmp(modified_version(version1), modified_version(version2))

def backup_id_compare(backupID1, backupID2):
    if isinstance(backupID1, tuple):
        backupID1 = backupID1[0]
        backupID2 = backupID2[0]
    pathID1, version1 = packetid.SplitBackupID(backupID1)
    pathID2, version2 = packetid.SplitBackupID(backupID2)
    if pathID1 is None or pathID2 is None:
        return 0
    if pathID1 != pathID2:
        return cmp(pathID1, pathID2)
    return version_compare(version1, version2)

def sorted_backup_ids(backupIds, reverse=False):
    sorted_ids = sorted(backupIds, backup_id_compare, reverse=reverse)
    return sorted_ids

def sorted_versions(versions, reverse=False):
    sorted_versions_list = sorted(versions, version_compare, reverse=reverse)
    return sorted_versions_list

#------------------------------------------------------------------------------ 

BASE_ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!()+-#$^&_=@[]{}`~' 
BASE_LIST = BASE_ALPHABET
BASE_DICT = dict((c, i) for i, c in enumerate(BASE_LIST))

def base_decode(string, reverse_base=BASE_DICT):
    return base64.decodestring(string)
#    length = len(reverse_base)
#    ret = 0
#    for i, c in enumerate(string[::-1]):
#        ret += (length ** i) * reverse_base[c]
#    return ret

def base_encode(string, base=BASE_LIST):
    return base64.encodestring(string)
#    length = len(base)
#    ret = ''
#    while integer != 0:
#        ret = base[integer % length] + ret
#        integer /= length
#    return ret

def FilePathToBackupID(filepath):
    # be sure the string is in unicode
    fp = dhnio.portablePath(filepath)
    # now convert to string with char codes as numbers
    result = ''
    for part in fp.split('/'):
        if part == '':
            result += '/'
            continue
        if len(result) > 0:
            # skip first separator
            # if this is Linux absolute path  
            result += '/'
        # switch from unicode if it was
        part = str(part) # unicode(part).encode()
        # word = base64.b64encode(part).replace('+', '-').replace('/', '_')
        # word = base64.b64encode(hashlib.sha1(part+os.urandom(8)).digest()).replace('+', '-').replace('/', '_').replace('=', '')
        # word = hashlib.sha1(part+os.urandom(8)).hexdigest()
        print base64.b64encode(os.urandom(6))
        word = hashlib.md5(part+os.urandom(4)).hexdigest()
        print len(word)
#        # compress the string
#        if compress:
#            # import zlib
#            # word = base_encode(zlib.compress(upart, 9))
#            word = base_encode(upart)
#        else:
#            word = u''
#            for c in upart:
#                word += '%04d' % ord(c)
#        word = word.strip()
        # print '[%s]' % word
        result += word 
    return result

def BackupIDToFilePath(backupID, decompress=False):
    result = ''
    part = ''
    ch = ''
    for c in backupID:
        if c == '/':
            if part != '':
                # base64.b64encode(part).replace('+', '-').replace('/', '_')
                result += base64.b64decode(part.replace('-', '+').replace('_', '/'))
#                if decompress:
#                    import zlib
#                    # result += zlib.decompress(base_decode(part))
#                    result += base_decode(part)
#                else:
#                    result += part
            result += c
            part = ''
        else:
            part += c
#            if decompress:
#                part += c
#            else:
#                ch += c
#                if len(ch) == 4:
#                    try:
#                        v = int(ch)
#                    except:
#                        dhnio.DprintException()
#                    part += unichr(v)
#                    ch = ''
    if part:
        result += base64.b64decode(part.replace('-', '+').replace('_', '/'))
        # result += part
#        if decompress:
#            import zlib
#            result += zlib.decompress(base_decode(part))
#        else:
#            result += part
    # we return string in unicode
    return unicode(result)

#------------------------------------------------------------------------------ 

def DigitsOnly(input, includes=''):
    return ''.join([c for c in input if c in '0123456789' + includes])

def ToInt(input, default=0):
    try:
        return int(input)
    except:
        return default
    
def ToFloat(input, default=0.0):
    try:
        return float(input)
    except:
        return default

def IsDigitsOnly(input):
    for c in input:
        if c not in '0123456789':
            return False
    return True

#------------------------------------------------------------------------------ 

def ValidUserName(username):
    if len(username) < settings.MinimumUsernameLength():
        return False
    if len(username) > settings.MaximumUsernameLength():
        return False
    for c in username:
        if c not in settings.LegalUsernameChars():
            return False
    if username[0] not in set('abcdefghijklmnopqrstuvwxyz'):
        return False
    if username.startswith('dhn'):
        return False
    return True

def ValidEmail(email, full_check=True):
    regexp = '^[\w\-\.\@]*$'
    if re.match(regexp,email) == None:
        return False
    if email.startswith('.'):
        return False
    if email.endswith('.'):
        return False
    if email.startswith('-'):
        return False
    if email.endswith('-'):
        return False
    if email.startswith('@'):
        return False
    if email.endswith('@'):
        return False
    if len(email) < 3:
        return False
    if full_check:
        regexp2 = '^[\w\-\.]*\@[\w\-\.]*$'
        if re.match(regexp2,email) == None:
            return False
    return True

def ValidPhone(value):
    regexp = '^[ \d\-\+]*$'
    if re.match(regexp,value) == None:
        return False
    if len(value) < 5:
        return False
    return True

def ValidName(value):
    regexp = '^[\w\-]*$'
    if re.match(regexp, value) == None:
        return False
    if len(value) > 100:
        return False
    return True

def MakeValidHTMLComment(text):
    ret = ''
    for c in text:
        if c in set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-+*/=_()[]{}:;,.?!@#$%|~ "):
            ret += c
    return ret

def ValidateBitCoinAddress(strAddr):
    """ does simple validation of a bitcoin address. 
    param : strAddr : an ASCII or unicode string, of a bitcoin public address.
    returns : boolean, indicating that the address has a correct format.
    http://www.rugatu.com/questions/3255/anybody-has-python-code-to-verifyvalidate-bitcoin-address"""
    # The first character indicates the "version" of the address.
    CHARS_OK_FIRST = "123"
    # alphanumeric characters without : l I O 0
    CHARS_OK = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    # We do not check the high length limit of the adress. 
    if len(strAddr) < 27:
        return False
    if len(strAddr) > 35:
        return False
    if strAddr[0] not in CHARS_OK_FIRST:
        return False
    # We use the function "all" by passing it an enumerator as parameter. 
    # It does a little optimisation : 
    # if one of the character is not valid, the next ones are not tested.
    return all( ( char in CHARS_OK for char in strAddr[1:] ) )

#------------------------------------------------------------------------------ 

# For some things we need to have files which are round sizes
# for example some encryption needs files that are multiples of 8 bytes
# This function rounds filename up to the next multiple of stepsize
def RoundupFile(filename, stepsize):
    try:
        size = os.path.getsize(filename)
    except:
        return
    mod = size % stepsize;
    increase=0;
    if mod > 0:
        increase = stepsize - mod
        file = open(filename,'a')         # append
#        for i in range (0, increase):
#            file.write(' ')
        file.write(' '*increase)
        file.close()

def RoundupString(data, stepsize):
    size = len(data)
    mod = size % stepsize
    increase = 0
    addon = ''
    if mod > 0:
        increase = stepsize-mod
#        for i in range(0,increase):
#            addon = addon + ' '
        addon = ' ' * increase
    return data + addon

def AddNL(s):
    return s + "\n"

def Data():
    return "Data"

def Parity():
    return "Parity"

# Have had some troubles with jelly/banana
# Plan to move to my own serialization of objects but leaving this here for now
def BinaryToAscii(input):
    return base64.encodestring(input)

def AsciiToBinary(input):
    return base64.decodestring(input)

def ObjectToString(input):
    banana.setPrefixLimit(200000000)                              # 200 MB is ok - does not work
    banana.SIZE_LIMIT = 200000000                                 # PREPRO not sure this is nice
    return banana.encode(jelly.jelly(input))

def StringToObject(input):
    banana.setPrefixLimit(200000000)                              # 200 MB is ok
    banana.SIZE_LIMIT = 200000000                                 # PREPRO not sure this is nice
    if len(input) == 0:
        dhnio.Dprint(1, 'misc.StringToObject ERROR in banana.decode, data length=0')
        return None
    try:
        bananaDecode = banana.decode(input)
    except:
#         try:
#             _data = input
#             ver, x, _data = _data.partition(' ')
#             cmd, x, _data = _data.partition(' ')
#             portorlength, x, _data = _data.partition(' ')
#             int(ver)
#             # assert cmd in ['length', 'port']
#             int(portorlength)
#             input = _data
#             bananaDecode = banana.decode(input)
#         except:
            if len(input) > 0:
                fd, filename = tmpfile.make('other', '', 'banana.error-')
                os.write(fd, input)
                os.close(fd)
            dhnio.Dprint(1, 'misc.StringToObject ERROR in banana.decode, data length=%d' % len(input))
            dhnio.DprintException()
            return None
    
    try:
        # works for 384 bit RSA keys
        unjellyObject = jelly.unjelly(bananaDecode)
    except:
        # small patch to fix new dhnpacket location
        # this is for oldest code to understand newest code
        if bananaDecode[0] in [
                'lib.dhnpacket.dhnpacket',
                'p2p.datahaven.lib.dhnpacket.dhnpacket',
                ]:
            bananaDecode[0] = 'datahaven.lib.dhnpacket.dhnpacket'

        # different versions need to understand each other
        # this is for newest code to understand oldest code
        elif bananaDecode[0] == 'datahaven.lib.dhnpacket.dhnpacket':
            bananaDecode[0] = 'lib.dhnpacket.dhnpacket'

        # try again
        try:
            unjellyObject = jelly.unjelly(bananaDecode)
            dhnio.Dprint(4, 'misc.StringToObject bananaDecode[0]=%s' % str(bananaDecode[0]))
        except:
            if len(bananaDecode) > 0:
                fd, filename = tmpfile.make('other', '', 'jelly.error-')
                os.write(fd, input)
                os.close(fd)
            dhnio.Dprint(1, 'misc.StringToObject ERROR in jelly.unjelly, data length=%d' % len(str(input)))
            dhnio.DprintException()
            return None

    return unjellyObject

def ObjectToAscii(input):
    return BinaryToAscii(ObjectToString(input))

def AsciiToObject(input):
    return StringToObject(AsciiToBinary(input))              # works for 384 bit RSA keys

def pack_url_param(s):
    try:
        return urllib.quote(s)
    except:
        try:
            return str(urllib.quote(str(s)))
        except:
            dhnio.DprintException()
    return s

def unpack_url_param(s, default=None):
    if s is None or s == '':
        if default is not None:
            return default
        return s
    try:
        return urllib.unquote(str(s))
    except:
        dhnio.DprintException()
        return default

def rndstr(length):
    return ''.join([random.choice(string.letters+string.digits) for i in range(0,length)])

def stringToLong(s):
    return long('\0'+s, 256)

def longToString(n):
    s = n.tostring()
    if s[0] == '\0' and s != '\0':
        s = s[1:]
    return s

def receiptIDstr(receipt_id):
    try:
        return '%08d' % int(receipt_id)
    except:
        return str(receipt_id)

def username2idurl(username, host='identity.datahaven.net'):
    return 'http://' + host + '/' + username + '.xml'

def calculate_best_dimension(sz, maxsize=8):
    cached = {2: (2,1), 
              4:(4,1),
              7:(4,2),
              13:(5,3),
              18:(6,3),
              26:(7,4),
              64:(8,8)}.get(sz, None)
    if cached:
        return cached
    try:
        w = math.sqrt(sz)
        h = sz / w
    except:
        dhnio.DprintException()
    w = w * 1.4
    h = h / 1.4
    if int(w) * int(h) < sz and int(h) > 0:
        w += 1.0
    if w > maxsize:
        w = float(maxsize)
        h = sz / w
    w = int(w)
    h = int(h)
    w = 1 if w==0 else w
    h = 1 if h==0 else h
    if w * h < sz:
        h += 1
    if w * h - sz > h:
        w -= 1 
    return w, h

def calculate_padding(w, h):
    imgW = 64
    imgH = 64
    if w >= 4:
        imgW = 4 * imgW / w
        imgH = 4 * imgH / w
    padding = 64/w - 8
    return imgW, imgH, padding

def getDeltaTime(tm):
    try:
#        tm = time.mktime(time.strptime(self.backupID, "F%Y%m%d%I%M%S%p"))
        dt = round(time.time() - tm)
        if dt > 2*60*60:
            return round(dt/(60.0*60.0)), 'hours'
        if dt > 60:
            return round(dt/60.0), 'minutes'
        return dt, 'seconds'
    except:
        return None, None

def getRealHost(host, port=None):
    if isinstance(host, str):
        if host.startswith('http://'):
            host = host[7:]
        elif host.startswith('cspace://'):
            host = host[9:]
        if port is not None:
            host += ':' + str(port)
    elif isinstance(host, tuple) and len(host) == 2:
        host = host[0] + ':' + str(host[1])
    elif host is None:
        host = 'None'
    else:
        if getattr(host, 'host', None) is not None:
            if getattr(host, 'port', None) is not None:
                host = str(getattr(host, 'host')) + ':' + str(getattr(host, 'port'))
            else:
                host = str(getattr(host, 'host'))
        elif getattr(host, 'underlying', None) is not None:
            host = str(getattr(host, 'underlying'))
        else:
            host = str(host)
            if port is not None:
                host += ':' + str(port)
    return host


#split strings "%dx%d+%d+%d" into 4 integers
def split_geom_string(geomstr):
    try:
        r = re.split('\D+', geomstr, 4)
        return int(r[0]), int(r[1]), int(r[2]), int(r[3])
    except:
        return None, None, None, None


def percent2string(percent, precis=3):
    s = str(round(percent, precis))
    if s[-2:] == '.0':
        s = s[:-2]
    return s + '%'

#def FloatToString(input):
#    formatted = '%.10f' % (input)
#    stripped = re.split('0+$', formatted)
#    if stripped[0][-1] in ['.', ',']: # some localizations use ',' instead of '.'
#        return stripped[0] + '0'
#    else:
#        return stripped[0]
def float2str(float_value, mask='%6.8f', no_trailing_zeros=True):
    try:
        f = float(float_value)
    except:
        return float_value 
    s = mask % f
    if no_trailing_zeros:
        s = s.rstrip('0').rstrip('.')
    return s

def seconds_to_time_left_string(seconds):
    s = int(seconds)
    years = s // 31104000
    if years > 1:
        return '%d years' % years
    s = s - (years * 31104000)
    months = s // 2592000
    if years == 1:
        r = 'one year'
        if months > 0:
            r += ' and %d months' % months
        return r
    if months > 1:
        return '%d months' % months
    s = s - (months * 2592000)
    days = s // 86400
    if months == 1:
        r = 'one month'
        if days > 0:
            r += ' and %d days' % days
        return r
    if days > 1:
        return '%d days' % days
    s = s - (days * 86400)
    hours = s // 3600
    if days == 1:
        r = 'one day'
        if hours > 0:
            r += ' and %d hours' % hours
        return r 
    s = s - (hours * 3600)
    minutes = s // 60
    seconds = s - (minutes * 60)
    if hours >= 6:
        return '%d hours' % hours
    if hours >= 1:
        r = '%d hours' % hours
        if hours == 1:
            r = 'one hour'
        if minutes > 0:
            r += ' and %d minutes' % minutes
        return r
    if minutes == 1:
        r = 'one minute'
        if seconds > 0:
            r += ' and %d seconds' % seconds
        return r
    if minutes == 0:
        return '%d seconds' % seconds
    if seconds == 0:
        return '%d minutes' % minutes
    return '%d minutes and %d seconds' % (minutes, seconds)

#------------------------------------------------------------------------------ 

def unicode_to_str_safe(unicode_string, encodings=None):
    try:
        return str(unicode_string) # .decode('utf-8')
    except:
        try:
            return unicode(unicode_string).encode(locale.getpreferredencoding(), errors='ignore')
        except:
            pass
    if encodings is None:
        encodings = [locale.getpreferredencoding(),] #  'utf-8' 
    output = ''
    for i in xrange(len(unicode_string)):
        unicode_char = unicode_string[i]
        char = '?'
        try:
            char = unicode_char.encode(encodings[0])
            # print char, encodings[0]
        except:
            for encoding in encodings:
                try:
                    char = unicode_char.encode(encoding, errors='ignore')
                    # print char, encoding
                    break
                except:
                    pass
        output += char
    return output

#------------------------------------------------------------------------------

def getClipboardText():
    if dhnio.Windows():
        try:
            import win32clipboard
            import win32con
            win32clipboard.OpenClipboard()
            d = win32clipboard.GetClipboardData(win32con.CF_TEXT)
            win32clipboard.CloseClipboard()
            return d.replace('\r\n','\n')
        except:
            dhnio.DprintException()
            return ''
    elif dhnio.Linux():
        try:
            import wx
            # may crash, otherwise
            # this needs app.MainLoop() to be started 
            if not wx.TheClipboard.IsOpened():  
                do = wx.TextDataObject()
                wx.TheClipboard.Open()
                success = wx.TheClipboard.GetData(do)
                wx.TheClipboard.Close()
                if success:
                    return do.GetText()
                else:
                    return ''
            else:
                return ''
        except:
            return ''
    else:
        return ''

def setClipboardText(txt):
    if dhnio.Windows():
        try:
            import win32clipboard
            import win32con
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_TEXT, txt)
            win32clipboard.CloseClipboard()
        except:
            dhnio.DprintException()
    elif dhnio.Linux():
        try:
            import wx
            clipdata = wx.TextDataObject()
            clipdata.SetText(txt)
            if wx.TheClipboard:
                wx.TheClipboard.Open()
                wx.TheClipboard.SetData(clipdata)
                wx.TheClipboard.Close()
        except:
            dhnio.DprintException()
    else:
        #TODO
        return
              
#------------------------------------------------------------------------------ 

def isValidTransport(transport):
    global validTransports
    if transport in validTransports:
        return True
    else:
        return False

def validateTransports(orderL):
    global validTransports
    transports = []
    for transport in orderL:
        if isValidTransport(transport):
            transports.append(transport)
        else:
            dhnio.Dprint(6, 'misc.validateTransports WARNING invalid entry int transport list: %s , ignored' % str(transport))
    if len(transports) == 0:
        dhnio.Dprint(1, 'misc.validateTransports ERROR no valid transports, using default transports ' + str(validTransports))
        transports = validTransports
#    if len(transports) != len(orderL):
#        dhnio.Dprint(1, 'misc.validateTransports ERROR Transports contained an invalid entry, need to figure out where it came from.')
    return transports

def setTransportOrder(orderL):
    orderl = orderL
    orderL = validateTransports(orderL)
    orderTxt = string.join(orderl, ' ')
    dhnio.Dprint(8, 'misc.setTransportOrder: ' + str(orderTxt))
    dhnio.WriteFile(settings.DefaultTransportOrderFilename(), orderTxt)

def getTransportOrder():
    global validTransports
    dhnio.Dprint(8, 'misc.getTransportOrder')
    order = dhnio.ReadTextFile(settings.DefaultTransportOrderFilename()).strip()
    if order == '':
        orderL = validTransports
    else:
        orderL = order.split(' ')
        orderL = validateTransports(orderL)
    setTransportOrder(orderL)
    return orderL

def getOrderFromContacts(ident):
    return ident.getProtoOrder()

#-------------------------------------------------------------------------------

def StartWebStream():
    dhnio.Dprint(6,"misc.StartWebStream")
    import weblog
    weblog.init(settings.getWebStreamPort())
    dhnio.SetWebStream(weblog.log)

def StopWebStream():
    dhnio.Dprint(6,"misc.StopWebStream")
    dhnio.SetWebStream(None)
    import weblog
    weblog.shutdown()

def StartWebTraffic(root=None, path='traffic'):
    dhnio.Dprint(6,"misc.StartWebStream")
    import lib.webtraffic as webtraffic
    webtraffic.init(root, path, settings.getWebTrafficPort())

def StopWebTraffic():
    dhnio.Dprint(6,"misc.StopWebTraffic")
    import lib.webtraffic as webtraffic
    webtraffic.shutdown()

#------------------------------------------------------------------------------

def hmac_hash(string):
    h = hmac.HMAC(settings.HMAC_key_word(), string)
    return h.hexdigest().upper()

def encode64(s):
    return base64.b64encode(s)

def decode64(s):
    return base64.b64decode(s)

def get_hash(src):
##    h = md5.new(src).hexdigest()
    return hashlib.md5(src).hexdigest()

def file_hash(path):
    src = dhnio.ReadBinaryFile(path)
    if not src:
        return None
    return get_hash(src)

#-------------------------------------------------------------------------------

def time2daystring(tm=None):
    tm_ = tm
    if tm_ is None:
        tm_ = time.time()
    return time.strftime('%Y%m%d', time.localtime(tm_))

def daystring2time(daystring):
    try:
        t = time.strptime(daystring, '%Y%m%d')
    except:
        return None
    return time.mktime(t)

def time2str(format):
    return time.strftime(format)

def gmtime2str(format, seconds=None):
    if not seconds:
        return time.strftime(format, time.gmtime())
    return time.strftime(format, time.gmtime(seconds))

def str2gmtime(time_string, format):
    return time.mktime(time.strptime(time_string, format))

#------------------------------------------------------------------------------ 

def ReadRepoLocation():
    if dhnio.Linux():
        repo_file = os.path.join(dhnio.getExecutableDir(), 'repo.txt')
        if os.path.isfile(repo_file):
            src = dhnio.ReadTextFile(repo_file)
            if src:
                try:
                    return src.split('\n')[0].strip(), src.split('\n')[1].strip() 
                except:
                    dhnio.DprintException()
        return 'sources', 'http://datahaven.net/download.html'
            
        #TODO need to add something - so user can change the current repository
#        if dhnio.getExecutableDir().count('/usr/share/datahaven'):
#            return 'devel', 'http://datahaven.net/apt'
#        return 'sources', 'http://datahaven.net/download.html'
    src = dhnio.ReadTextFile(settings.RepoFile()).strip()
    if src == '':
        return settings.DefaultRepo(), settings.UpdateLocationURL(settings.DefaultRepo())
    l = src.split('\n')
    if len(l) < 2:
        return settings.DefaultRepo(), settings.UpdateLocationURL(settings.DefaultRepo())
    return l[0], l[1]   

#-------------------------------------------------------------------------------

def SetAutorunWindows():
    if os.path.abspath(dhnio.getExecutableDir()) != os.path.abspath(settings.WindowsBinDir()):
        return
    createWindowsShortcut(
        'DataHaven.NET.lnk',
        '%s' % settings.getIconLaunchFilename(),
        dhnio.getExecutableDir(),
        os.path.join(dhnio.getExecutableDir(), 'icons', settings.IconFilename()),
        '',
        'Startup', )

def ClearAutorunWindows():
    removeWindowsShortcut('DataHaven.NET.lnk', folder='Startup')

#def SetAutorunWindowsOld(CUorLM='CU', location=settings.getAutorunFilename(), name=settings.ApplicationName()):
#    cmdexec = r'reg add HK%s\software\microsoft\windows\currentversion\run /v "%s" /t REG_SZ /d "%s" /f' % (CUorLM, name, location)
#    dhnio.Dprint(6, 'misc.SetAutorunWindows executing: ' + cmdexec)
#    return nonblocking.ExecuteString(cmdexec)
#
#def ClearAutorunWindowsOld(CUorLM='CU', name = settings.ApplicationName()):
#    cmdexec = r'reg delete HK%s\software\microsoft\windows\currentversion\run /v "%s" /f' % (CUorLM, name)
#    dhnio.Dprint(6, 'misc.ClearAutorunWindows executing: ' + cmdexec)
#    return nonblocking.ExecuteString(cmdexec)

#-------------------------------------------------------------------------------

def transport_control_remove_after():
    global _RemoveAfterSent
    return _RemoveAfterSent

def set_transport_control_remove_after(flag):
    global _RemoveAfterSent
    _RemoveAfterSent = flag

#-------------------------------------------------------------------------------

def pathToWindowsShortcut(filename, folder='Desktop'):
    try:
        from win32com.client import Dispatch
        shell = Dispatch('WScript.Shell')
        desktop = shell.SpecialFolders(folder)
        return os.path.join(desktop, filename)
    except:
        dhnio.DprintException()
        return ''

def createWindowsShortcut(filename, target='', wDir='', icon='', args='', folder='Desktop'):
    if dhnio.Windows():
        try:
            from win32com.client import Dispatch
            shell = Dispatch('WScript.Shell')
            desktop = shell.SpecialFolders(folder)
            path = os.path.join(desktop, filename)
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = target
            shortcut.WorkingDirectory = wDir
            shortcut.Arguments = args
            if icon != '':
                shortcut.IconLocation = icon
            shortcut.save()
        except:
            dhnio.DprintException()

def removeWindowsShortcut(filename, folder='Desktop'):
    if dhnio.Windows():
        path = pathToWindowsShortcut(filename, folder)
        if os.path.isfile(path) and os.access(path, os.W_OK):
            try:
                os.remove(path)
            except:
                dhnio.DprintException()

#-------------------------------------------------------------------------------

def pathToStartMenuShortcut(filename):
    try:
        from win32com.shell import shell, shellcon
        from win32com.client import Dispatch
        shell_ = Dispatch('WScript.Shell')
        csidl = getattr(shellcon, 'CSIDL_PROGRAMS')
        startmenu = shell.SHGetSpecialFolderPath(0, csidl, False)
        return os.path.join(startmenu, filename)
    except:
        dhnio.DprintException()
        return ''

def createStartMenuShortcut(filename, target='', wDir='', icon='', args=''):
    if dhnio.Windows():
        try:
            from win32com.shell import shell, shellcon
            from win32com.client import Dispatch
            shell_ = Dispatch('WScript.Shell')
            csidl = getattr(shellcon, 'CSIDL_PROGRAMS')
            startmenu = shell.SHGetSpecialFolderPath(0, csidl, False)
            path = os.path.join(startmenu, filename)
            shortcut = shell_.CreateShortCut(path)
            shortcut.Targetpath = target
            shortcut.WorkingDirectory = wDir
            shortcut.Arguments = args
            if icon != '':
                shortcut.IconLocation = icon
            shortcut.save()
        except:
            dhnio.DprintException()

def removeStartMenuShortcut(filename):
    if dhnio.Windows():
        path = pathToStartMenuShortcut(filename)
        if os.path.isfile(path) and os.access(path, os.W_OK):
            try:
                os.remove(path)
            except:
                dhnio.DprintException()
    return

#------------------------------------------------------------------------------ 

def DoRestart(param=''):
    if dhnio.Windows():
        if dhnio.isFrozen():
            dhnio.Dprint(2, "misc.DoRestart under Windows (Frozen), param=%s" % param)
            dhnio.Dprint(2, "misc.DoRestart sys.executable=" + sys.executable)
            dhnio.Dprint(2, "misc.DoRestart sys.argv=" + str(sys.argv))
            starter_filepath = os.path.join(dhnio.getExecutableDir(), settings.WindowsStarterFileName())
            if not os.path.isfile(starter_filepath):
                dhnio.Dprint(2, "misc.DoRestart ERROR %s not found" % starter_filepath)
                return
            cmdargs = [os.path.basename(starter_filepath),]
            if param != '':
                cmdargs.append(param)
            dhnio.Dprint(2, "misc.DoRestart cmdargs="+str(cmdargs))
            os.spawnve(os.P_DETACH, starter_filepath, cmdargs, os.environ)

        else:
            dhnio.Dprint(2, "misc.DoRestart under Windows param=%s" % param)
            dhnio.Dprint(2, "misc.DoRestart sys.executable=" + sys.executable)
            dhnio.Dprint(2, "misc.DoRestart sys.argv=" + str(sys.argv))

            pypath = sys.executable
            cmdargs = [sys.executable]
            cmdargs.append(sys.argv[0])
            cmdargs += sys.argv[1:]
            if param != '' and not sys.argv.count(param):
                cmdargs.append(param)
            if cmdargs.count('restart'):
                cmdargs.remove('restart')

            dhnio.Dprint(2, "misc.DoRestart cmdargs="+str(cmdargs))
            # os.spawnve(os.P_DETACH, pypath, cmdargs, os.environ)
            os.execvpe(pypath, cmdargs, os.environ)

    else:
        dhnio.Dprint(2, "misc.DoRestart under Linux param=%s" % param)
        dhnio.Dprint(2, "misc.DoRestart sys.executable=" + sys.executable)
        dhnio.Dprint(2, "misc.DoRestart sys.argv=" + str(sys.argv))
        
        pypyth = sys.executable
        cmdargs = [sys.executable]
        if sys.argv[0] == '/usr/share/datahaven/dhn.py':
            cmdargs.append('/usr/bin/datahaven')
        else:
            cmdargs.append(sys.argv[0])
        if param:
            cmdargs.append(param)

        pid = os.fork()
        if pid == 0:
            dhnio.Dprint(2, "misc.DoRestart cmdargs="+str(cmdargs))
            os.execvpe(pypyth, cmdargs, os.environ)
        else:
            dhnio.Dprint(2, "misc.DoRestart os.fork returned "+str(pid))
            
            
def RunBatFile(filename, output_filename=None):
    if not dhnio.Windows():
        return
    dhnio.Dprint(0, 'misc.RunBatFile going to execute ' + str(filename))

    cmd = os.path.abspath(filename).replace('\\', '/')
    if output_filename is not None:
        cmd += ' >"%s"' % os.path.abspath(output_filename).replace('\\', '/')

    return RunShellCommand(cmd, False)

#    cmdargs = [filename, ]

#    # method 1
#    try:
#        import win32process
#        BatProcess = nonblocking.Popen(
#            cmdargs,
##            shell=True,
#            stdin=subprocess.PIPE,
##            stdout=stdout_file,
##            stderr=stdout_file,
#            creationflags = win32process.CREATE_NO_WINDOW,)
#    except:
#        dhnio.Dprint(1, 'misc.RunBatFile ERROR executing: ' + str(filename))
#        dhnio.DprintException()
#        BatProcess = None
#    return BatProcess

#    # method 2
#    filename = os.path.abspath(filename).replace('\\', '/')
#    cmdargs = [filename, ]
#    if output_filename is not None:
#        cmdargs.append('>"%s"' % output_filename)
#    dhnio.Dprint(0, 'misc.RunBatFile cmdargs=' + str(cmdargs))
#    return os.spawnve(os.P_DETACH, filename, cmdargs, os.environ)


def RunShellCommand(cmdstr, wait=True):
    dhnio.Dprint(8, 'misc.RunShellCommand ' + cmdstr)
    try:
        if dhnio.Windows():
            import win32process
            p = subprocess.Popen(
                cmdstr,
                shell=True,
                creationflags = win32process.CREATE_NO_WINDOW,)
        else:
            p = subprocess.Popen(
                cmdstr,
                shell=True,)
    except:
        dhnio.DprintException()
        return None
    if wait:
        try:
            result = p.wait()
        except:
            dhnio.DprintException()
            return None
    else:
        return p.pid
    return result


def ExplorePathInOS(filepath):
    try:
        if dhnio.Windows():
            # os.startfile(filepath)
            if os.path.isfile(filepath):
                subprocess.Popen(['explorer', '/select,', '%s' % (filepath.replace('/','\\'))])
            else:
                subprocess.Popen(['explorer', '%s' % (filepath.replace('/','\\'))])

        elif dhnio.Linux():
            subprocess.Popen(['xdg-open', filepath])

        elif dhnio.Mac():
            subprocess.Popen(['open', filepath])

    except:
        try:
            import webbrowser
            webbrowser.open(filepath)
        except:
            dhnio.DprintException()
    return


#def CopyBinariesAndUserDataOnDrive(drive):
#    #TODO
#    return
#
#    if not dhnio.Windows():
#        binSize = dhnio.getDirectorySize(dhnio.getExecutableDir())
#        dataSize = dhnio.getDirectorySize(settings.BaseDir())
#
#        cmdargs1 = ['cp', '-r', dhnio.getExecutableDir(), os.path.join(drive,'DataHaven.NET')]
#        dhnio.Dprint(4, 'misc.CopyBinariesAndUserDataOnDrive call '+str(cmdargs1))
#        subprocess.call(cmdargs1)
#        cmdargs2 = ['cp', '-r', settings.BaseDir(), os.path.join(drive,'datahavennet')]
#        dhnio.Dprint(4, 'misc.CopyBinariesAndUserDataOnDrive call '+str(cmdargs2))
#        subprocess.call(cmdargs2)
#        return 'ok'
#
#    else:
#        import win32api
#        binSize = dhnio.getDirectorySize(dhnio.getExecutableDir())
#        dataSize = dhnio.getDirectorySize(settings.BaseDir())
#        t = win32api.GetDiskFreeSpace(os.path.abspath(drive))
#        freeSpace = t[0] * t[1] * t[2]
#        if binSize + dataSize + 1024 * 1024 * 5 > freeSpace:
#            return 'space %d Mb' % ((binSize + dataSize) / (1024*1024))
#
#        dir1 = os.path.abspath(os.path.join(drive,'DataHaven.NET'))
#        dir2 = os.path.abspath(os.path.join(drive,'datahavennet'))
#
#        if os.path.exists(dir1):
#            return 'exist '+dir1
#
#        if os.path.exists(dir2):
#            return 'exist '+dir2
#
#        cmdstr1 = 'mkdir ' + dir1
#        cmdstr2 = 'mkdir ' + dir2
#        cmdstr3 = 'xcopy "%s" %s /E /K /R /H /Y' % (os.path.join(dhnio.getExecutableDir(), '*.*'), dir1)
#        cmdstr4 = 'xcopy "%s" %s /E /K /R /H /Y' % (os.path.join(settings.BaseDir(), '*.*'), dir2)
#
#        if RunShellCommand(cmdstr1) is None:
#            return 'error'
#        if RunShellCommand(cmdstr2) is None:
#            return 'error'
#        if RunShellCommand(cmdstr3) is None:
#            return 'error'
#        if RunShellCommand(cmdstr4) is None:
#            return 'error'
#
#        return 'ok'


def MoveFolderWithFiles(current_dir, new_dir, remove_old=False):
    if os.path.abspath(current_dir) == os.path.abspath(new_dir):
        return
    
    current = cmdLineQuote(current_dir)
    new = cmdLineQuote(new_dir)
    
    try:
        if dhnio.Linux():
            cmdargs = ['cp', '-r', current, new]
            dhnio.Dprint(4, 'misc.MoveFolderWithFiles wish to call: ' + str(cmdargs))
            subprocess.call(cmdargs)
            if remove_old:
                cmdargs = ['rm', '-r', current]
                dhnio.Dprint(4, 'misc.MoveFolderWithFiles wish to call: ' + str(cmdargs))
                subprocess.call(cmdargs)
            return 'ok'
    
        if dhnio.Windows():
            cmdstr0 = 'mkdir %s' % new
            cmdstr1 = 'xcopy %s %s /E /K /R /H /Y' % (cmdLineQuote(os.path.join(current_dir, '*.*')), new)
            cmdstr2 = 'rmdir /S /Q %s' % current
            if not os.path.isdir(new):
                dhnio.Dprint(4, 'misc.MoveFolderWithFiles wish to call: ' + str(cmdstr0))
                if RunShellCommand(cmdstr0) is None:
                    return 'error'
                dhnio.Dprint(4, 'misc.MoveFolderWithFiles wish to call: ' + str(cmdstr1))
            if RunShellCommand(cmdstr1) is None:
                return 'error'
            if remove_old:
                dhnio.Dprint(4, 'misc.MoveFolderWithFiles wish to call: ' + str(cmdstr2))
                if RunShellCommand(cmdstr2) is None:
                    return 'error'
            return 'ok'
        
    except:
        return 'failed'
    
    return 'ok'

#------------------------------------------------------------------------------

def UpdateDesktopShortcut():
    dhnio.Dprint(6, 'misc.UpdateDesktopShortcut')
    if dhnio.Windows() and dhnio.isFrozen():
        if settings.getGeneralDesktopShortcut():
            if not os.path.exists(pathToWindowsShortcut(settings.getIconLinkFilename())):
                createWindowsShortcut(
                    settings.getIconLinkFilename(),
                    '%s' % settings.getIconLaunchFilename(),
                    dhnio.getExecutableDir(),
                    os.path.join(dhnio.getExecutableDir(), 'icons', settings.IconFilename()),
                    'show' )
        else:
            if os.path.exists(pathToWindowsShortcut(settings.getIconLinkFilename())):
                removeWindowsShortcut(settings.getIconLinkFilename())

    # under Linux we need to mark file to be executable.
    # let's disable the desktop icon for now
    # elif dhnio.Linux():
        # if settings.getGeneralDesktopShortcut():
        #     RunShellCommand("xdg-desktop-icon install --novendor datahaven.desktop")
        # else:
        #     RunShellCommand("xdg-desktop-icon uninstall datahaven.desktop")


def UpdateStartMenuShortcut():
    dhnio.Dprint(6, 'misc.UpdateStartMenuShortcut')
    if dhnio.Windows() and dhnio.isFrozen():
        if settings.getGeneralStartMenuShortcut():
            if not os.path.exists(pathToStartMenuShortcut(settings.getIconLinkFilename())):
                createStartMenuShortcut(
                    settings.getIconLinkFilename(),
                    '%s' % settings.getIconLaunchFilename(),
                    dhnio.getExecutableDir(),
                    os.path.join(dhnio.getExecutableDir(), 'icons', settings.IconFilename()),
                    'show' )
        else:
            if os.path.exists(pathToStartMenuShortcut(settings.getIconLinkFilename())):
                removeStartMenuShortcut('Data Haven .NET.lnk')

    # we do not need this at all
    # .deb file will take care of the application menu shortcut
    # elif dhnio.Linux():
    #     if settings.getGeneralStartMenuShortcut():
    #         RunShellCommand("xdg-desktop-menu install --novendor datahavenmenu.desktop")
    #     else:
    #         RunShellCommand("xdg-desktop-menu uninstall datahavenmenu.desktop")

def UpdateSettings():
    dhnio.Dprint(6, 'misc.UpdateSettings')

    # setting up a Desktop shortcuts
    # UpdateDesktopShortcut()
    # UpdateStartMenuShortcut()

    # setting up autorun
    # I just realized this.
    # we can not do this on Linux
    # we need permissions to write to the /etc/crontab
    # under Linux we can do it only during installing of datahaven package
    # Best choice is removing Autorun option at all!
    # So let's just check it every time we start (for Windows)
    # if dhnio.isFrozen() and dhnio.Windows():
    #     SetAutorunWindows()
    #     UpdateRegistryUninstall()
    # UPDATED: 
    # did a new setup installer for Windows.
    # it will handle all those things

#-------------------------------------------------------------------------------

def SendDevReportOld(subject, body, includelogs):
    try:
        filesList = []
        if includelogs:
            filesList.append(settings.LocalIdentityFilename())
            filesList.append(settings.UserConfigFilename())
            filesList.append(os.path.join(dhnio.getExecutableDir(), 'dhnmain.exe.log'))
            filesList.append(os.path.join(dhnio.getExecutableDir(), 'dhnmain.log'))
            for filename in os.listdir(settings.LogsDir()):
                filepath = os.path.join(settings.LogsDir(), filename)
                filesList.append(filepath)
        if len(filesList) > 0:
            import zipfile
            import tempfile
            import time
            username = dhnio.ReadTextFile(settings.UserNameFilename())
            zipfd, zipfilename = tempfile.mkstemp('.zip', username+'-'+time.strftime('%Y%m%d%I%M%S')+'-' )
            zfile = zipfile.ZipFile(zipfilename, "w", compression=zipfile.ZIP_DEFLATED)
            for filename in filesList:
                if os.path.isfile(filename):
                    try:
                        if os.path.getsize(filename) < 1024*512:
                            zfile.write(filename, os.path.basename(filename))
                    except:
                        pass
            zfile.close()
            filesList = [zipfilename]    
        dhnnet.SendEmail(
            'to@mail',
            'from@mail',
            'smtp.gmail.com',
            587,
            'user',
            'password',
            subject,
            body,
            filesList,)
    except:
        dhnio.DprintException()
        

def SendDevReport(subject, body, includelogs, progress=None, receiverDeferred=None):
    try:
        zipfilename = ''
        filesList = []
        if includelogs:
            filesList.append(settings.LocalIdentityFilename())
            filesList.append(settings.UserConfigFilename())
            filesList.append(os.path.join(dhnio.getExecutableDir(), 'dhnmain.exe.log'))
            filesList.append(os.path.join(dhnio.getExecutableDir(), 'dhnmain.log'))
            for filename in os.listdir(settings.LogsDir()):
                filepath = os.path.join(settings.LogsDir(), filename)
                filesList.append(filepath)
        if len(filesList) > 0:
            import zipfile
            import tempfile
            import time
            username = dhnio.ReadTextFile(settings.UserNameFilename())
            zipfd, zipfilename = tempfile.mkstemp('.zip', username+'-'+time.strftime('%Y%m%d%I%M%S')+'-' )
            zfile = zipfile.ZipFile(zipfilename, "w", compression=zipfile.ZIP_DEFLATED)
            for filename in filesList:
                if os.path.isfile(filename):
                    try:
                        # if os.path.getsize(filename) < 1024*1024*10:
                        zfile.write(filename, os.path.basename(filename))
                    except:
                        pass
            zfile.close()
        files = {}
        if zipfilename:
            files['upload'] = zipfilename
        data = {'subject': subject, 'body': body}
        dhnnet.uploadHTTP('http://datahaven.net/cgi-bin/feedback.py', files, data, progress, receiverDeferred)            
        return True 
    except:
        dhnio.DprintException()
    return False

#------------------------------------------------------------------------------ 

def GetUserProfilePicturePath():
    if dhnio.Windows():
        # http://social.msdn.microsoft.com/Forums/en/vcgeneral/thread/8c72b948-d32c-4785-930e-0d6fdf032ecc
        username = os.path.basename(os.path.expanduser('~'))
        if dhnio.windows_version() == 5: # Windows XP
            # %ALLUSERSPROFILE%\Application Data\Microsoft\User Account Pictures
            allusers = os.environ.get('ALLUSERSPROFILE', os.path.join(os.path.dirname(os.path.expanduser('~')), 'All Users'))
            return os.path.join(allusers, 'Application Data', 'Microsoft', 'User Account Pictures', username+'.bmp')
        elif dhnio.windows_version() == 6: # Windows 7
            # C:\Users\<username>\AppData\Local\Temp\<domain>+<username>.bmp 
            default_path = os.path.join(os.path.expanduser('~'), 'Application Data')
            return os.path.join(os.environ.get('APPDATA', default_path), 'Local', 'Temp', username+'.bmp')
        else:
            return ''
    elif dhnio.Linux():
        return os.path.join(os.path.expanduser('~'), '.face')
    return ''

def UpdateRegistryUninstall(uninstall=False):
    try:
        import _winreg
    except:
        return False
    
    unistallpath = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall" 
    regpath = unistallpath + "\\DataHaven.NET"
    values = {
        'DisplayIcon':      '%s,0' % str(dhnio.getExecutableFilename()),
        'DisplayName':      'DataHaven.NET',
        'DisplayVersion':   'rev'+dhnio.ReadTextFile(settings.RevisionNumberFile()).strip(),
        'InstallLocation:': settings.BaseDir(),
        'NoModify':         1,
        'NoRepair':         1,
        'UninstallString':  '%s uninstall' % dhnio.getExecutableFilename(),
        'URLInfoAbout':     'http://datahaven.net', }    

    # open
    try:
        reg = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, regpath, 0, _winreg.KEY_ALL_ACCESS)
    except:
        try:
            reg = _winreg.CreateKey(_winreg.HKEY_LOCAL_MACHINE, regpath)
        except:
            dhnio.DprintException()
            return False

    # check
    i = 0
    while True:
        try:
            name, value, typ = _winreg.EnumValue(reg, i)
        except:
            break
        i += 1
        if uninstall:
            try:
                _winreg.DeleteKey(reg, name)
            except:
                try:
                    _winreg.DeleteValue(reg, name)
                except:
                    dhnio.DprintException()
        else:
            if name == 'DisplayName' and value == 'DataHaven.NET':
                _winreg.CloseKey(reg)
                return True

    # delete
    if uninstall:
        _winreg.CloseKey(reg)
        try:
            reg = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, unistallpath, 0, _winreg.KEY_ALL_ACCESS)
        except:
            dhnio.DprintException()
            return False
        try:
            _winreg.DeleteKey(reg, 'DataHaven.NET')
        except:
            dhnio.DprintException()
            _winreg.CloseKey(reg)
            return False
        _winreg.CloseKey(reg)
        return True

    # write
    for key, value in values.items():
        typ = _winreg.REG_SZ
        if isinstance(value, int):
            typ = _winreg.REG_DWORD
        _winreg.SetValueEx(reg, key, 0, typ, value)
    _winreg.CloseKey(reg)

    return True


def MakeBatFileToUninstall(wait_appname='dhnmain.exe', local_dir=dhnio.getExecutableDir(), dirs2delete=[settings.BaseDir(),]):
    dhnio.Dprint(0, 'misc.MakeBatFileToUninstall')
    import tempfile
    batfileno, batfilename = tempfile.mkstemp('.bat', 'DataHaven.NET-uninstall-')
    batsrc = ''
    batsrc += 'cd "%s"\n' % local_dir
    batsrc += 'del search.log /Q\n'
    batsrc += ':again\n'
    batsrc += 'sleep 1\n'
    batsrc += 'tasklist /FI "IMAGENAME eq %s" /FO CSV > search.log\n' % wait_appname
    batsrc += 'FOR /F %%A IN (search.log) DO IF %%-zA EQU 0 GOTO again\n'
#    batsrc += 'start /B /D"%s" %s\n' % (local_dir, start_cmd)
#    batsrc += 'start /B /D"%s" %s\n' % (dhnio.shortPath(local_dir), start_cmd)
    for dirpath in dirs2delete:
        batsrc += 'rmdir /S /Q "%s"\n' % os.path.abspath(dirpath)
    batsrc += 'del /F /S /Q "%s"\n' % os.path.abspath(batfilename)
    print batsrc
    os.write(batfileno, batsrc)
    os.close(batfileno)
    return os.path.abspath(batfilename)

#------------------------------------------------------------------------------

def LoopAttenuation(current_delay, faster, min, max):
    global _AttenuationFactor
    if faster:
        return min
    else:
        if current_delay < max:
            return current_delay * _AttenuationFactor   
    return current_delay

#------------------------------------------------------------------------------ 

if __name__ == '__main__':
    dhnio.SetDebug(10)
    dhnio.init()
    init()

#    print time.localtime()    
#    v = NewBackupID()
#    i = v.rfind('M')
#    print v, i
#    ampm = v[i-1:i+1]
#    st_time = v[1:i-1]
#    print ampm, st_time
#    bk1 = '0/0/1/'+v+'2'
#    bk2 = '0/0/1/'+v+'1'
#    print backup_id_compare(bk1, bk2)
    
    # import base64
    # base64.
    
    # print len(BASE_ALPHABET)
    
    # a = FilePathToBackupID(sys.argv[1])
    # b = FilePathToBackupID(sys.argv[1], False)
    # b = BackupIDToFilePath(a)
    # print len(a), a
    # print b, len(b)
    # print os.path.exists(b)
    
    #debug
#    from twisted.internet import reactor
#    reactor.callLater(1, SetAutorun)
#    reactor.run()

#    target = 'C:\Program Files\DataHaven.Net\dhnmain.exe'
#    workdir = 'C:\Program Files\DataHaven.Net'


#    SetAutorun()

#    print calculate_best_dimension(2)

#    path = 'c:\\Program Files\\\xc4 \xd8 \xcd'
#    batfilename = MakeBatFile2Restart(local_dir=path)
##    RunBatFile(batfilename, settings.RunUpdateLogFilename())
#    RunBatFile(batfilename)

    #import imp
    #sys.modules['datahaven.lib.dhnpacket'] = imp.new_module('datahaven.lib.dhnpacket')
    #sys.modules['datahaven.lib.dhnpacket'].dhnpacket = dhnpacket.dhnpacket
    #.dhnpacket = dhnpacket.dhnpacket # sys.modules['dhnpacket']

    #m = sys.modules.keys()
    #m.sort()
    #print '\n'.join(m)

    #sss = open('jelly.error1').read()
    #o = StringToObject(sss)
    #print type(o), o

#    from twisted.internet.defer import setDebugging
#    setDebugging(True)

    if True:
        from twisted.internet import reactor
        from twisted.internet.defer import Deferred        
        def _progress(x, y):
            print '%d/%d' % (x,y)      
        def _done(x):
            print 'DONE', x
            reactor.stop()  
        d = Deferred()
        d.addBoth(_done)
        SendDevReport('subject ', 'some body112', True, _progress, d)
        reactor.run()
        
        
#    else:
#        SendDevReportOld('subject', 'some body\n LALALALAL\n DataHaven.NET for all!!!', True)

#    for i in range(24):
#        #print '-------------------'
#        tm = time.time()+i*60*60
#        #print tm
#        st = time.localtime(tm)
#        #print st
#        bid = NewBackupID(st)
#        #print bid
#        tm2 = TimeFromBackupID(bid)
#        #print tm2
#        ok = int(tm) == int(tm2)
#        print ok

#    for i in range(10):
#        print pow(8, i), seconds_to_time_left_string(pow(8, i))

