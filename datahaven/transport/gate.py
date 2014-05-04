#!/usr/bin/python
#gate.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

"""
This is a replacement for `lib.transport_control` stuff.
Here is place to put `outgoing` files to send to other users in the network.
Also this code receives a `incoming` files from other nodes.

Keeps a list of available `transports` - we use a plug-in system so you can
use external p2p (or centralized) networks to transfer files in different ways.

To identify user need to place his ID inside given external network to his public identity file.
So DataHaven.NET users can use different ways to communicate and transfer data.
DHN code will use that module to talk with nodes in the network.
  
Seems like we faced with such situation - 
DHN software need to work together with other networks software on same machine.
This means we need to communicate between system processes - this is work for plug-ins.
So the idea is to make plug-ins code working inside the main process thread - 
they just need to send/receive a short commands to another process in the OS.
So it must be atomic operations (or deferred) and do not use any resources.

And it seems like some plug-ins must have 2 parts:
    - DataHaven.NET python module with interface to do file transfer
    - external code inside given network to control it from DHN.
Communication between both parts can be done in a different ways, I think XMLRPC can work for most cases.
We need to run XML-RPC on both sides because transport plug-in 
must be able to respond to the main process too. 

External network can be written in C++ or Java and the second part of the transport plig-in need to 
deal with that and be portable.   

Different networks provides various functions, something more than just transfer files.
Some of them uses DHT to store data on nodes - we can use that stuff also. 
"""

import os
import sys
import time

from twisted.web import server
from twisted.web import xmlrpc
from twisted.internet import reactor

try:
    import lib.dhnio as dhnio
except:
    dirpath = os.path.dirname(os.path.abspath(sys.argv[0]))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..')))
    try:
        import lib.dhnio as dhnio
    except:
        sys.exit()

#------------------------------------------------------------------------------ 

XMLRPC_DEFAULT_PORT_NUMBERS = {
   'tcp': 9010,
   'udp': 9011,
   'cspace': 9012, }

REGISTERED_TRANSPORTS = {}

try:
    import tcp_interface
    REGISTERED_TRANSPORTS['tcp'] = tcp_interface
except:
    pass # dhnio.DprintException()

try:
    import t_udp
    REGISTERED_TRANSPORTS['udp'] = t_udp
except:
    pass # dhnio.DprintException()

try:
    import t_cspace
    REGISTERED_TRANSPORTS['cspace'] = t_cspace
except:
    pass # dhnio.DprintException()

#------------------------------------------------------------------------------ 

_TransfersDict = {}
_XMLRPCListener = None
_XMLRPCPort = None
_XMLRPCURL = ''

#------------------------------------------------------------------------------ 

def init():
    """
    Initialize the transports gate.
    """
    global _XMLRPCListener
    global _XMLRPCPort
    global _XMLRPCURL
    dhnio.Dprint(4, 'gate.init')
    _XMLRPCListener = reactor.listenTCP(0, server.Site(TransportGateXMLRPCServer()))
    _XMLRPCPort = _XMLRPCListener.getHost().port
    _XMLRPCURL = "http://localhost:%d" % int(_XMLRPCPort)
    dhnio.Dprint(6, 'gate.init XML-RPC: %s' % _XMLRPCURL)
    
    
def shutdown():
    global _XMLRPCListener
    global _XMLRPCPort
    global _XMLRPCURL
    dhnio.Dprint(4, 'gate.shutdown')


def init_proto(protocol):
    global _XMLRPCURL   
    p = protos(protocol)
    if p is None:
        return None
    return p.init(_XMLRPCURL)


def shutdown_proto(protocol):
    p = protos(protocol)
    if p is None:
        return None
    p.shutdown()
    

def init_all_protos(): 
    global _XMLRPCURL   
    for proto, modul in protos().items():
        dhnio.Dprint(6, 'gate.init_all_protos execute transport [%s]' % proto)
        try:
            modul.init(_XMLRPCURL)
        except:
            dhnio.DprintException()
            continue


def shutdown_all_protos():    
    for proto, modul in protos().items():
        dhnio.Dprint(6, 'gate.shutdown_all_protos want to stop transport [%s]' % proto)        
        try:
            modul.shutdown()
        except:
            dhnio.DprintException()
            continue
            

def protos(proto=None):
    """
    Return a list of available transport plug-ins.
    """
    global REGISTERED_TRANSPORTS
    if proto is None:
        return REGISTERED_TRANSPORTS
    return REGISTERED_TRANSPORTS[proto] 


def transfers():
    """
    Return a list of registered transfers.
    """
    global _TransfersDict
    return _TransfersDict


def send_packet(outpacket, doAck, wide=False):
    """
    Sends `dhnpacket` to the network.
        :param outpacket: an instance of dhnpacket
        :param doAck: set to True if you want to wait for an Ack packet before counting that transfer as finished
        :param wide: set to True if you need to send the packet to all contacts of Remote Identity
    """


def packet_received(filename, proto, host):
    """
    Incoming file will be `Unserialized` here. 
    """
#------------------------------------------------------------------------------ 

class FileTransferInfo():
    """
    Keeps info about given file transfer which is running at the moment.
    """
    def __init__(self, filename, transfer_id, proto, host, send_or_receive, idurl=None, callback=None, size=None, description=None):
        self.filename = filename
        self.transfer_id = transfer_id
        self.proto = proto
        self.host = host
        self.send_or_receive = send_or_receive
        self.idurl = idurl
        self.callback = callback
        self.size = size
        self.description = description
        self.started = time.time()
        
#------------------------------------------------------------------------------ 

def make_transfer_ID():
    """
    Generate a unique transfer ID.
    """
    global _LastTransferID
    if _LastTransferID is None:
        _LastTransferID = int(str(int(time.time() * 100.0))[4:])
    _LastTransferID += 1
    return _LastTransferID

class TransportGateXMLRPCServer(xmlrpc.XMLRPC):
    """
    XML-RPC server to receive calls from transport plug-ins.
    """

    def xmlrpc_transport_started(self, protocol, xmlrpcurl):
        protos(protocol).create_proxy(xmlrpcurl)
        if protocol == 'tcp':
            protos(protocol).receive()
        return True
    
    def xmlrpc_receiving_started(self, protocol, host, options_modified=None):
        """
        """
        return True

    def xmlrpc_receiving_failed(self, protocol, error_code=None):
        """
        """
        return True

    def xmlrpc_register_file_sending(self, protocol, host, remote_user_id, filename, description=None):
        """
        Called from transport plug-in when sending a single file were started to some remote peer.
        Must return a unique transfer ID so plug-in will know that ID.
        After finishing that given transfer - that ID is passed to `unregister_file_sending()`.
        """
        return True
    
    def xmlrpc_register_file_receiving(self, protocol, host, remote_user_id, filename, description=None):
        """
        Called from transport plug-in when receiving a single file were started from some remote peer.
        Must return a unique transfer ID, create a `FileTransferInfo` object and put it into "transfers" list.
        Plug-in's code must create a temporary file and write incoming data into that file.
        """
        return True

    def xmlrpc_unregister_file_sending(self, transfer_id, status, error_message=None):
        """
        Called from transport plug-in after finish sending a single file.
        """
        return True
    
    def xmlrpc_unregister_file_receiving(self, transfer_id, status, error_message=None):
        """
        Called from transport plug-in after finish receiving a single file.
        """
        return True
    
    def xmlrpc_start_connecting(self, host):
        """
        """
        return True
    
    def xmlrpc_session_opened(self, host, remote_user_id):
        """
        """
        
    def xmlrpc_connection_failed(self, host, error_message=None):
        """
        """
        
    def xmlrpc_session_closed(self, host, remote_user_id, reason=None):
        """
        """
        
    def xmlrpc_message_received(self, host, remote_user_id, data):
        """
        """
        
    

#------------------------------------------------------------------------------ 

def main():
    dhnio.SetDebug(14)
    init()
    init_all_protos()
    reactor.run()
    
if __name__ == "__main__":
    main()
      




