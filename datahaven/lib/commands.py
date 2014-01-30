#!/usr/bin/python
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
# If all commands are repeatable, then sequence numbers are not so critical,
#   though we would want date so time for replay trouble was limited.
#  If backups are write, read, delete (and never write again), then replay
#   is not an issue here and we use PacketID that identifies data.
#  So we want things like "replace supplier Vincecate"  not "replace supplier 5" where seeing command an extra time would not hurt.


#  These are the valid values for the command field of a dhnpacket
#        Data/Ack/                 (if customer sends you data you store it) (could be parity packet too)
#        Retrieve/Data|Fail        (data packets returned exactly as is with our signature)
#        ListFiles/Files   (ask supplier to list backup IDs he knows about for us)
#    To DHN
#        ListContacts/Contacts
#    From DHN
#        NearnessCheck/Nearness

def IsCommand(s):                 # check to see if s is a valid command
    return IsP2PCommand(s) or IsCentralCommand(s)

P2PCommandAcks={}
CentralCommandAcks={}

def init():
    initP2PCommands()
    initCentralCommands()

# These are command strings sent P2P in "command" field of dhnpackets only
def initP2PCommands():
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

def IsP2PCommand(s):                      # check to see if s is a valid command
    global P2PCommandAcks
    result = s in P2PCommandAcks
    # print "Commands.IsP2PCommand given %s  is returning %s" % (s, result)
    return result

def AckForCommand(s):                     # Return the command we expect back after this type of command
    global P2PCommandAcks
    global CentralCommandAcks
    if s in P2PCommandAcks:
        return P2PCommandAcks[s]
    if s in CentralCommandAcks:
        return CentralCommandAcks[s]
    raise Exception("Commands.AckForCommand asked for Ack for non command " + s)

# This is not sent between machines, just used when seeing what type of Ack to expect
def NoAck():
    return "NoAck"

def Data():
    return "Data"

def Ack():
    return "Ack"

def Retrieve():
    return "Retrieve"

def Fail():
    return "Fail"

# for case when local scrubber has detected some bitrot and asks customer to resend
# def Resend():
#    return("Resend")

def ListFiles():
    return "ListFiles"

def Files():
    return "Files"

def ListContacts():
    return "ListContacts"

def Contacts():
    return "Contacts"

def NearnessCheck():
    return "NearnessCheck"

def Nearness():
    return "Nearness"

def RequestIdentity():
    return "RequestIdentity"

def Identity():
    return "Identity"

def DeleteFile():
    return "DeleteFile"

def DeleteBackup():
    return "DeleteBackup"

def Transfer():
    return "Transfer"

def Receipt():
    return "Receipt"

def Message():
    return "Message"

def Correspondent():
    return "Correspondent"

#  Next commands are for talking to Central
def initCentralCommands():
    return

# check to see if is a valid central command
def IsCentralCommand(s):
    result=False
    if (s==Ack()):result=True
    if (s==Register()):result=True
    if (s==Identity()):result=True
    if (s==Suppliers()):result=True
    if (s==Customers()):result=True
    if (s==FireContact()):result=True
    if (s==Settings()):result=True
    if (s==Transfer()):result=True
    if (s==BandwidthReport()):result=True
    if (s==RequestSuppliers()):result=True
    if (s==RequestCustomers()):result=True
    if (s==RequestSpace()):result=True
    if (s==RequestSettings()):result=True
    if (s==RequestReceipt()):result=True
    return(result)

def Register():
    return("Register")

def RequestSuppliers():
    return("RequestSuppliers")

def Suppliers():
    return("Suppliers")

def RequestCustomers():
    return("RequestCustomers")

def Customers():
    return("Customers")

def FireContact():
    return("FireContact")

def Settings():
    return('Settings')

def BandwidthReport():
    return 'BandwidthReport'

def RequestSpace():
    return 'RequestSpace'

def RequestSettings():
    return 'RequestSettings'

def RequestReceipt():
    return "RequestReceipt"



