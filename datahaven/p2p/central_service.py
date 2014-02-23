#!/usr/bin/python
#central_service.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#
# This is for services with the central DHN.  Main services are:
#
# 1) register with central service
# 2) list suppliers or customers
# 3) fire a supplier, hire another supplier
# 4) account information and transfers  - done in account.py
# 5) nearnesscheck - meat of function done by nearnesscheck.py
#

import os
import sys
import time
import string

try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in central_service.py')

from twisted.internet.defer import Deferred, succeed
from twisted.internet.task import LoopingCall

import lib.misc as misc
import lib.dhnio as dhnio
import lib.settings as settings
import lib.dhnpacket as dhnpacket
import lib.nameurl as nameurl
import lib.packetid as packetid
import lib.commands as commands
import lib.contacts as contacts
import lib.eccmap as eccmap
import lib.transport_control as transport_control
import lib.transport_tcp as transport_tcp
import lib.bandwidth as bandwidth
import lib.diskspace as diskspace
import lib.identitycache as identitycache
import lib.automats as automats

import central_connector
import fire_hire
import data_sender

import identitypropagate
import money
import local_tester
import backup_control
import events


_InitDone = False
_Connector = None
_InitControlFunc = None
_CentralStatusDict = {}
_LoopSendBandwidthReportsTask = None
_MarketBids = None
_MarketOffers = None
_LastRequestSuppliers = 0
_LastRequestCustomers = 0

#------------------------------------------------------------------------------ 

OnListSuppliersFunc = None
OnListCustomersFunc = None
OnMarketListFunc = None

#-------------------------------------------------------------------------------

def init(hello_interaval=60):
    global _InitDone
    if _InitDone:
        return
    dhnio.Dprint(4, 'central_service.init')
    transport_control.AddInboxCallback(inbox)
    bandwidth.init()
    _InitDone = True

def shutdown():
    _LoopSendBandwidthReportsTask.cancel()
    return succeed(1)

#------------------------------------------------------------------------------

def inbox(newpacket, proto, host):
    commandhandled = False

    if newpacket.OwnerID not in [ settings.CentralID(), settings.MarketServerID(), ]:
        return False

    if newpacket.Command == commands.Ack():
        Ack(newpacket)
        commandhandled = True

    elif newpacket.Command == commands.Receipt():
        Receipt(newpacket)
        commandhandled = True

    elif newpacket.Command == commands.ListContacts():
        ListContacts(newpacket)
        commandhandled = True

    if commandhandled:
        dhnio.Dprint(12, "central_service.inbox [%s] from %s://%s handled" % (newpacket.Command, proto, host))

#    if proto == 'tcp':        
#        try:
#            x, host, port, x = contacts.getContact(settings.CentralID()).getProtoParts('tcp')
#            reactor.callLater(10, transport_tcp.disconnect, host, int(port))
#        except:
#            dhnio.DprintException()

    return commandhandled

def send2central(command, data, doAck=False, PacketID=None):
    MyID = misc.getLocalID()
    RemoteID = settings.CentralID()
    if PacketID is None:
        PacketID = packetid.UniqueID()
    packet = dhnpacket.dhnpacket(
        command,
        MyID,
        MyID,
        PacketID,
        data,
        RemoteID,)
    transport_control.outbox(packet, doAck)
    #del packet
    return PacketID

def send2market(command, data, doAck=False, PacketID=None):
    MyID = misc.getLocalID()
    RemoteID = settings.MarketServerID()
    if PacketID is None:
        PacketID = packetid.UniqueID()
    packet = dhnpacket.dhnpacket(
        command,
        MyID,
        MyID,
        PacketID,
        data,
        RemoteID,)
    transport_control.outbox(packet, doAck)
    return PacketID

#------------------------------------------------------------------------------

#def LoopSendAlive():
#    dhnio.Dprint(4, 'central_service.LoopSendAlive')
#    SendIdentity()
#    reactor.callLater(settings.DefaultAlivePacketTimeOut(), LoopSendAlive)


#-- SENDING --------------------------------------------------------------------

# Register our identity with central
def SendIdentity(doAck=False):
    LocalIdentity = misc.getLocalIdentity()
    dhnio.Dprint(4, "central_service.SendIdentity") #' version=[%s] contacts=[%s]" % (str(LocalIdentity.version), str(LocalIdentity.contacts)))
    data = LocalIdentity.serialize()
    ret = send2central(commands.Identity(), data, doAck, misc.getLocalID())
    return ret

#------------------------------------------------------------------------------ 

# Say what eccmap we are using for recovery info
# How many suppliers we want (probably same as used by eccmap but just in case)
# Say how much disk we are donating now
def SendSettings(doAck=False, packetID=None):
    if packetID is None:
        packetID = packetid.UniqueID()
    sdict = {}
    sdict['s'] = str(settings.getCentralNumSuppliers())
    # donated = DiskSpace(s=settings.getCentralMegabytesDonated())
    # needed = DiskSpace(s=settings.getCentralMegabytesNeeded())
    # sdict['d'] = str(donated.getValueMb())
    # sdict['n'] = str(needed.getValueMb())
    sdict['d'] = str(diskspace.GetMegaBytesFromString(settings.getCentralMegabytesDonated()))
    sdict['n'] = str(diskspace.GetMegaBytesFromString(settings.getCentralMegabytesNeeded()))
    sdict['e'] = settings.getECC()
    sdict['p'] = str(settings.BasePricePerGBDay())
    sdict['e1'] = str(settings.getEmergencyEmail())
    sdict['e2'] = str(settings.getEmergencyPhone())
    sdict['e3'] = str(settings.getEmergencyFax())
    sdict['e4'] = str(settings.getEmergencyOther()).replace('\n', '<br>')
    sdict['mf'] = settings.getEmergencyFirstMethod()
    sdict['ms'] = settings.getEmergencySecondMethod()
    sdict['ie'] = misc.readExternalIP()
    sdict['il'] = misc.readLocalIP()
    sdict['nm'] = str(settings.uconfig('personal.personal-name'))
    sdict['sn'] = str(settings.uconfig('personal.personal-surname'))
    sdict['nn'] = str(settings.uconfig('personal.personal-nickname'))
    sdict['bt'] = str(settings.uconfig('personal.personal-betatester'))
    i = 0
    for idurl in contacts.getCorrespondentIDs():
        sdict['f%03d' % i] = idurl
        i += 1

    data = dhnio._pack_dict(sdict)
    pid = send2central(commands.Settings(), data, doAck, packetID)
    dhnio.Dprint(4, "central_service.SendSettings PacketID=[%s]" % pid)
    return pid

def SettingsResponse(packet):
    words = packet.Payload.split('\n')
    try:
        status = words[0]
        last_receipt = int(words[1])
    except:
        status = ''
        last_receipt = -1
    dhnio.Dprint(4, "central_service.SettingsResponse: status=[%s] last receipt=[%s]" % (status, str(last_receipt)))

def SendRequestSettings(doAck=False):
    dhnio.Dprint(4, 'central_service.SendRequestSettings')
    return send2central(commands.RequestSettings(), '', doAck)

#------------------------------------------------------------------------------ 

def SendReplaceSupplier(numORidurl, doAck=False):
    if isinstance(numORidurl, str):
        idurl = numORidurl
    else:
        idurl = contacts.getSupplierID(numORidurl)
    if not idurl:
        dhnio.Dprint(2, "central_service.SendReplaceSupplier ERROR supplier not found")
        return None
    dhnio.Dprint(4, "central_service.SendReplaceSupplier [%s]" % nameurl.GetName(idurl))
    data = 'S\n'+idurl+'\n'+str(contacts.numberForSupplier(idurl))
    ret = send2central(commands.FireContact(), data, doAck)
    events.notify('central_service', 'sent request to dismiss supplier %s' % nameurl.GetName(idurl))
    return ret

def SendChangeSupplier(numORidurl, newidurl, doAck=False):
    if isinstance(numORidurl, str):
        idurl = numORidurl
    else:
        idurl = contacts.getSupplierID(numORidurl)
    if not idurl or not newidurl:
        return None
    dhnio.Dprint(4, "central_service.SendChangeSupplier [%s]->[%s]" % (nameurl.GetName(idurl), nameurl.GetName(newidurl)))
    data = 'N\n'+idurl+'\n'+newidurl
    ret = send2central(commands.FireContact(), data, doAck)

def SendReplaceCustomer(numORidurl, doAck=False):
    if isinstance(numORidurl, str):
        idurl = numORidurl
    else:
        idurl = contacts.getCustomerID(numORidurl)
    if not idurl:
        dhnio.Dprint(2, "central_service.SendReplaceCustomer ERROR customer not found")
        return None
    dhnio.Dprint(4, "central_service.SendReplaceCustomer [%s]" % nameurl.GetName(idurl))
    data = 'C\n'+idurl+'\n'+str(contacts.numberForCustomer(idurl))
    ret = send2central(commands.FireContact(), data, doAck)
    events.notify('central_service', 'sent request to dismiss customer %s' % nameurl.GetName(idurl))
    return ret

#------------------------------------------------------------------------------ 

def SendRequestSuppliers(data = '', doAck=False):
    global _LastRequestSuppliers
    dt = time.time() - _LastRequestSuppliers
    if dt < 60 * 10:
        dhnio.Dprint(4, "central_service.SendRequestSuppliers skip, last request was %d minutes ago" % (dt/60.0))
        return
    _LastRequestSuppliers = time.time()
    dhnio.Dprint(4, "central_service.SendRequestSuppliers")
    return send2central(commands.RequestSuppliers(), data, doAck)

def SendRequestCustomers(data = '', doAck=False):
    global _LastRequestCustomers
    dt = time.time() - _LastRequestCustomers
    if dt < 60 * 10:
        dhnio.Dprint(4, "central_service.SendRequestCustomers skip, last request was %d minutes ago" % (dt/60.0))
        return
    _LastRequestCustomers = time.time()
    dhnio.Dprint(4, "central_service.SendRequestCustomers")
    return send2central(commands.RequestCustomers(), data, doAck)

#------------------------------------------------------------------------------ 
# Account
# User needs to be able to know his balance. We want to keep it on
#   this machine, not check central each time.  Might have a charge
#   for checking with central and keep date of last checkin so user
#   can not check in too often.
#
# Users who have been with DHN for more than 6 months will be able
#    to transfer some of his prepaid/earned balance to another user.
#    This is like a prepaid cellphone transfering balance to another phone.
#
#    A dhnpacket with a commands.Transfer()
#         The data portion says:
#             Amount: 23.4
#             To: http://foo.bar/baz.xml
#
#    With the dhnpacket signed, we know it is legit.  The ID of the destination is there.
#
#
def SendTransfer(DestinationID, Amount, doAck=False):
    dhnio.Dprint(4, "central_service.SendTransfer  DestinationID=%s  Amount=%s" % (DestinationID, str(Amount)))
    data = DestinationID+'\n'+str(Amount)
    return send2central(commands.Transfer(), data, doAck)


def SendRequestReceipt(missing_receipts, doAck=False):
    dhnio.Dprint(4, 'central_service.SendRequestReceipt ' + str(missing_receipts))
    data = string.join(list(missing_receipts), ' ')
    return send2central(commands.RequestReceipt(), data, doAck)

#------------------------------------------------------------------------------ 
# Market
# First we send a Transfer packet to the Central - the destination ID is Market server 
# The packet contains info about bid or offer.
# Central server checks that user have the needed balance and transfer funds to Market server
#
def SendBid(maxamount, price, days, comment, btcaddress, transactionid, doAck=False):
    dhnio.Dprint(4, 'central_service.SendBid ' + str((maxamount, price, days)))
    data = '%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s' % (misc.getLocalID(), 'bid', misc.float2str(maxamount), misc.float2str(price), str(days), str(btcaddress), str(transactionid), str(comment).replace('\n', ''))
    # send bid to the Market server
    return send2market(commands.Transfer(), data, doAck) 

def SendCancelBid(bidID, doAck=False):
    dhnio.Dprint(4, 'central_service.SendCancelBid ' + str(bidID))
    data = '%s\n%s\n%s' % (misc.getLocalID(), 'cancelbid', bidID)
    # send 'cencel bid' to Market server
    return send2market(commands.Transfer(), data, doAck)

def SendOffer(maxamount, minamount, price, days, comment, btcaddress, doAck=False):
    dhnio.Dprint(4, 'central_service.SendOffer ' + str((maxamount, price, days, btcaddress)))
    data = '%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s' % (settings.MarketServerID(), 'offer', misc.float2str(maxamount), misc.float2str(minamount), misc.float2str(price), str(days),  btcaddress, str(comment).replace('\n', ''))
    # send offer to the Central server to check user balance first and than send Receipt to Market server
    return send2central(commands.Transfer(), data, doAck)

def SendCancelOffer(offerID, doAck=False):
    dhnio.Dprint(4, 'central_service.SendCancelOffer ' + str(offerID))
    data = '%s\n%s\n%s' % (misc.getLocalID(), 'canceloffer', offerID)
    # send 'cancel offer' to Market server
    return send2market(commands.Transfer(), data, doAck)

def MarketListAck(newpacket):
    global _MarketBids
    global _MarketOffers
    global OnMarketListFunc
    dhnio.Dprint(4, "central_service.MarketListAck")
    buf = ''
    bidORoffer = None
    _MarketBids = []
    _MarketOffers = []
    for line in newpacket.Payload.splitlines():
        if line.startswith('begin bid'):
            bidORoffer = 'bid'
            continue
        if line.startswith('begin offer'):
            bidORoffer = 'offer'
            continue
        if line.startswith('end'):
            if bidORoffer == 'bid':
                _MarketBids.append(dhnio._unpack_dict(buf))
            elif bidORoffer == 'offer':
                _MarketOffers.append(dhnio._unpack_dict(buf))
            buf = ''
            continue
        buf += line + '\n'
    # dhnio.Dprint(4, '    bids:   ' + str(_MarketBids))
    # dhnio.Dprint(4, '    offers: ' + str(_MarketOffers))
    if OnMarketListFunc is not None:
        OnMarketListFunc()   

def SendRequestMarketList(doAck=True, packetID=None):
    LocalIdentity = misc.getLocalIdentity()
    dhnio.Dprint(4, "central_service.SendRequestMarketList")
    data = LocalIdentity.serialize()
    if packetID is None:
        packetID = packetid.UniqueID()
    # transport_control.RegisterInterest(MarketListAck, settings.MarketServerID(), packetID)
    return send2market(commands.Identity(), data, doAck, packetID)

#--- RECEIVING -----------------------------------------------------------------


def Ack(packet):
    dhnio.Dprint(4, "central_service.Ack packetID=[%s]" % packet.PacketID)
    if packet.CreatorID == settings.MarketServerID():
        MarketListAck(packet)


def Receipt(request):
    dhnio.Dprint(4, "central_service.Receipt " )
    money.InboxReceipt(request)
    if request.OwnerID != settings.MarketServerID():
        transport_control.SendAck(request)
    missing_receipts = money.SearchMissingReceipts()
    if len(missing_receipts) > 0:
        reactor.callLater(5, SendRequestReceipt, missing_receipts)


#S list of suppliers after RequestSuppliers
#s list of suppliers after RequestSuppliers and have troubles (not found)
#fS list of suppliers after FireContact(supplier)
#fs list of suppliers after FireContact(supplier) and have troubles (not found)
#C list of customers after RequestCustomers
#c list of customers after RequestCustomers and have troubles (not found)
#fC list of customers after FireContact(customers)
#fc list of customers after FireContact(customers) and have troubles (not found)
#bS user was banned with negative balance
legal_codes = ['S','C','s','c','fS','fC','fs','fc','bS']
def ListContacts(request):
    global _CentralStatusDict
    global legal_codes
    global OnListSuppliersFunc
    global OnListCustomersFunc

    data = request.Payload
    dhnio.Dprint(6, 'central_service.ListContacts\n%s' % data)
    words = data.split('\n', 1)
    if len(words) < 2:
        dhnio.Dprint(1, 'central_service.ListContacts ERROR wrong data packet [%s]' % str(request.Payload))
        return

    code = words[0]
    if not code in legal_codes:
        dhnio.Dprint(1, 'central_service.ListContacts ERROR wrong data in the packet [%s] '  % str(request.Payload))
        return

    current_contacts = []
    clist, tail = dhnio._unpack_list(words[1])

    fire_flag = code.startswith('f')
    ban_flag = code.startswith('b')
    contact_type = code.lower()[-1]
    error_flag = code[-1].islower()

    spaceDict = None
    if tail is not None:
        # extract info about who is alive at the moment
        onlineArray = ''
        spaceDict = dhnio._unpack_dict_from_list(tail)
        if spaceDict.has_key('online'):
            onlineArray = spaceDict.pop('online')
        for i in range(len(onlineArray)):
            if i < len(clist):
                if clist[i]:
                    _CentralStatusDict[clist[i]] = onlineArray[i]
        # extract info about contacts local ip
        # if they are in same LAN we need to connect to local IP, not external
        local_ips = {}
        i = 0
        while True:
            idurl_and_local_ip = spaceDict.get('localip%03d' % i, None)
            if idurl_and_local_ip is None:
                break
            try:
                contact_idurl, contact_local_ip = idurl_and_local_ip.split('|')
            except:
                break
            local_ips[contact_idurl] = contact_local_ip
            spaceDict.pop('localip%03d' % i)
            i += 1
            dhnio.Dprint(6, 'central_service.ListContacts got local IP for %s: %s' % (nameurl.GetName(contact_idurl), contact_local_ip))
        identitycache.SetLocalIPs(local_ips)

    #---suppliers
    if contact_type == 's':
        current_contacts = contacts.getSupplierIDs()
        contacts.setSupplierIDs(clist)
        eccmap.init()
        contacts.saveSupplierIDs()
        for supid in contacts.getSupplierIDs():
            if supid.strip() == '':
                error_flag = True
                break
        dhnio.Dprint(4, "central_service.ListContacts (SUPPLIERS) code:%s error:%s length:%d" % (str(code), str(error_flag), len(clist)))
        for oldidurl in current_contacts:
            if oldidurl:
                if oldidurl not in clist:
                    events.info('central_service', 'supplier %s were disconnected' % nameurl.GetName(oldidurl),)
                    misc.writeSupplierData(oldidurl, 'disconnected', time.strftime('%d%m%y %H:%M:%S'))
                    dhnio.Dprint(6, 'central_service.ListContacts supplier %s were disconnected' % nameurl.GetName(oldidurl))
        for newidurl in clist:
            if newidurl:
                if newidurl not in current_contacts:
                    transport_control.ClearAliveTime(newidurl)
                    misc.writeSupplierData(newidurl, 'connected', time.strftime('%d%m%y %H:%M:%S'))
                    events.info('central_service', 'new supplier %s connected' % nameurl.GetName(newidurl), '',)
                    dhnio.Dprint(6, 'central_service.ListContacts new supplier %s connected' % nameurl.GetName(newidurl))
        backup_control.SetSupplierList(clist)
        if not fire_flag and current_contacts != clist:
            dhnio.Dprint(6, 'central_service.ListContacts going to call suppliers')
            identitypropagate.suppliers(wide=True)
        if OnListSuppliersFunc is not None:
            OnListSuppliersFunc()

    #---customers
    elif contact_type == 'c':
        current_contacts = contacts.getCustomerIDs()
        contacts.setCustomerIDs(clist)
        contacts.saveCustomerIDs()
        if spaceDict is not None:
            dhnio._write_dict(settings.CustomersSpaceFile(), spaceDict)
            reactor.callLater(3, local_tester.TestUpdateCustomers)
        # if not fire_flag and current_contacts != clist:
        identitypropagate.customers(wide=True)
        dhnio.Dprint(4, "central_service.ListContacts (CUSTOMERS) code:%s error:%s length:%d" % (str(code), str(error_flag), len(clist)))
        for oldidurl in current_contacts:
            if oldidurl not in clist:
                events.info('central_service', 'customer %s were disconnected' % nameurl.GetName(oldidurl),)
                dhnio.Dprint(6, 'central_service.ListContacts customer %s were disconnected' % nameurl.GetName(oldidurl))
        for newidurl in clist:
            if newidurl not in current_contacts:
                transport_control.ClearAliveTime(newidurl)
                events.info('central_service', 'new customer %s connected' % nameurl.GetName(newidurl))
                dhnio.Dprint(6, 'central_service.ListContacts new customer %s connected' % nameurl.GetName(newidurl))
        if OnListCustomersFunc is not None:
            OnListCustomersFunc()

    #---fire_flag
    if fire_flag:
        if contact_type == 's':
            index = -1
            for index in range(len(clist)):
                if clist[index] != current_contacts[index]:
                    break
            if index >= 0:
                # we want to send our Identity to new supplier
                # and than ask a list of files he have
                # so it should start rebuilding backups immediately
                # right after we got ListFiles from him
                identitypropagate.single(clist[index], wide=True) 

    #---ban_flag
    if ban_flag:
        events.notify('central_service', 'you have negative balance, all your suppliers was removed', '',)
        dhnio.Dprint(2, 'central_service.ListContacts !!! you have negative balance, all your suppliers was removed !!!')

    #---error_flag
    if error_flag:
        #reactor.callLater(settings.DefaultNeedSuppliersPacketTimeOut(), SendRequestSuppliers)
        events.info('central_service', 'could not find available suppliers',
                     'Central server can not find available suppliers for you.\nCheck your central settings.\n',)
        dhnio.Dprint(2, 'central_service.ListContacts !!! could not find available suppliers !!!')

    #---send ack            
    transport_control.SendAck(request)

    #---automats
    if contact_type == 's':
        central_connector.A('list-suppliers', clist)
        fire_hire.A('list-suppliers', (current_contacts, clist))
        data_sender.A('restart')
    elif contact_type == 'c':
        central_connector.A('list-customers', clist)
        
    #---transport_udp
    if transport_control._TransportUDPEnable:
        import lib.transport_udp as transport_udp
        new_contacts = contacts.getContactsAndCorrespondents()
        transport_udp.ListContactsCallback(current_contacts, new_contacts)



#--- NEARNESS ------------------------------------------------------------------

#  NearnessCheck request coming from central
#  When request comes in we start the check with callback
#  going to NearnessResult which will send results to central.
def NearnessCheck(request):
    dhnio.Dprint(4, "central_service.NearnessCheck")

def NearnessResult():
    dhnio.Dprint(4, "central_service.NearnessResult")

#--- BANDWIDTH -----------------------------------------------------------------

def LoopSendBandwidthReport():
    global _LoopSendBandwidthReportsTask
    if _LoopSendBandwidthReportsTask is not None:
        return
    pid = SendBandwidthReport()
    interval = settings.DefaultBandwidthReportTimeOut()
    if pid is not None:
        transport_control.RegisterInterest(ReceiveBandwidthAck, settings.CentralID(), pid)
    else:
        interval /= 10.0
    _LoopSendBandwidthReportsTask = reactor.callLater(interval, LoopSendBandwidthReport)

def SendBandwidthReport():
    listin, listout = bandwidth.files2send()
    if len(listin) == 0 and len(listout) == 0:
        dhnio.Dprint(4, 'central_service.SendBandwidthReport skip')
        return None
    dhnio.Dprint(4, 'central_service.SendBandwidthReport')
    src = ''
    for filepath in listin:
        filename = os.path.basename(filepath)
        if len(filename) != 6:
            dhnio.Dprint(6, 'central_service.SendBandwidthReport WARNING incorrect filename ' + filepath)
            continue
        s = dhnio.ReadBinaryFile(filepath)
        if not s:
            # dhnio.Dprint(6, 'central_service.SendBandwidthReport WARNING %s is empty' % filepath)
            continue
        src += '[in] %s\n' % filename
        src += s.strip()
        src += '\n[end]\n'
    for filepath in listout:
        filename = os.path.basename(filepath)
        if len(filename) != 6:
            dhnio.Dprint(6, 'central_service.SendBandwidthReport WARNING incorrect filename ' + filepath)
            continue
        s = dhnio.ReadBinaryFile(filepath)
        if not s:
            # dhnio.Dprint(6, 'central_service.SendBandwidthReport WARNING %s is empty' % filepath)
            continue
        src += '[out] %s\n' % filename
        src += s.strip()
        src += '\n[end]\n'
    # dhnio.Dprint(4, '\n' + src)
    if src.strip() == '':
        # dhnio.Dprint(4, 'central_service.SendBandwidthReport WARNING src is empty. skip.')
        return None
    return send2central(commands.BandwidthReport(), src)

def ReceiveBandwidthAck(packet):
    dhnio.Dprint(4, 'central_service.ReceiveBandwidthAck')
    for line in packet.Payload.split('\n'):
        try:
            typ, filename = line.strip().split(' ')
        except:
            continue
        if typ == '[in]':
            filepath = os.path.join(settings.BandwidthInDir(), filename)
        elif typ == '[out]':
            filepath = os.path.join(settings.BandwidthOutDir(), filename)
        else:
            dhnio.Dprint(2, 'central_service.ReceiveBandwidthAck ERROR typ=%s filename=%s' % (typ, filename))
            continue
        if not os.path.isfile(filepath):
            dhnio.Dprint(2, 'central_service.ReceiveBandwidthAck ERROR %s not found' % filepath)
            continue
        if os.path.isfile(filepath+'.sent'):
            dhnio.Dprint(2, 'central_service.ReceiveBandwidthAck WARNING %s already sent' % filepath)
            continue
        try:
            os.rename(filepath, filepath+'.sent')
        except:
            dhnio.Dprint(2, 'central_service.ReceiveBandwidthAck ERROR can not rename %s' % filepath)
            dhnio.DprintException()
        dhnio.Dprint(4, '  %s %s accepted' % (typ, filename))

#-------------------------------------------------------------------------------

# possible values are: 
# '!' - ONLINE, 'x' - OFFLINE, '~' - was connected in last hour, '?' - unknown
def get_user_status(idurl):
    global _CentralStatusDict
    return _CentralStatusDict.get(idurl, '?') 

def clear_users_statuses(users_list):
    global _CentralStatusDict
    for idurl in users_list:
        _CentralStatusDict.pop(idurl, None)
     
#------------------------------------------------------------------------------ 

def main():
    try:
        from twisted.internet import reactor
    except:
        sys.exit('Error initializing twisted.internet.reactor in central_service.py')

    transport_control.init()
    SendIdentity()
    reactor.run()


if __name__ == '__main__':
    main()



