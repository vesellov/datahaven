#!/usr/bin/python
#transport_skype.py

_Skype4PyInstalled = False
try:
    import Skype4Py
    _Skype4PyInstalled = True
except:
    pass


import os
import sys
import time
import base64
import tempfile
import random
import types

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in transport_skype.py')

from twisted.internet import threads
from twisted.internet.defer import Deferred


import transport_control
import dhnio
import misc
import packetid


_SkypeObject = None
_ApplicationName = 'dhn-transport'
_SkypeStatus = None
_LocalSkypeName = ''

_AttachNotifier = None
_ReceiveNotifier = None
_SentNotifier = None

_PacketSize = 1024*8
_OutboxQueue = []
_Buffer = ''
_CurrentPacket = None

_InboxFilesNames = {}
_InboxFilesSize = {}


#-------------------------------------------------------------------------------

def SetReceiveNotifier(notify_func = None):
    global _ReceiveNotifier
    _ReceiveNotifier = notify_func

def SetSentNotifier(notify_func = None):
    global _SentNotifier
    _SentNotifier = notify_func

def SetAttachNotifier(notify_func = None):
    global _AttachNotifier
    _AttachNotifier = notify_func

#-------------------------------------------------------------------------------


def _Try2Attach():
    global _SkypeObject
    if _SkypeObject is None:
        return
    try:
        _SkypeObject.Attach()
    except:
        dhnio.Dprint(6, 'transport_skype._Try2Attach Attachment Failed')
        return

def _OnAttachmentStatus(status):
    global _SkypeObject
    global _ApplicationName
    global _Skype4PyInstalled
    global _SkypeStatus
    global _LocalSkypeName
    global _AttachNotifier

    if not _Skype4PyInstalled:
        return
    _SkypeStatus = status
    dhnio.Dprint(14, 'transport_skype._OnAttachmentStatus ' + str(status))
    if _SkypeObject is None:
        return
    if status == Skype4Py.apiAttachAvailable:
        reactor.callInThread(_Try2Attach)
        dhnio.Dprint(14, 'transport_skype._OnAttachmentStatus Attach')
    elif status == Skype4Py.apiAttachSuccess:
        try:
            _SkypeObject.Application(_ApplicationName).Create()
            _LocalSkypeName = _SkypeObject.CurrentUserHandle.split(':')[0]
        except:
            dhnio.Dprint(6, 'transport_skype._OnAttachmentStatus ERROR Application create Failed')
            dhnio.DprintException()
            return
        dhnio.Dprint(14, 'transport_skype._OnAttachmentStatus dhn-transport application created')
        if _AttachNotifier is not None:
            _AttachNotifier(status, _LocalSkypeName)
    elif status == Skype4Py.apiAttachRefused:
        dhnio.Dprint(6, 'transport_skype._OnAttachmentStatus Attach Refused')
    elif status == Skype4Py.apiAttachNotAvailable:
        dhnio.Dprint(6, 'transport_skype._OnAttachmentStatus Skype not available')


def connect(skype_name, src):
    global _Skype4PyInstalled
    global _Buffer
    global _SkypeObject
    global _ApplicationName
    dhnio.Dprint(14, 'transport_skype.connect to ' + str(skype_name))
    if not _Skype4PyInstalled:
        dhnio.Dprint(4, 'transport_skype.connect Skype4Py not installed')
        return
    if _SkypeObject is None:
        dhnio.Dprint(4, 'transport_skype.connect skype not ready')
        return
    _Buffer = base64.b64encode(src) + ' '
    try:
        _SkypeObject.Application(_ApplicationName).Connect(skype_name, False)
    except:
        dhnio.Dprint(4, 'transport_skype.connect to %s FAILED' % str(skype_name))
        dhnio.DprintException()
        buffer_fail()
        return

def _OnApplicationConnecting(app, users):
    global _Buffer
    global _SkypeObject
    global _ApplicationName
    try:
        streams = _SkypeObject.Application(_ApplicationName).Streams
    except:
        dhnio.Dprint(1, 'transport_skype._OnApplicationConnecting NETERROR')
        dhnio.DprintException()
        buffer_fail()
        return
    if streams.Count == 0:
        return
    dhnio.Dprint(14, 'transport_skype._OnApplicationConnecting ')
    at_least_one_sent = False
    for stream in streams:
        try:
            skype_name = stream.Handle.split(':')[0]
        except:
            dhnio.Dprint(1, 'transport_skype._OnApplicationConnecting NETERROR wrong stream handle')
            continue
        if _stream_write(stream, _Buffer, skype_name) > 0:
            at_least_one_sent = True
    if at_least_one_sent:
        buffer_sent()
    else:
        buffer_fail()

def _stream_write(stream, data, skype_name):
    global _SentNotifier
    total_length = 0
    for part in data.split(' '):
        try:
            stream.Write(str(len(part))+':'+str(part))
        except:
            dhnio.Dprint(4, 'transport_skype._stream_write  FAIL sending to ' + str(skype_name))
            transport_control.log('skype', 'sending to %s failed' % str(skype_name))
            continue
        total_length += len(part)
    transport_control.log('skype', 'sending to %s done' % str(skype_name))
    dhnio.Dprint(12, 'transport_skype._stream_write %s bytes sent to %s' % (str(total_length), str(skype_name)))
    if _SentNotifier is not None:
        _SentNotifier(skype_name, total_length)
    return total_length

def _OnApplicationStreams(app, streams):
    dhnio.Dprint(14, 'transport_skype._OnApplicationStreams ')
    if streams.Count > 1:
        dhnio.Dprint(4, 'transport_skype._OnApplicationStreams WARNING streams.Count='+str(streams.Count))
##        streams[1].Disconnect()

def _OnApplicationReceiving(app, streams):
    dhnio.Dprint(14, 'transport_skype._OnApplicationReceiving')
    transport_control.log('skype', 'incomming connection')
    if streams.Count == 0:
        return
    if streams[0].DataLength == 0:
        return
    for stream in streams:
        _stream_read(stream)

def _stream_read(stream):
    global _ReceiveNotifier
    dhnio.Dprint(14, 'transport_skype._stream_read')
    try:
        skype_name = stream.Handle.split(':')[0]
    except:
        dhnio.Dprint(1, 'transport_skype._stream_read NETERROR wrong stream handle')
        return
    total_length = 0
    try:
        parts = stream.Read()
    except:
        transport_control.log('skype', 'receiving from %s failed' % str(skype_name))
        dhnio.Dprint(4, 'transport_skype._stream_read  FAILED receiving from ' + str(skype_name))
        return
    for part in parts.split(' '):
        if len(part.strip()) == 0:
            continue
        try:
            (lengthStr, data) = part.split(':')
        except:
            dhnio.Dprint(1, 'transport_skype._stream_read NETERROR wrong data ' + str(part))
            continue
        try:
            lengthI = int(lengthStr)
        except:
            dhnio.Dprint(1, 'transport_skype._stream_read NETERROR wrong data ' + str(lengthStr))
            continue
        if lengthI != len(data):
            dhnio.Dprint(1, 'transport_skype._stream_read NETERROR wrong data size')
            continue
        if lengthI == 0:
            continue
        try:
            data_decoded = base64.b64decode(data)
        except:
            dhnio.Dprint(1, 'transport_skype._stream_read NETERROR decoding data')
            continue

        total_length += lengthI

        packet = unserialize(data_decoded)
        if packet is None:
            dhnio.Dprint(1, 'transport_skype._stream_read ERROR unserialize incomming data')
            continue

        inbox(packet)

    if _ReceiveNotifier is not None:
        _ReceiveNotifier(skype_name, total_length)


#-------------------------------------------------------------------------------

def get_user_status(skype_name):
    global _SkypeObject
    if _SkypeObject is None:
        return
    user = _SkypeObject.User(Username = skype_name)
    return user.OnlineStatus

#-------------------------------------------------------------------------------


class SkypeListener(Deferred):
    def stopListening(self):
        global _SkypeObject
        if _SkypeObject is None:
            return
        _SkypeObject.OnApplicationReceiving = None

def _wait4receive(d, count):
    global _SkypeStatus
    dhnio.Dprint(12, 'transport_skype._wait4receive ' + str(count))
    if _SkypeStatus == Skype4Py.apiAttachSuccess:
        d.callback('')
        return
    if count > 60:
        d.errback(Exception(''))
        return
    reactor.callLater(5, _wait4receive, d, count+1)

def inbox(packet):
    global _InboxFilesNames
    global _InboxFilesSize
    dhnio.Dprint(12, 'transport_skype.inbox ' + str(packet))

    fd, filename = tempfile.mkstemp(".dhn-skype-in", "%s-%s-"% (str(packet.packet_id), str(packet.file_id)))
    os.write(fd, packet.data)
    try:
        fd.flush()
        os.close(fd)
    except:
        pass

    if not _InboxFilesNames.has_key(packet.file_id):
        _InboxFilesNames[packet.file_id] = list()
        _InboxFilesSize[packet.file_id] = 0
    _InboxFilesNames[packet.file_id].append(filename)
    _InboxFilesSize[packet.file_id] += len(packet.data)
    if _InboxFilesSize[packet.file_id] >=  packet.total_size:
        assemble(packet.file_id, packet.skype_name_from)

def assemble(file_id, skype_name_from):
    global _InboxFilesNames
    global _InboxFilesSize
    dhnio.Dprint(14, 'transport_skype.assemble file_id:%s from %s' % (str(file_id), skype_name_from))

    files_list = _InboxFilesNames[file_id]
    files_list.sort()

    fd, filename = tempfile.mkstemp(".dhn-skype-in")
    for part_filename in files_list:
        src = dhnio.ReadBinaryFile(part_filename)
        os.write(fd, src)
        if os.access(part_filename, os.W_OK):
            try:
                os.remove(part_filename)
            except:
                dhnio.Dprint(1, 'transport_skype.assemble ERROR removing ' + part_filename)
    try:
        fd.flush()
        os.close(fd)
    except:
        pass
    _InboxFilesNames.pop(file_id, None)
    _InboxFilesSize.pop(file_id, None)
    transport_control.receiveStatusReport(filename, "finished",
        'skype', skype_name_from)
    transport_control.log('skype', 'finish receiving from ' + str(skype_name_from))

def receive():
    global _Skype4PyInstalled
    global _SkypeObject
    global _SkypeStatus
    dhnio.Dprint(14, 'transport_skype.receive')
    if not _Skype4PyInstalled:
        dhnio.Dprint(4, 'transport_skype.receive Skype4Py not installed')
        return None, None
    if _SkypeObject is None:
        dhnio.Dprint(4, 'transport_skype.receive skype not ready yet')
        return None, None
    _SkypeObject.OnApplicationReceiving = _OnApplicationReceiving
    d = Deferred()
    if _SkypeStatus == Skype4Py.apiAttachSuccess:
        d.callback('')
    else:
        reactor.callLater(5, _wait4receive, d, 0)
    return d, SkypeListener()

#-------------------------------------------------------------------------------

def sendshort(skype_name, filename):
    try:
        fin = open(filename, 'rb')
        src = fin.read()
        fin.close()
    except:
        dhnio.Dprint(1, 'transport_skype.sendshort ERROR reading ' + str(filename))
        return
    connect(skype_name, src)

#-------------------------------------------------------------------------------

class Packet:
    def __init__(self,
            skype_name_to,
            skype_name_from,
            file_id,
            packet_id,
            total_size,
            data):
        self.skype_name_to = skype_name_to
        self.skype_name_from = skype_name_from
        self.file_id = file_id
        self.packet_id = packet_id
        self.total_size = total_size
        self.data = data
        dhnio.Dprint(14, str(self))

    def serialize(self):
        return misc.ObjectToString(self)

    def __str__(self):
        return 'Packet to %s from %s file_id:%s packet_id:%s with %s from %s bytes' % (
        self.skype_name_to,
        self.skype_name_from,
        self.file_id,
        self.packet_id,
        str(len(self.data)),
        str(self.total_size))

def unserialize(data):
    newobject = misc.StringToObject(data)
    if type(newobject) != types.InstanceType:
        dhnio.Dprint(1, "transport_skype.unserialize ERROR not an instance")
        return None
    if newobject.__class__ != Packet:
        dhnio.Dprint(1, "transport_skype.unserialize ERROR not a Packet:" + str(newobject.__class__))
        return None
    return newobject

def send(skype_name, filename):
    global _PacketSize
    global _LocalSkypeName
    src = dhnio.ReadBinaryFile(filename)

    total_size = len(src)
    file_id = packetid.UniqueID()
    packet_id = 0
    i = 0
    while True:
        buf = src[i:i + _PacketSize]
        packet = Packet(
            skype_name,
            _LocalSkypeName,
            file_id,
            packet_id,
            total_size,
            buf)
        outbox(packet)
        packet_id += 1
        i += _PacketSize
        if i >= len(src):
            break

def outbox(packet):
    global _OutboxQueue
    _OutboxQueue.append(packet)

def buffer_sent():
    global _Buffer
    global _CurrentPacket
    dhnio.Dprint(14, 'transport_skype.buffer_sent')
    packet = unserialize(base64.b64decode(_Buffer.strip()))
    if packet is None:
        return
    if _CurrentPacket is None:
        return
    if _CurrentPacket.packet_id == packet.packet_id and _CurrentPacket.file_id == packet.file_id:
        _OutboxQueue.pop(0)
        _CurrentPacket = None

def buffer_fail():
    global _Buffer
    global _CurrentPacket
    dhnio.Dprint(14, 'transport_skype.buffer_fail')
    packet = unserialize(base64.b64decode(_Buffer.strip()))
    if packet is None:
        return
    if _CurrentPacket is None:
        return
    if _CurrentPacket.packet_id == packet.packet_id and _CurrentPacket.file_id == packet.file_id:
        _CurrentPacket = None

def process_sending_queue():
    global _OutboxQueue
    global _CurrentPacket
    global _SkypeObject

    if not _Skype4PyInstalled:
        return

    reactor.callLater(0.01, process_sending_queue)

    if _SkypeObject is None:
        return
    if _SkypeStatus != Skype4Py.apiAttachSuccess:
        return
    if len(_OutboxQueue) == 0:
        return
    if _CurrentPacket is not None:
        return

    _CurrentPacket = _OutboxQueue[0]
    connect(_CurrentPacket.skype_name_to, _CurrentPacket.serialize())


#-------------------------------------------------------------------------------


def shutdown():
    global _Skype4PyInstalled
    global _SkypeObject
    global _ApplicationName
    if not _Skype4PyInstalled:
        dhnio.Dprint(4, 'transport_skype.shutdown Skype4Py not installed')
        return
    dhnio.Dprint(4, 'transport_skype.shutdown')
    if _SkypeObject is not None:
        try:
            _SkypeObject.Application(_ApplicationName).Delete()
        except:
            dhnio.Dprint(6, 'transport_skype.shutdown Application removing failed')
        del _SkypeObject
        _SkypeObject = None

def init():
    global _SkypeObject
    if not _Skype4PyInstalled:
        dhnio.Dprint(4, 'transport_skype.init Skype4Py not installed')
        return
    dhnio.Dprint(4, 'transport_skype.init')

    if _SkypeObject is not None:
        return
    _SkypeObject = Skype4Py.Skype()
    _SkypeObject.Timeout = 5.0
    _SkypeObject.OnAttachmentStatus = _OnAttachmentStatus
    _SkypeObject.OnApplicationStreams = _OnApplicationStreams
    _SkypeObject.OnApplicationConnecting = _OnApplicationConnecting

    reactor.callInThread(_Try2Attach)

    reactor.addSystemEventTrigger('before', 'shutdown', shutdown)

    reactor.callLater(0, process_sending_queue)


#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------


def cmd_send(skype_name, filename):
    def _attach_func(status, local_skype_name):
        send(skype_name, filename)
    SetAttachNotifier(_attach_func)

def cmd_sendshort(skype_name, filename):
    sendshort(skype_name, filename)

def cmd_receive():
    receive()

_Counter = 0
def cmd_loopsend(skype_name, filename, timeout):
    global _Counter
    _Counter += 1
    send(skype_name, filename)
    reactor.callLater(timeout, cmd_loopsend, skype_name, filename, timeout)

#-------------------------------------------------------------------------------

_RandomData = ''
_Bytes_sent = 0
_Start_tm = time.time()
def _sent_func(name, bytes):
    global _Start_tm
    global _Bytes_sent
    _Bytes_sent += bytes
    dt = time.time() - _Start_tm
    if dt > 0:
        speed = float(bytes/1024.0)/float(dt)
        print speed, 'Kb/sec'
##    _Start_tm = time.time()
##    reactor.callLater(0, _datasend, name, _RandomData)
def _loopsendspeed(skype_name):
    global _Bytes_sent
    global _Start_tm
    global _RandomData
    _Bytes_sent = 0
    _Start_tm = time.time()
    connect(skype_name, _RandomData)
    reactor.callLater(0.0, _loopsendspeed, skype_name)
def cmd_sendspeed(skype_name, kilobytes):
    global _RandomData
    SetSentNotifier(_sent_func)
    _RandomData = ''
    data1024 = ''
    print 'preparing random data...'
    for i in range(1024):
        data1024 += chr(random.randint(0, 255))
    for j in range(int(kilobytes)):
        _RandomData += data1024
    print 'start sending...'
    cmd_loopsendspeed(skype_name)

#-------------------------------------------------------------------------------

def cmd_receivespeed():
    pass

def cmd_senddata(skype_name, kilobytes):
    print 'preparing random data...'
    data1024 = ''
    data = ''
    for i in range(1024):
        data1024 += chr(random.randint(0, 255))
    for j in range(int(kilobytes)):
        data += data1024
    print 'sending %s bytes ...' % str(len(data))
    connect(skype_name, data)

def cmd_status(skype_name):
    print get_user_status(skype_name)

def cmd_line_execute():
    dhnio.SetDebug(18)
    if sys.argv.count('receive'):
        init()
        cmd_receive()
    elif sys.argv.count('send'):
        init()
        cmd_send(sys.argv[2], sys.argv[3])
    elif sys.argv.count('sendshort'):
        init()
        cmd_sendshort(sys.argv[2], sys.argv[3])
    elif sys.argv.count('loopsend'):
        init()
        cmd_loopsend(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    elif sys.argv.count('sendspeed'):
        init()
        cmd_sendspeed(sys.argv[2], sys.argv[3])
    elif sys.argv.count('senddata'):
        init()
        cmd_senddata(sys.argv[2], sys.argv[3])
    elif sys.argv.count('status'):
        init()
        cmd_status(sys.argv[2])
    else:
        print 'usage:'
        print 'transport_skype.py receive'
        print 'transport_skype.py receivespeed'
        print 'transport_skype.py send [skype_name] [filename]'
        print 'transport_skype.py sendshort [skype_name] [filename]'
        print 'transport_skype.py loopsend [skype_name] [filename] [timeout]'
        print 'transport_skype.py senddata [skype_name] [kilobytes]'
        print 'transport_skype.py sendspeed [skype_name] [kilobytes]'
        print 'transport_skype.py status [skype_name]'


        sys.exit()

if __name__ == '__main__':
    cmd_line_execute()
    reactor.run()





