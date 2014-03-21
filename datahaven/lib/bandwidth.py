#!/usr/bin/env python
#bandwidth.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#

"""
Here are counted incoming and outgoing traffic. 
Statistics are saved on the user's disk in the folders /bandin and /bandout in the DataHaven.NET local data dir.
This is a daily stats - a single file for every day. 
"""

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
    """
    Got a filename for today, check if already exists, read today file, start counting
    """
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
    """
    File name for incoming stats for today or other day 
    """
    if basename is None:
        basename = misc.gmtime2str('%d%m%y') 
    return os.path.join(settings.BandwidthInDir(), basename)


def filenameOUT(basename=None):
    """
    File name for outgoing stats for today or other day
    """
    if basename is None:
        basename = misc.gmtime2str('%d%m%y') 
    return os.path.join(settings.BandwidthOutDir(), basename)


def save():
    """
    Writes today stats on disk
    """
    dhnio.Dprint(6, 'bandwidth.save')
    dhnio._write_dict(filenameIN(), getBandwidthIN())
    dhnio._write_dict(filenameOUT(), getBandwidthOUT())


def saveIN(basename=None):
    """
    Writes incoming stats for today on disk 
    """
    if basename is None:
        basename = misc.gmtime2str('%d%m%y') 
    ret = os.path.isfile(filenameIN(basename))
    dhnio._write_dict(filenameIN(basename), getBandwidthIN())
    if not ret:
        dhnio.Dprint(4, 'bandwidth.saveIN to new file ' + basename)
    else:
        dhnio.Dprint(12, 'bandwidth.saveIN to ' + basename)
    return ret


def saveOUT(basename=None):
    """
    Writes outgoing stats for today on disk 
    """
    if basename is None:
        basename = misc.gmtime2str('%d%m%y') 
    ret = os.path.isfile(filenameOUT(basename))
    dhnio._write_dict(filenameOUT(basename), getBandwidthOUT())
    if not ret:
        dhnio.Dprint(4, 'bandwidth.saveOUT to new file ' + basename)
    else:
        dhnio.Dprint(12, 'bandwidth.saveOUT to ' + basename)
    return ret


def read_bandwidthIN():
    """
    Reads today's incoming bandwidth stats from disk  
    """
    global BandInDict
    dhnio.Dprint(6, 'bandwidth.read_bandwidthIN ')
    for idurl, bytes in dhnio._read_dict(filenameIN(), {}).items():
        BandInDict[idurl] = int(bytes)


def read_bandwidthOUT():
    """
    Reads today's outgoing bandwidth stats from disk  
    """
    global BandOutDict
    dhnio.Dprint(6, 'bandwidth.read_bandwidthOUT ')
    for idurl, bytes in dhnio._read_dict(filenameOUT(), {}).items():
        BandOutDict[idurl] = int(bytes)


def clear_bandwidthIN():
    """
    Erase all incoming stats from memory 
    """
    global BandInDict
    dhnio.Dprint(6, 'bandwidth.clear_bandwidthIN ')
    BandInDict.clear()


def clear_bandwidthOUT():
    """
    Erase all outgoing stats from memory
    """ 
    global BandOutDict
    dhnio.Dprint(6, 'bandwidth.clear_bandwidthOUT ')
    BandOutDict.clear()


def clear():
    """
    Erase all bandwidth stats from memory
    """ 
    clear_bandwidthIN()
    clear_bandwidthOUT()


def getBandwidthIN():
    """
    Get current incoming bandwidth stats from memory 
    """
    global BandInDict
    return BandInDict


def getBandwidthOUT():
    """
    Get current outgoing bandwidth stats from memory 
    """
    global BandOutDict
    return BandOutDict


def isExistIN():
    """
    Check existence of today's incoming bandwidth file on disk 
    """
    return os.path.isfile(filenameIN())


def isExistOUT():
    """
    Check existence of today's outgoing bandwidth file on disk 
    """
    return os.path.isfile(filenameOUT())


def files2send():
    """
    Return a list of file names to be read and send to Central server.
    Sent files are market with ".sent" extension and skipped here.  
    """
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
        # if filepath == filenameIN():
        #     continue
        listIN.append(filepath)
    for filename in os.listdir(settings.BandwidthOutDir()):
        if filename.endswith('.sent'):
            continue
        if len(filename) != 6:
            continue
        if filename == misc.gmtime2str('%d%m%y'): #time.strftime('%d%m%y'):
            continue
        filepath = os.path.join(settings.BandwidthOutDir(), filename)
        # if filepath == filenameOUT():
        #     continue
        listOUT.append(filepath)
    dhnio.Dprint(6, 'bandwidth.files2send listIN=%d listOUT=%d' % (len(listIN), len(listOUT)))
    for i in listIN:
        dhnio.Dprint(6, '  ' + i)
    for i in listOUT:
        dhnio.Dprint(6, '  ' + i)
    return listIN, listOUT


def IN(idurl, size):
    """
    Call this when need to count incoming bandwidth.
    `size` - how many incoming bytes received from user with `idurl`.
    Typically called when incoming packet arrives.
    """
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


def OUT(idurl, size):
    """
    Call this when need to count outgoing bandwidth.
    `size` - how many bytes sent to user with `idurl`.
    Typically called when outgoing packet were sent.
    """
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


def INfile(filename, newpacket, proto, host, status):
    """
    Count incoming file from `proto`://`host`, `newpacket` is already Unserialized.
    """
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
    # IN(packet_from, len(newpacket.Payload))


def OUTfile(filename, workitem, proto, host, status):
    """
    Count outgoing file to `proto`://`host`, `workitem` is from sending queue.
    """
    if status != 'finished':
        return
    try:
        sz = os.path.getsize(filename)
    except:
        dhnio.DprintException()
        return
    OUT(workitem.remoteid, sz)
    # OUT(workitem.remoteid, workitem.payloadsize)




