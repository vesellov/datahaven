#!/usr/bin/python
#identity.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#


import os
import sys
import time

from xml.dom import minidom, Node
from xml.dom.minidom import getDOMImplementation

import settings
import dhnio
import nameurl
import misc
import dhncrypto


default_identity_src = """<?xml version="1.0" encoding="ISO-8859-1"?>
<identity>
  <contacts>
  </contacts>
  <sources>
  </sources>
  <certificates>
  </certificates>
  <scrubbers>
  </scrubbers>
  <postage>1
  </postage>
  <date></date>
  <version>0</version>
  <publickey></publickey>
  <signature></signature>
</identity>"""


class identity:
    # Started from page 151 in "Fundations of Python Network Programming"
    # We are passed an XML version of an identity and make an Identity
    sources = []        # list of URLs, first is primary URL and name
    certificates = []   # signatures by identity servers
    publickey = ""      # string in twisted.conch.ssh format
    contacts = []       # list of ways to contact this identity
    scrubbers = []      # list of URLs for people allowed to scrub
    date = ""           # date
    version = "0"       # version string
    signature = ""      # digital signature

    def __init__ (  self,
                    sources = [],
                    certificates = [],
                    publickey = '',
                    contacts = [],
                    scrubbers = [],
                    postage = "1",
                    date = "",
                    version = "0",
                    xmlsrc = default_identity_src,
                    filename = '' ):

        self.sources = sources
        self.certificates = certificates
        self.publickey = publickey
        self.contacts = contacts
        self.scrubbers = scrubbers
        self.postage = postage
        self.date = date
        self.version = version

        if publickey != '':
            self.sign()
        else:
            self.signature=''
            # no point in signing if no public key listed, probably about to unserialize something

        if xmlsrc != '':
            self.unserialize(xmlsrc)

        if filename != '':
            self.unserialize(dhnio.ReadTextFile(filename))

    def clear_data(self):
        self.sources = []      # list of URLs for fetching this identiy, first is primary URL and name - called IDURL
        self.certificates = [] # identity servers each sign the source they are with - hash just (IDURL + publickey)
        self.publickey = ''    # string
        self.contacts = []     # list of ways to contact this identity
        self.scrubbers = []    # list of URLs for people allowed to scrub
        self.date = ''         # date
        self.postage = '1'     # postage price for message delivery if not on correspondents list
        self.version = '0'     # version string
        self.signature = ''    # digital signature

    def isCorrect(self):
        if len(self.contacts) == 0:
            return False
        if len(self.sources) == 0:
            return False
        if self.publickey == '':
            return False
        if self.signature == '':
            return False
        return True

    def getIDURL(self, index = 0):
        result = self.sources[index].strip()
        return result

    def getIDName(self, index = 0):
        protocol, host, port, filename = nameurl.UrlParse(self.getIDURL(index))
        return filename.strip()[0:-4]

    def setIDName(self, name, index = 0):
        protocol, host, port, filename = nameurl.UrlParse(self.getIDURL(index))
        url = nameurl.UrlMake(protocol, host, port, name+'.xml')
        self.sources[index] = url.encode("ascii").strip()

    def clearContacts(self):
        self.contacts = []

    def getContacts(self):
        return self.contacts

    def getContactsNumber(self):
        return len(self.contacts)

    def getContact(self, index=0):
        try:
##            return self.contacts[index].encode("ascii").strip()
            return self.contacts[index]
            # PREPRO don't understand why these were unicode
        except:
            return None

    def setContact(self, contact, index):
##        self.contacts[index] = contact.encode("ascii").strip()
        self.contacts[index] = contact

    def setCertificate(self, certificate):
        self.certificate=certificate
        self.sign()

    def setContactPort(self, index, newport):
        protocol, host, port, filename = nameurl.UrlParse(self.contacts[index])
        url = nameurl.UrlMake(protocol, host, newport, filename)
        self.contacts[index] = url.encode("ascii").strip()

    def getContactHost(self, index):
        protocol, host, port, filename = nameurl.UrlParse(self.contacts[index])
        return host

    def getContactPort(self, index):
        protocol, host, port, filename = nameurl.UrlParse(self.contacts[index])
        return port

    def setContactHost(self, host, index):
        protocol, host_, port, filename = nameurl.UrlParse(self.contacts[index])
        url = nameurl.UrlMake(protocol, host, port, filename)
        self.contacts[index] = url.encode("ascii").strip()

    def getContactParts(self, index):
        return nameurl.UrlParse(self.contacts[index])

    def getProtoParts(self, proto):
        contact = self.getProtoContact(proto)
        if contact is None:
            return None, None, None, None
        return nameurl.UrlParse(contact)

    def getProtoHost(self, proto, default=None):
        protocol, host, port, filename = self.getProtoParts(proto)
        if host is None:
            return default
        return host

    def setContactParts(self, index, protocol, host, port, filename):
        url = nameurl.UrlMake(protocol, host, port, filename)
        self.contacts[index] = url.encode("ascii").strip()

    def getContactIndex(self, proto):
        for i in range(0, len(self.contacts)):
            if self.contacts[i].find(proto+"://") == 0:
                return i
        return -1

    def setProtoContact(self, proto, contact):
        for i in range(0,len(self.contacts)):
            proto_, host, port, filename = nameurl.UrlParse(self.contacts[i])
            if proto_.strip() == proto.strip():
                self.contacts[i] = contact
                return
        self.contacts.append(contact)

    def getProtoContact(self, proto):
        for contact in self.contacts:
            if contact.startswith(proto+"://"):
                return contact
        return None

    def getProtoOrder(self):
        orderL = []
        for c in self.contacts:
            proto,host,port,filename = nameurl.UrlParse(c)
            orderL.append(proto)
        return orderL

    def getContactsByProto(self):
        d = {}
        for i in range(len(self.contacts)):
            proto, x, x, x = nameurl.UrlParse(self.contacts[i])
            d[proto] = self.contacts[i]
        return d

    def getContactProto(self, index):
        c = self.getContact(index)
        if c is None:
            return None
        return nameurl.UrlParse(c)[0]

    def getIP(self, proto=None):
        if proto:
            host = self.getProtoHost(proto)
            if host:
                return host
        host = self.getProtoHost('tcp')
        if host:
            return host
        host = self.getProtoHost('udp')
#        if host is None:
#            host = self.getProtoHost('ssh')
#        if host is None:
#            host = self.getProtoHost('http')
        return host

    def deleteProtoContact(self, proto):
        for contact in self.contacts:
            if contact.find(proto+"://") == 0:
                self.contacts.remove(contact)

    #move given protocol in the bottom of the contacts list
    def pushProtoContact(self, proto):
        i = self.getContactIndex(proto)
        if i < 0:
            return
        contact = self.contacts[i]
        del self.contacts[i]
        self.contacts.append(contact)

    #move given protocol to the top of the contacts list
    def popProtoContact(self, proto):
        i = self.getContactIndex(proto)
        if i < 0:
            return
        contact = self.contacts[i]
        del self.contacts[i]
        self.contacts.insert(0, contact)

    # http://docs.python.org/lib/module-urlparse.html
    # note that certificates and signatures are not part of what is hashed
    def makehash(self):
        sep = "-"
        c = ''
        for i in self.contacts:
            c += i
        s = ''
        for i in self.scrubbers:
            s += i
        sr = ''
        for i in self.sources:
            sr += i
        stufftohash = c + sep + s + sep + sr + sep + self.version + sep + self.postage + sep + self.date.replace(' ', '_')
        #PREPRO thinking of standard that fields have lables and empty fields are left out,
        #including label, so future versions could have same signatures as older which had fewer fields - can just do this for fields after these,
        #so maybe don't need to change anything for now
        hashcode = dhncrypto.Hash(stufftohash)          # don't include certificate - so identity server can just add it
        return hashcode

    def sign(self):
        hashcode = self.makehash()
        self.signature = dhncrypto.Sign(hashcode)
##        if self.Valid():
##            dhnio.Dprint(12, "identity.sign tested after making and it looks good")
##        else:
##            dhnio.Dprint(1, "identity.sign ERROR tested after making sign ")
##            raise Exception("sign fails")

    def Valid(self):
        # PREPRO - should test certificate too
        hashcode = self.makehash()
        result = dhncrypto.VerifySignature(
            self.publickey,
            hashcode,
            str(self.signature))
        return result

    def unserialize(self, xmlsrc):
        try:
            doc = minidom.parseString(xmlsrc)
        except:
            dhnio.DprintException()
            dhnio.Dprint(2, '\n'+xmlsrc[:256]+'\n')
            return
        self.clear_data()
        self.from_xmlobj(doc.documentElement)

    def unserialize_object(self, xmlobject):
        self.clear_data()
        self.from_xmlobj(xmlobject)

    def serialize(self):
        return self.toxml()[0]

    def serialize_object(self):
        return self.toxml()[1]

    def toxml(self):
        impl = getDOMImplementation()
        doc = impl.createDocument(None, 'identity', None)
        root = doc.documentElement
        contacts = doc.createElement('contacts')
        root.appendChild(contacts)
        for contact in self.contacts:
            n = doc.createElement('contact')
            n.appendChild(doc.createTextNode(contact))
            contacts.appendChild(n)

        sources = doc.createElement('sources')
        root.appendChild(sources)
        for source in self.sources:
            n = doc.createElement('source')
            n.appendChild(doc.createTextNode(source))
            sources.appendChild(n)

        certificates = doc.createElement('certificates')
        root.appendChild(certificates)
        for certificate in self.certificates:
            n = doc.createElement('certificate')
            n.appendChild(doc.createTextNode(certificate))
            certificates.appendChild(n)

        scrubbers = doc.createElement('scrubbers')
        root.appendChild(scrubbers)
        for scrubber in self.scrubbers:
            n = doc.createElement('scrubber')
            n.appendChild(doc.createTextNode(scrubber))
            scrubbers.appendChild(n)

        postage = doc.createElement('postage')
        postage.appendChild(doc.createTextNode(self.postage))
        root.appendChild(postage)

        date = doc.createElement('date')
        date.appendChild(doc.createTextNode(self.date))
        root.appendChild(date)

        version = doc.createElement('version')
        version.appendChild(doc.createTextNode(self.version))
        root.appendChild(version)

        publickey = doc.createElement('publickey')
        publickey.appendChild(doc.createTextNode(self.publickey))
        root.appendChild(publickey)

        signature = doc.createElement('signature')
        signature.appendChild(doc.createTextNode(self.signature))
        root.appendChild(signature)

        return doc.toprettyxml("  ", "\n", "ISO-8859-1"), root, doc

    def from_xmlobj(self, root_node):
        if root_node is None:
            return
        try:
            for xsection in root_node.childNodes:
                if xsection.nodeType != Node.ELEMENT_NODE:
                    continue
                if xsection.tagName == 'contacts':
                    for xcontacts in xsection.childNodes:
                        for xcontact in xcontacts.childNodes:
                            if (xcontact.nodeType == Node.TEXT_NODE):
                                self.contacts.append(xcontact.wholeText.strip().encode())
                elif xsection.tagName == 'sources':
                    for xsources in xsection.childNodes:
                        for xsource in xsources.childNodes:
                            if (xsource.nodeType == Node.TEXT_NODE):
                                self.sources.append(xsource.wholeText.strip().encode())
                elif xsection.tagName == 'certificates':
                    for xcertificates in xsection.childNodes:
                        for xcertificate in xcertificates.childNodes:
                            if (xcertificate.nodeType == Node.TEXT_NODE):
                                self.certificates.append(xcertificate.wholeText.strip().encode())
                elif xsection.tagName == 'scrubbers':
                    for xscrubbers in xsection.childNodes:
                        for xscrubber in xscrubbers.childNodes:
                            if (xscrubber.nodeType == Node.TEXT_NODE):
                                self.scrubbers.append(xscrubber.wholeText.strip().encode())
                elif xsection.tagName == 'publickey':
                    for xkey in xsection.childNodes:
                        if (xkey.nodeType == Node.TEXT_NODE):
                            self.publickey=xkey.wholeText.strip().encode()
                elif xsection.tagName == 'postage':
                    for xpostage in xsection.childNodes:
                        if (xpostage.nodeType == Node.TEXT_NODE):
                            self.date=xpostage.wholeText.strip().encode()
                elif xsection.tagName == 'date':
                    for xkey in xsection.childNodes:
                        if (xkey.nodeType == Node.TEXT_NODE):
                            self.date=xkey.wholeText.strip().encode()
                elif xsection.tagName == 'version':
                    for xkey in xsection.childNodes:
                        if (xkey.nodeType == Node.TEXT_NODE):
                            self.version=xkey.wholeText.strip().encode()
                elif xsection.tagName == 'signature':
                    for xkey in xsection.childNodes:
                        if (xkey.nodeType == Node.TEXT_NODE):
                            self.signature=xkey.wholeText.strip().encode()
        except:
            dhnio.DprintException()

#-------------------------------------------------------------------------------

def makeDefaultIdentity(name='', ip='', successTCP='', successSSH='', successHTTP=''):
    dhnio.Dprint(4, 'identity.makeDefaultIdentity: %s %s tcp:%s ssh:%s http:%s' % (name, ip, successTCP, successSSH, successHTTP))
    if ip == '':
        ip = dhnio.ReadTextFile(settings.ExternalIPFilename())
    if name == '':
        name = ip.replace('.', '-') + '_' + time.strftime('%M%S')
    servername = settings.DefaultIdentityServer()
    url = 'http://'+servername+'/'+name.lower()+'.xml'

    ident = identity(xmlsrc=default_identity_src)
    ident.sources.append(url.encode("ascii").strip())
    ident.certificates=[]
    cdict = {}
    if settings.enableTCP() and settings.enableTCPreceiving():
        cdict['tcp'] = 'tcp://'+ip+':'+settings.getTCPPort()
    if settings.enableUDP() and settings.enableUDPreceiving():
        cdict['udp'] = 'udp://'+ip+':'+settings.getUDPPort()
    # if settings.enableSSH():
    #     cdict['ssh'] = 'ssh://'+ip+':'+settings.getSSHPort()
    # if settings.enableHTTP() or settings.enableHTTPServer():
    #     cdict['http'] = 'http://'+ip+':'+settings.getHTTPPort()
    # if settings.enableQ2Q():
    #     if settings.getQ2Qusername().strip() != '' and settings.getQ2Qhost().strip() != '':
    #         cdict['q2q'] = 'q2q://'+settings.getQ2Quserathost()
    #     else:
    #         cdict['q2q'] = 'q2q://default@'+settings.getQ2Qhost()
    # if settings.enableEMAIL():
    #     if settings.getEmailAddress().strip() != '':
    #         cdict['email'] = 'email://'+settings.getEmailAddress()
    #     else:
    #         cdict['email'] = 'email://'+name+'@datahaven.net'
    if settings.enableCSpace():
        if settings.getCSpaceKeyID() != '':
            cdict['cspace'] = 'cspace://'+settings.getCSpaceKeyID()
        else:
            cdict['cspace'] = 'cspace://not-registered'
        
    for c in misc.validTransports:
        if cdict.has_key(c):
            ident.contacts.append(cdict[c].encode("ascii").strip())

    ident.publickey = dhncrypto.MyPublicKey()
    ident.date = time.strftime('%b %d, %Y')
    ident.postage = "1"

    revnum = dhnio.ReadTextFile(settings.RevisionNumberFile())
    repo, location = misc.ReadRepoLocation()
    ident.version = (revnum.strip() + ' ' + repo.strip() + ' ' + dhnio.osinfo().strip()).strip()

    ident.sign()

    return ident

#-------------------------------------------------------------------------------

def test1():
    myidentity=misc.getLocalIdentity()
    print 'getIP =', myidentity.getIP()
    if myidentity.Valid():
        print "myidentity is Valid!!!!"
    else:
        print "myidentity is not Valid"
        misc.saveLocalIdentity()            # sign and save
        raise Exception("myidentity is not Valid")
    print "myidentity.contacts"
    print myidentity.contacts
    print "len myidentity.contacts "
    print len (myidentity.contacts)
    print "len myidentity.contacts[0] "
    print myidentity.contacts[0]
    con=myidentity.getContact()
    print "con:", con, type(con)
    protocol, machine, port, filename = nameurl.UrlParse(con)
    print protocol, machine, port, filename
    print "identity.main serialize:\n", myidentity.serialize()
    for index in range(myidentity.getContactsNumber()):
        proto, host, port, filename = myidentity.getContactParts(index)
        print '[%s] [%s] [%s] [%s]' % (proto, host, port, filename)


def test2():
    ident = makeDefaultIdentity()
    print ident.serialize() 

#------------------------------------------------------------------------------ 


def main():
    misc.loadLocalIdentity()
    if misc.isLocalIdentityReady():
        misc.getLocalIdentity().sign()
        print misc.getLocalIdentity().serialize()
        print 'Valid is: ', misc.getLocalIdentity().Valid()
    else:
        misc.setLocalIdentity(makeDefaultIdentity(sys.argv[1]))
        misc.saveLocalIdentity()
        print misc.getLocalIdentity().serialize()
        print 'Valid is: ', misc.getLocalIdentity().Valid()
        misc._LocalIdentity = None
        misc.loadLocalIdentity()
        
def update():
    dhnio.init()
    settings.init()
    src = dhnio.ReadTextFile(settings.LocalIdentityFilename())
    misc.setLocalIdentity(identity(xmlsrc=src))
    misc.getLocalIdentity().sign()
    misc.saveLocalIdentity()
    print misc.getLocalIdentity().serialize()    
    
#------------------------------------------------------------------------------ 


if __name__ == '__main__':
    dhnio.SetDebug(18)
    main()



