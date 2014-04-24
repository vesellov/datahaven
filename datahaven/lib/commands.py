#!/usr/bin/python
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
"""
This module describes all commands in the DataHaven.NET p2p communication protocol.
The command is stored as a string in the dhnpacket.Command field. 
If all commands are repeatable, then sequence numbers are not so critical,
though we would want date so time for replay trouble was limited.
If backups are write, read, delete (and never write again), then replay
is not an issue here and we use PacketID that identifies data.
So we want things like "replace supplier Vincecate"  not "replace supplier 5" 
where seeing command an extra time would not hurt.

These are the valid values for the command field of a dhnpacket:
    - Data/Ack/                 (if customer sends you data you store it) (could be parity packet too)
    - Retrieve/Data|Fail        (data packets returned exactly as is with our signature)
    - ListFiles/Files           (ask supplier to list backup IDs he knows about for us)
    
To DHN:
    ListContacts/Contacts
        
From DHN:
    NearnessCheck/Nearness
"""

#------------------------------------------------------------------------------ 

P2PCommandAcks={}
CentralCommandAcks={}

#------------------------------------------------------------------------------ 

def init():
    """
    Initialize a list of valid p2p and central commands.
    """
    initP2PCommands()
    initCentralCommands()

def initP2PCommands():
    """
    These are command strings sent P2P in "command" field of dhnpackets only.
    """
    global P2PCommandAcks
    P2PCommandAcks[Ack()]=NoAck()                         # No Ack for Ack
    P2PCommandAcks[Fail()]=NoAck()                        # No Ack for Fail

    P2PCommandAcks[Data()]=Ack()                          # Ack with Ack unless it is our data coming back (would be only after Retrieve)
    P2PCommandAcks[Retrieve()]=Data()                     # Ack with Data

    P2PCommandAcks[ListFiles()]=Files()                   # Ack ListFiles with Files
    P2PCommandAcks[Files()]=NoAck()

    P2PCommandAcks[ListContacts()]=Contacts()             # Ack with Contacts
    P2PCommandAcks[Contacts()]=NoAck()

    P2PCommandAcks[NearnessCheck()]=Nearness()            # Ack with Nearness
    P2PCommandAcks[Nearness()]=NoAck()

    P2PCommandAcks[RequestIdentity()]=Identity()          # Ack with Identity (always an interested party waiting)
    P2PCommandAcks[Identity()]=Ack()                      # If identity comes in and no interested party then transport sends an Ack

    P2PCommandAcks[DeleteFile()]=Ack()                    # Ack with Ack (maybe should be Files)
    P2PCommandAcks[DeleteBackup()]=Ack()                  # Ack with Ack (maybe should be Files)
    P2PCommandAcks[Message()]=Ack()                       # Ack with Ack
    P2PCommandAcks[Receipt()]=Ack()                       # Ack with Ack
    
    P2PCommandAcks[Correspondent()]=Correspondent()

def initCentralCommands():
    """
    Those commands are for talking to Central server.
    """
    global CentralCommandAcks
    CentralCommandAcks[Ack()] = NoAck()
    CentralCommandAcks[Register()] = Ack()
    CentralCommandAcks[Identity()] = Ack()
    CentralCommandAcks[Suppliers()] = Ack()
    CentralCommandAcks[Customers()] = Ack()
    CentralCommandAcks[FireContact()] = Ack()
    CentralCommandAcks[Settings()] = Ack()
    CentralCommandAcks[Transfer()] = Ack()
    CentralCommandAcks[BandwidthReport()] = Ack()
    CentralCommandAcks[RequestSuppliers()] = Ack()
    CentralCommandAcks[RequestCustomers()] = Ack()
    CentralCommandAcks[RequestSpace()] = Ack()
    CentralCommandAcks[RequestSettings()] = Ack()
    CentralCommandAcks[RequestReceipt()] = Ack()

#------------------------------------------------------------------------------ 

def IsCommand(s):                 
    """
    Check to see if `s` is a valid command.
    """
    return IsP2PCommand(s) or IsCentralCommand(s)

def IsP2PCommand(s):                      
    """
    Check to see if `s` is a valid p2p command.
    """
    global P2PCommandAcks
    if len(P2PCommandAcks) == 0:
        initP2PCommands()
    result = s in P2PCommandAcks
    return result

def IsCentralCommand(s):
    """
    Check to see if `s` is a valid Central server command.
    """
    global CentralCommandAcks
    if len(CentralCommandAcks) == 0:
        initCentralCommands()
    result = s in CentralCommandAcks
    return result

#------------------------------------------------------------------------------ 

def AckForCommand(s):
    """
    Return the command we expect back after this type of command.
    """
    global P2PCommandAcks
    global CentralCommandAcks
    if s in P2PCommandAcks:
        return P2PCommandAcks[s]
    if s in CentralCommandAcks:
        return CentralCommandAcks[s]
    raise Exception("Commands.AckForCommand asked for Ack for non command " + s)

def NoAck():
    """
    This is not sent between machines, just used when seeing what type of Ack to expect.
    """
    return "NoAck"

def Data():
    """
    Data packet, may be Data, Parity, Backup database, may be more
    """
    return "Data"

def Ack():
    """
    Response packet for some request.
    """
    return "Ack"

def Retrieve():
    """
    Used to request some data from supplier for example.
    """
    return "Retrieve"

def Fail():
    """
    Used to report an error in response, for example when requested file is not found on remote machine.
    """
    return "Fail"

# for case when local scrubber has detected some bitrot and asks customer to resend
# def Resend():
#    return("Resend")

def ListFiles():
    """
    Response from remote peer with a list of my files stored on his machine.
    """
    return "ListFiles"

def Files():
    """
    Request a list of my files from remote peer.
    """
    return "Files"

def ListContacts():
    """
    Response with a list of my contacts from Central server, may be suppliers, customers or correspondents 
    """
    return "ListContacts"

def Contacts():
    """
    Request a list of my contacts from Central server
    """
    return "Contacts"

def NearnessCheck():
    """
    Used to detect how far is peers
    """ 
    return "NearnessCheck"

def Nearness():
    """
    Used to detect how far is peers
    """ 
    return "Nearness"

def RequestIdentity():
    """
    Not used right now, probably can be used to request latest version of peer's identity.
    """
    return "RequestIdentity"

def Identity():
    """
    Packet containing peer identity file.
    """
    return "Identity"

def DeleteFile():
    """
    Request to delete a single file or list of my files from remote machine.
    """
    return "DeleteFile"

def DeleteBackup():
    """
    Request to delete whole backup or list of backups from remote machine.
    """
    return "DeleteBackup"

def Transfer():
    """
    Transfer funds to remote peer.
    """
    return "Transfer"

def Receipt():
    """
    Some billing report. 
    """
    return "Receipt"

def Message():
    """
    A message from one peer to another.
    """
    return "Message"

def Correspondent():
    """
    Remote user should send you this to be included in your correspondents list.
    """
    return "Correspondent"

#------------------------------------------------------------------------------ 

def Register():
    """
    Not used right now, probably to register a new identity on Central server.
    """
    return "Register"

def RequestSuppliers():
    """
    Request a list of my suppliers from Central server.
    """
    return "RequestSuppliers"

def Suppliers():
    """
    Not used right now.
    """
    return "Suppliers"

def RequestCustomers():
    """
    Request a list of my customers from Central server.
    """
    return "RequestCustomers"

def Customers():
    """
    Not used right now.
    """
    return "Customers"

def FireContact():
    """
    Request to replace on of my suppliers from Central server, it will respond with ListContacts.
    """
    return "FireContact"

def Settings():
    """
    Used to save my local settings on Central server.
    """
    return 'Settings'

def BandwidthReport():
    """
    Used to daily reports of users bandwidh stats to the Central server.
    """
    return 'BandwidthReport'

def RequestSpace():
    """
    Not used right now.
    """
    return 'RequestSpace'

def RequestSettings():
    """
    Request my settings from Central server.
    """
    return 'RequestSettings'

def RequestReceipt():
    """
    Request a billing reports from Central server.
    """
    return "RequestReceipt"



