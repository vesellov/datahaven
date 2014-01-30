#!/usr/bin/python
#identitycache.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
# identitycache.py stores local copies of identities
#
# This fetches identities off the web and stores an xml copy in file and an identity object
#   in a dictionary.  
# Other parts of DHN call this to get an identity using an IDURL.

import os

from twisted.internet.defer import Deferred

import dhnio
import dhnnet
import settings
import identitydb
import nameurl

_CachingTasks = {}

#-------------------------------------------------------------------------------

def init(success_func=None, fail_func=None):
    dhnio.Dprint(4, 'identitycache.init')
    identitydb.init()
    CacheCentralID(success_func, fail_func)
    CacheMoneyServerID()
    CacheMarketServerID()
    

def CacheCentralID(success_func=None, fail_func=None):
    dhnio.Dprint(6, 'identitycache.CacheCentralID')
    if HasKey(settings.CentralID()):
        if success_func:
            success_func('')
        return
    src = dhnio._read_data(os.path.join(dhnio.getExecutableDir(), 'dhncentral.xml'))
    if src:
        if identitydb.update(settings.CentralID(), src):
            if success_func:
                success_func('')
            return
    d = immediatelyCaching(settings.CentralID())
    if success_func is not None:
        d.addCallback(success_func)
    if fail_func is not None:
        d.addErrback(fail_func)
    else:
        d.addErrback(lambda x: dhnio.Dprint(6, 'identitycache.CacheCentralID NETERROR: '+x.getErrorMessage()))
        
        
def CacheMoneyServerID():
    dhnio.Dprint(6, 'identitycache.CacheMoneyServerID')
    immediatelyCaching(settings.MoneyServerID()).addErrback(lambda x: dhnio.Dprint(6, 'identitycache.CacheMoneyServerID NETERROR: '+x.getErrorMessage()))


def CacheMarketServerID():
    dhnio.Dprint(6, 'identitycache.CacheMarketServerID')
    immediatelyCaching(settings.MarketServerID()).addErrback(lambda x: dhnio.Dprint(6, 'identitycache.CacheMarketServerID NETERROR: '+x.getErrorMessage()))    


def Clear(excludeList=None):
    identitydb.clear(excludeList)


def CacheLen():
    return identitydb.size()


def PrintID(url):
    identitydb.print_id(url)


def PrintCacheKeys():
    identitydb.print_keys()


def PrintAllInCache():
    identitydb.print_cache()


def HasKey(url):
    return identitydb.has_key(url)


def FromCache(url):
    return identitydb.get(url)


def GetIDURLsByContact(contact):
    return identitydb.get_idurls_by_contact(contact)


def GetIDURLByIPPort(ip, port):
    return identitydb.get_idurl_by_ip_port(ip, port)


def GetContacts(url):
    return identitydb.idcontacts(url)


def Remove(url):
    return identitydb.remove(url)


def UpdateAfterChecking(url, xml_src):
    #dhnio.Dprint(12, 'identitycache.UpdateAfterChecking ' + url)
    return identitydb.update(url, xml_src)


def RemapContactAddress(address):
    idurl = GetIDURLByIPPort(address[0], address[1])
    if idurl is not None and HasLocalIP(idurl):
        newaddress = (GetLocalIP(idurl), address[1])
#        dhnio.Dprint(8, 'identitycache.RemapContactAddress for %s [%s] -> [%s]' % (
#            nameurl.GetName(idurl), str(address), str(newaddress)))
        return newaddress
    return address

#------------------------------------------------------------------------------ 

def getPageSuccess(src, url):
    UpdateAfterChecking(url, src)
    return src


def getPageFail(x, url):
    dhnio.Dprint(6, "identitycache.getPageFail NETERROR in request to " + url)
    return x


def pageRequestTwisted(url):
    d = dhnnet.getPageTwisted(url)
    d.addCallback(getPageSuccess, url)
    d.addErrback(getPageFail, url)
    return d


# Even if we have a copy in cache we are to try and read another one
def scheduleForCaching(url):
    return pageRequestTwisted(url)

#------------------------------------------------------------------------------ 

def immediatelyCaching(url, success_func=None, fail_func=None):
    global _CachingTasks
    if _CachingTasks.has_key(url):
        return _CachingTasks[url]
    
    def _getPageSuccess(src, url, res):
        global _CachingTasks
        _CachingTasks.pop(url)
        if UpdateAfterChecking(url, src):
            if success_func is not None:
                success_func(url+'\n'+src)
            res.callback(src)
        else:
            if fail_func is not None:
                fail_func(url+'\n'+src)
            res.errback(Exception(src))
        
    def _getPageFail(x, url, res):
        global _CachingTasks
        _CachingTasks.pop(url)
        if fail_func is not None:
            fail_func(x)
        res.errback(x)
        
    result = Deferred()
    d = dhnnet.getPageTwisted(url)
    d.addCallback(_getPageSuccess, url, result)
    d.addErrback(_getPageFail, url, result)
    
    _CachingTasks[url] = result
    
    return result

#------------------------------------------------------------------------------ 

def SetLocalIPs(local_ips):
    return identitydb.update_local_ips_dict(local_ips)


def GetLocalIP(idurl):
    return identitydb.get_local_ip(idurl)


def HasLocalIP(idurl):
    return identitydb.has_local_ip(idurl)


def SearchLocalIP(ip):
    return identitydb.search_local_ip(ip)

#------------------------------------------------------------------------------ 


