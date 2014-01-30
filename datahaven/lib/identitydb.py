#!/usr/bin/python
#identitydb.py

import os
import dhnio
import settings
import identity
import nameurl

# Dictionary cache of identities - lookup by primary url
# global dictionary of identities in this file
# indexed with urls and contains identity objects
_IdentityCache = {}
_Contact2IDURL = {}
_IDURL2Contacts = {}
_IPPort2IDURL = {}
_LocalIPs = {}

#------------------------------------------------------------------------------ 

def init():
    dhnio.Dprint(4,"identitydb.init")
    iddir = settings.IdentityCacheDir()
    if not os.path.exists(iddir):
        dhnio.Dprint(8, 'identitydb.init create folder ' + iddir)
        dhnio._dir_make(iddir)

def clear(exclude_list=None):
    global _IdentityCache
    global _Contact2IDURL
    global _IPPort2IDURL
    global _IDURL2Contacts
    dhnio.Dprint(4,"identitydb.clear")
    _IdentityCache.clear()
    _Contact2IDURL.clear()
    _IPPort2IDURL.clear()
    _IDURL2Contacts.clear()

    iddir = settings.IdentityCacheDir()
    if not os.path.exists(iddir):
        return

    for name in os.listdir(iddir):
        path = os.path.join(iddir, name)
        if not os.access(path, os.W_OK):
            continue
        if exclude_list:
            idurl = nameurl.FilenameUrl(name)
            if idurl in exclude_list:
                continue 
        os.remove(path)
        dhnio.Dprint(6, 'identitydb.clear remove ' + path)

def size():
    global _IdentityCache
    return len(_IdentityCache)

def has_key(idurl):
    global _IdentityCache
    return _IdentityCache.has_key(idurl)

def idset(idurl, id_obj):
    global _IdentityCache
    global _Contact2IDURL
    global _IDURL2Contacts
    global _IPPort2IDURL
    if not has_key(idurl):
        dhnio.Dprint(6, 'identitydb.idset new identity: ' + idurl)
    _IdentityCache[idurl] = id_obj
    for contact in id_obj.getContacts():
        if not _Contact2IDURL.has_key(contact):
            _Contact2IDURL[contact] = set()
        else:
            if len(_Contact2IDURL[contact]) >= 1 and idurl not in _Contact2IDURL[contact]:
                dhnio.Dprint(6, 'identitydb.idset WARNING another user have same contact: ' + str(list(_Contact2IDURL[contact])))
        _Contact2IDURL[contact].add(idurl)
        if not _IDURL2Contacts.has_key(idurl):
            _IDURL2Contacts[idurl] = set()
        _IDURL2Contacts[idurl].add(contact)
        try: 
            proto, host, port, fname = nameurl.UrlParse(contact)
            ipport = (host, int(port))
            _IPPort2IDURL[ipport] = idurl 
        except:
            pass

def idget(url):
    global _IdentityCache
    return _IdentityCache.get(url, None)

def idremove(url):
    global _IdentityCache
    global _Contact2IDURL
    global _IDURL2Contacts
    global _IPPort2IDURL
    idobj = _IdentityCache.pop(url, None)
    _IDURL2Contacts.pop(url, None)
    if idobj is not None:
        for contact in idobj.getContacts():
            _Contact2IDURL.pop(contact, None)
            try: 
                proto, host, port, fname = nameurl.UrlParse(contact)
                ipport = (host, int(port))
                _IPPort2IDURL.pop(ipport, None) 
            except:
                pass
    return idobj

def idcontacts(idurl):
    global _IDURL2Contacts
    return list(_IDURL2Contacts.get(idurl, set()))

def get(url):
    if has_key(url):
        return idget(url)
    else:
        try:
            partfilename = nameurl.UrlFilename(url)
        except:
            dhnio.Dprint(1, "identitydb.get ERROR %s is incorrect" % str(url))
            return None
        
        filename = os.path.join(settings.IdentityCacheDir(), partfilename)
        if not os.path.exists(filename):
            dhnio.Dprint(6, "identitydb.get file %s not exist" % os.path.basename(filename))
            return None
        
        idxml = dhnio.ReadTextFile(filename)
        if idxml:
            idobj = identity.identity(xmlsrc=idxml)
            url2 = idobj.getIDURL()
            if url == url2:
                idset(url, idobj)
                return idobj
            
            else:
                dhnio.Dprint(1, "identitydb.get ERROR url=%s url2=%s" % (url, url2))
                return None

        dhnio.Dprint(6, "identitydb.get %s not found" % nameurl.GetName(url))
        return None

def get_idurls_by_contact(contact):
    global _Contact2IDURL
    return list(_Contact2IDURL.get(contact, set()))

def get_idurl_by_ip_port(ip, port):
    global _IPPort2IDURL
    return _IPPort2IDURL.get((ip, int(port)), None)

def update(url, xml_src):
    try:
        newid = identity.identity(xmlsrc=xml_src)
    except:
        dhnio.DprintException()
        return False

    if not newid.isCorrect():
        dhnio.Dprint(1, "identitydb.update ERROR: incorrect identity " + str(url))
        return False

    try:
        if not newid.Valid():
            dhnio.Dprint(1, "identitydb.update ERROR identity not Valid" + str(url))
            return False
    except:
        dhnio.DprintException()
        return False

    filename = os.path.join(settings.IdentityCacheDir(), nameurl.UrlFilename(url))
    if os.path.exists(filename):
        oldidentityxml = dhnio.ReadTextFile(filename)
        oldidentity = identity.identity(xmlsrc=oldidentityxml)

        if oldidentity.publickey != newid.publickey:
            dhnio.Dprint(1, "identitydb.update ERROR new publickey does not match old : SECURITY VIOLATION " + url)
            return False

        if oldidentity.signature != newid.signature:
            dhnio.Dprint(6, 'identitydb.update have new data for ' + nameurl.GetName(url))
        else:
            idset(url, newid)
            return True

    # PREPRO need to check that date or version is after old one so not vulnerable to replay attacks
    dhnio.WriteFile(filename, xml_src)             # publickeys match so we can update it
    idset(url, newid)

    return True

def remove(url):
    filename = os.path.join(settings.IdentityCacheDir(), nameurl.UrlFilename(url))
    if os.path.isfile(filename):
        dhnio.Dprint(6, "identitydb.remove file %s" % filename)
        try:
            os.remove(filename)
        except:
            dhnio.DprintException()
    idremove(url)

def update_local_ips_dict(local_ips_dict):
    global _LocalIPs
    # _LocalIPs.clear()
    # _LocalIPs = local_ips_dict
    _LocalIPs.update(local_ips_dict)
    
def get_local_ip(idurl):
    global _LocalIPs
    return _LocalIPs.get(idurl, None)

def has_local_ip(idurl):
    global _LocalIPs
    return _LocalIPs.has_key(idurl)

def search_local_ip(ip):
    global _LocalIPs
    for idurl, localip in _LocalIPs.items():
        if localip == ip:
            return idurl
    return None

#------------------------------------------------------------------------------ 

def print_id(url):
    if has_key(url):
##        print "has key"
##        idForKey = _IdentityCache[url]
        idForKey = get(url)
        dhnio.Dprint(6, str(idForKey.sources) )
        dhnio.Dprint(6, str(idForKey.contacts ))
        dhnio.Dprint(6, str(idForKey.publickey ))
        dhnio.Dprint(6, str(idForKey.signature ))

def print_keys():
    global _IdentityCache
    for key in _IdentityCache.keys():
        dhnio.Dprint(6, key)
##    print "PrintCacheKeys"

def print_cache():
    global _IdentityCache
##    print "PrintCacheKeys"
    for key in _IdentityCache.keys():
        dhnio.Dprint(6, "---------------------" )
        print_id(key)









