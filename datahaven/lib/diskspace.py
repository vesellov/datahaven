#!/usr/bin/python
#diskspace.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#


_Suffixes = {
    '':                 1.0,
    'bytes':            1.0,
    'b':                1.0,
    'KB':               1024.0,
    'Kb':               1024.0,
    'kb':               1024.0,
    'Kilobytes':        1024.0,
    'kilobytes':        1024.0,
    'MB':               1024.0*1024.0,
    'Mb':               1024.0*1024.0,
    'mb':               1024.0*1024.0,
    'Megabytes':        1024.0*1024.0,
    'megabytes':        1024.0*1024.0,
    'GB':               1024.0*1024.0*1024.0,
    'Gb':               1024.0*1024.0*1024.0,
    'gb':               1024.0*1024.0*1024.0,
    'Gigabytes':        1024.0*1024.0*1024.0,
    'gigabytes':        1024.0*1024.0*1024.0,
}

_SuffixLabels = ['bytes', 'Kb', 'Mb', 'Gb']

_MultiDict = {
        'Kb' : 1024.0,
        'Mb' : 1024.0 * 1024.0,
        'Gb' : 1024.0 * 1024.0 * 1024.0,
    }


class DiskSpace:
    def __init__(self, v = None, s = '0Mb'):
        if v is None:
            self.v = s
            if self.getSZ() not in ['Kb', 'Mb', 'Gb']:
                self.addSZ('Mb')
        else:
            self.v = str(self.getValueBest(v))
        self.b = self.getValue() * _MultiDict[self.getSZ()]
    def __repr__(self):
        return self.v
    def addSZ(self, sz):
        self.v += sz
    def setSZ(self, sz):
        self.v[-2] = sz[0]
        self.v[-1] = sz[1]
    def getSZ(self):
        return self.v[-2:]
    def getValue(self):
        try:
            return float(self.v[:-2])
        except:
            return 0.0
    def getValueBytes(self):
        return self.b
    def getValueKb(self):
        sz = self.getSZ()
        if sz == 'Gb':
            return round(self.getValue() * 1024.0 * 1024.0, 2)
        elif sz == 'Mb':
            return round(self.getValue() * 1024.0, 2)
        return self.getValue()
    def getValueMb(self):
        sz = self.getSZ().lower()
        if sz == 'Kb':
            return round(self.getValue() / 1024.0, 2)
        elif sz == 'Gb':
            return round(self.getValue() * 1024.0, 2)
        return self.getValue()
    def getValueGb(self):
        sz = self.getSZ()
        if sz == 'Kb':
            return round( self.getValue() / (1024.0 * 1024.0), 2)
        elif sz == 'Mb':
            return round( self.getValue() / 1024.0, 2)
        return self.getValue()
    def getValueBest(self, value = None):
        if value is not None:
            v = value
        else:
            v = self.getValueBytes()
        if v > _MultiDict['Gb']:
            res = round(v / _MultiDict['Gb'], 2)
            sz = 'Gb'
        elif v > _MultiDict['Mb']:
            res = round(v / _MultiDict['Mb'], 2)
            sz = 'Mb'
        else:
            res = round(v / _MultiDict['Kb'], 2)
            sz = 'Kb'
        return str(res)+sz


def SuffixIsCorrect(suffix):
    return suffix in _Suffixes.keys()

def SuffixLabels():
    return _SuffixLabels

def SameSuffix(suf1, suf2):
    if not SuffixIsCorrect(suf1):
        return False
    if not SuffixIsCorrect(suf2):
        return False
    return _Suffixes[suf1] == _Suffixes[suf2]

def MakeString(value, suf):
    if not SuffixIsCorrect(suf):
        return str(value)
    if round(float(value)) == float(value):
        return str(int(float(value))) + ' ' + suf
    return str(value) + ' ' + suf

# return (number, suffix) or (None, None)
# "342.67Mb" will return (342.67, "Mb")
def SplitString(s):
    num = s.rstrip('bytesBYTESgmkGMK ')
    suf = s.lstrip('0123456789., ').strip()
    try:
        num = float(num)
    except:
        return (None, None)

    if round(num) == num:
        num = int(num)

    if not SuffixIsCorrect(suf):
        return (None, None)

    return (num, suf)

# Make a correct value with siffix.
# 123456.789 will return "120.56 Kb"
# 123.456789 will return "123 bytes"
def MakeStringFromBytes(value):
    try:
        v = float(value)
    except:
        return value

    if v > _Suffixes['GB']:
        res = round(v / _Suffixes['GB'], 2)
        sz = 'GB'
    elif v > _Suffixes['MB']:
        res = round(v / _Suffixes['MB'], 2)
        sz = 'MB'
    elif v > _Suffixes['KB']:
        res = round(v / _Suffixes['KB'], 2)
        sz = 'KB'
    else:
        res = int(v)
        sz = 'bytes'
    return MakeString(res, sz)

# return total bytes from string with suffix or None
# "123.456 Mb" will return 129452998.656
def  GetBytesFromString(s, default=None):
    num, suf = SplitString(s)
    if num is None:
        return default
    return int(num * _Suffixes[suf])

# convert input string to a string with given suffix
# ("12.345 Mb", "Kb") will return "12641.28 Kb"
def MakeStringWithSuffix(s, suffix):
    b = GetBytesFromString(s)
    if b is None:
        return s
    if not SuffixIsCorrect(suffix):
        return s
    res = round(b / _Suffixes[suffix], 2)
    if _Suffixes[suffix] == 1.0:
        res = int(res)
    return MakeString(res, suffix)

def GetMegaBytesFromString(s):
    b = GetBytesFromString(s)
    if b is None:
        return None
    return round(b/(1024*1024), 2)

def MakeStringFromString(s):
    value, suf = SplitString(s)
    if value is None:
        return s
    return MakeString(value, suf) 

