#bandwidth.py

import os
import time

import nameurl
import settings
import dhnio
import misc
import commands


BandInDict = {}
BandOutDict = {}
CountTimeIn = 0
CountTimeOut = 0


#------------------------------------------------------------------------------

def init():
    global CountTimeIn
    global CountTimeOut
    dhnio.Dprint(4, 'bandwidth.init ')
    fin = filenameIN()
    fout = filenameOUT()
    if not os.path.isfile(fin):
        dhnio.WriteFile(fin, '')
    if not os.path.isfile(fout):
        dhnio.WriteFile(fout, '')
    read_bandwidthIN()
    read_bandwidthOUT()
    CountTimeIn = time.time()
    CountTimeOut = time.time()


def filenameIN(basename=None):
    if basename is None:
        basename = misc.gmtime2str('%d%m%y') 
    return os.path.join(settings.BandwidthInDir(), basename)


def filenameOUT(basename=None):
    if basename is None:
        basename = misc.gmtime2str('%d%m%y') 
    return os.path.join(settings.BandwidthOutDir(), basename)


def save():
    dhnio.Dprint(6, 'bandwidth.save')
    dhnio._write_dict(filenameIN(), getBandwidthIN())
    dhnio._write_dict(filenameOUT(), getBandwidthOUT())


def saveIN(basename=None):
    if basename is None:
        basename = misc.gmtime2str('%d%m%y') 
##    dhnio.Dprint(12, 'bandwidth.saveIN ' + basename)
    ret = os.path.isfile(filenameIN(basename))
    dhnio._write_dict(filenameIN(basename), getBandwidthIN())
    if not ret:
        dhnio.Dprint(4, 'bandwidth.saveIN to new file ' + basename)
    else:
        dhnio.Dprint(12, 'bandwidth.saveIN to ' + basename)
    return ret


def saveOUT(basename=None):
    if basename is None:
        basename = misc.gmtime2str('%d%m%y') 
##    dhnio.Dprint(12, 'bandwidth.saveOUT ' + basename)
    ret = os.path.isfile(filenameOUT(basename))
    dhnio._write_dict(filenameOUT(basename), getBandwidthOUT())
    if not ret:
        dhnio.Dprint(4, 'bandwidth.saveOUT to new file ' + basename)
    else:
        dhnio.Dprint(12, 'bandwidth.saveOUT to ' + basename)
    return ret


def read_bandwidthIN():
    global BandInDict
    dhnio.Dprint(6, 'bandwidth.read_bandwidthIN ')
    for idurl, bytes in dhnio._read_dict(filenameIN(), {}).items():
        BandInDict[idurl] = int(bytes)


def read_bandwidthOUT():
    global BandOutDict
    dhnio.Dprint(6, 'bandwidth.read_bandwidthOUT ')
    for idurl, bytes in dhnio._read_dict(filenameOUT(), {}).items():
        BandOutDict[idurl] = int(bytes)


def clear_bandwidthIN():
    global BandInDict
    dhnio.Dprint(6, 'bandwidth.clear_bandwidthIN ')
    BandInDict.clear()


def clear_bandwidthOUT():
    global BandOutDict
    dhnio.Dprint(6, 'bandwidth.clear_bandwidthOUT ')
    BandOutDict.clear()


def getBandwidthIN():
    global BandInDict
    return BandInDict


def getBandwidthOUT():
    global BandOutDict
    return BandOutDict


def clear():
    clear_bandwidthIN()
    clear_bandwidthOUT()


def isExistIN():
    return os.path.isfile(filenameIN())


def isExistOUT():
    return os.path.isfile(filenameOUT())


def files2send():
    dhnio.Dprint(6, 'bandwidth.files2send')
    listIN = []
    listOUT = []
    for filename in os.listdir(settings.BandwidthInDir()):
        # if we sent the file - skip it
        if filename.endswith('.sent'):
            continue
        # if filename is not a date - skip it
        if len(filename) != 6:
            continue
        # skip today bandwidth - it is still counting, right?
        if filename == misc.gmtime2str('%d%m%y'): 
            continue
        filepath = os.path.join(settings.BandwidthInDir(), filename)
##        if filepath == filenameIN():
##            continue
        listIN.append(filepath)
    for filename in os.listdir(settings.BandwidthOutDir()):
        if filename.endswith('.sent'):
            continue
        if len(filename) != 6:
            continue
        if filename == misc.gmtime2str('%d%m%y'): #time.strftime('%d%m%y'):
            continue
        filepath = os.path.join(settings.BandwidthOutDir(), filename)
##        if filepath == filenameOUT():
##            continue
        listOUT.append(filepath)
    dhnio.Dprint(6, 'bandwidth.files2send listIN=%d listOUT=%d' % (len(listIN), len(listOUT)))
    for i in listIN:
        dhnio.Dprint(6, '  ' + i)
    for i in listOUT:
        dhnio.Dprint(6, '  ' + i)
    return listIN, listOUT


def IN(idurl, size):
    global BandInDict
    global CountTimeIn
    if not isExistIN():
        currentFileName = time.strftime('%d%m%y', time.localtime(CountTimeIn))
        if currentFileName != misc.gmtime2str('%d%m%y'):
            saveIN(currentFileName)
            clear_bandwidthIN()
            CountTimeIn = time.time()
    currentV = int(BandInDict.get(idurl, 0))
    currentV += size
    BandInDict[idurl] = currentV
    saveIN()
    dhnio.Dprint(12, 'bandwidth.IN %d(+%d) for %s. len=%d' % (
        currentV, size, idurl, len(BandInDict)))


def OUT(idurl, size):
    global BandOutDict
    global CountTimeOut
    if not isExistOUT():
        currentFileName = time.strftime('%d%m%y', time.localtime(CountTimeOut))
        if currentFileName != misc.gmtime2str('%d%m%y'):
            saveOUT(currentFileName)
            clear_bandwidthOUT()
            CountTimeOut = time.time()
    currentV = int(BandOutDict.get(idurl, 0))
    currentV += size
    BandOutDict[idurl] = currentV
    saveOUT()
    dhnio.Dprint(12, 'bandwidth.OUT %d(+%d) for %s. len=%d' % (
        currentV, size, idurl, len(BandOutDict)))


def INfile(filename, newpacket, proto, host, status):
    if status != 'finished':
        return
    try:
        sz = os.path.getsize(filename)
    except:
        dhnio.DprintException()
        return
    packet_from = newpacket.OwnerID
    if newpacket.OwnerID == misc.getLocalID() and newpacket.Command == commands.Data():
        packet_from = newpacket.RemoteID
    IN(packet_from, sz)
##    IN(packet_from, len(newpacket.Payload))


def OUTfile(filename, workitem, proto, host, status):
    if status != 'finished':
        return
    try:
        sz = os.path.getsize(filename)
    except:
        dhnio.DprintException()
        return
    OUT(workitem.remoteid, sz)
##    OUT(workitem.remoteid, workitem.payloadsize)




