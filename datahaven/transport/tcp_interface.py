#!/usr/bin/python
#tcp_interface.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

"""
This is a client side part of the TCP plug-in. 
The server side part is placed in the file tcp_process.py. 
"""

import os
import sys

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in t_tcp.py')

from twisted.web import xmlrpc
from twisted.internet import protocol

import lib.dhnio as dhnio
import lib.child_process as child_process

#------------------------------------------------------------------------------ 

_BaseDir = '.'
_Process = None
_Proxy = None

#------------------------------------------------------------------------------ 

def init(gate_xmlrpc_url):
    global _Process
    dhnio.Dprint(4, 'tcp_interface.init')
    if len(dhnio.find_process('dhntcp.')) > 0:
        dhnio.Dprint(4, 'tcp_interface.init [dhntcp] already started')
        return _Process
    _Process = child_process.run('dhntcp', ['--rooturl', gate_xmlrpc_url])
    return _Process


def shutdown():
    global _Process
    global _Proxy
    dhnio.Dprint(4, 'tcp_interface.shutdown')
    if _Process is not None:
        child_process.kill_process(_Process)
        _Process = None
    child_process.kill_child('dhntcp')
    del _Proxy
    _Proxy = None


def create_proxy(xmlrpcurl): 
    global _Proxy
    _Proxy = xmlrpc.Proxy(xmlrpcurl)


def proxy():
    global _Proxy
    return _Proxy
 
        
def send(filename, host):
    return proxy().callRemote('send', filename, host)
        
        
def receive(tcpport):
    return proxy().callRemote('receive', tcpport)
    
#------------------------------------------------------------------------------ 

        
        
        
        
        
        
