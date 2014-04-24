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

"""
This is a core module.

Identity might better be called business card, since it is really
mostly just your contatct info.  But more than that since public key.
Hum.

Example in http://identity.datahaven.net/veselin.xml

Could have info just be XML on a web page.  So an Identity could be a URL.
If we do this, then we get the scaling of DNS for free.  

DataHaven.net could have mappings from unique short names to URLs for
identities.  Or we could just make sure that the MD5 of the URL was
always unique (this is 16 bytes).  Or we could go with the primary URL.  
Hum.  DataHaven.net does need some sort of unique identifier, as do others.  
Also, would be nice to be able to send someone a list of their 
current 64 nodes they use, or the 300 that use them, without
crazy amounts of data.  For display
of backup status I would like a unique identifier that is short,
like 15 chars or something.  Can get main part of URLs that is
short like that, say "id.ai/vince1".  Seems funny to limit the
length of a URL like this, but we could as there will be
identity servers and they can get very short names like id.ai.
If we forced them all to be ".com/" we could display "id:vince1",
or "cate:vince1", which is short.  The force could just be
a lower rating for those that did not do this.  Could have
short name take up 2 lines out of my 5, and just plan on 
letting user click on things to change what things are
displayed.  So they have 5 lines and full URL takes 2,
but last of URL is just 1 line, and maybe they don't 
care what the name is and just display other stuff.

If we open it up a bit, people could just use tinyurl.com/foolksd
if their URL was too long.  We could limit primary URL
to 32 chars and not really have any trouble.  Can say it
must start with http:// (so we don't have to store that)
and be less than 32 chars after that.  If does not really
start with http:// then tiny URL can fix that too.

It is a bit like bittorrent using a .torrent file on the
web to get the original start for things.  This seems good.

All Identity/business-card info in XML:
PublicKey
primary URL for this identity (say https://cate.com/vinceID)
backup URLs for this identity (maybe URLs) that secondary this identity
contact: domain/port  pairs  (good even if IP out of date)
contact: IP/port  pairs    (good even if DNS in trouble)
contact: nat-traverser/ID pairs  (for those without fixed IPs)
contact: emails for this identity (recommend people have one just in case)
contact: http://foobar.com/data.pl    (use a web account to forward requests/data)
scrubbers: URL1, URL2, URL3           (people who can access our data if we stop checking it)
date
version number
signature on all identity info

Contact list has enough info we can tell what protocol to use.
User could put in order he prefers us to try the contact methods.  
So we might have a list like:
    datahaven:offshore.ai:5008
    datahaven:209.88.68.34:5008
    stun:stun.me:90
    vertex:foo@bar.com
    email:datahaven@gmail.com
    email:datahaven@hotmal.com
    http://foobar.com/data.pl?vince    

Really best if all the identity servers use SSL.
We could make certificates for identity servers, but might
not bother as it is probably best if they have ones that
web browsers understand.    
On the other hand, this might be a good way to get into the certificate-authority business. :-)

Having XML on a web site means we can start before we
really have identity server code.  Also means it is
easy to grok and debug.

As long as identity server is just some CGI that we can run on
any ISP anywhere (pair.com etc), and users always use 3 identity servers,
then we could just pop up as many as needed on ISPs all over
the world as fast as we grew.  It would not be an infrastructure
limitation really.  And we don't need to farm it out.
Identity's are signed and have a version number, so an identity
server can pass on an update that it gets to other servers listed
for that identity (in case there is network partition funnyness)
to help keep all of them updated. 
"""

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
    """
    We are passed an XML version of an identity and make an Identity.
    Also can construct an Identity by providing all fields. 
    The fields is:
        sources : list of URLs, first is primary URL and name
        certificates : signatures by identity servers
        publickey : the public part of user's key, string in twisted.conch.ssh format
        contacts : list of ways to contact this identity
        scrubbers : list of URLs for people allowed to scrub
        date : the date an time when that identity was created 
        version : a version string
        signature : digital signature to protect the file
    """
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
        """
        Erase all fields data, clear identity.
        """
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
        """
        Do some checking on the object fields.
        """
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
        """
        Return a source IDURL - this is a user ID.
        Must have at least one IDURL in the `sources`.
        """
        result = self.sources[index].strip()
        return result

    def getIDName(self, index = 0):
        """
        Return an account name - this is just a user name taken from IDURL:
            "veselin" for "http://identity.datahaven.net/veselin.xml"
        """
        protocol, host, port, filename = nameurl.UrlParse(self.getIDURL(index))
        return filename.strip()[0:-4]

    def clearContacts(self):
        """
        Erase all items in identity contacts list.
        """
        self.contacts = []

    def getContacts(self):
        """
        Return identity contacts list.
        """
        return self.contacts

    def getContactsNumber(self):
        """
        Return identity contacts number.
        """
        return len(self.contacts)

    def getContact(self, index=0):
        """
        Return a contact with given `index` number or None.
        """ 
        try:
            return self.contacts[index]
        except:
            return None

    def setContact(self, contact, index):
        """
        Set a string value `contact` at given `index` position in the list.
        """
        self.contacts[index] = contact

    def setCertificate(self, certificate):
        """
        Not used yet. 
        TODO. Need to ask Vince for more details about id certificates.
        """
        self.certificate = certificate
        self.sign()

    def setContactPort(self, index, newport):
        """
        This is useful when listening port get changed. 
        """
        protocol, host, port, filename = nameurl.UrlParse(self.contacts[index])
        url = nameurl.UrlMake(protocol, host, newport, filename)
        self.contacts[index] = url.encode("ascii").strip()

    def getContactHost(self, index):
        """
        Get the host name part of the contact.
        """
        protocol, host, port, filename = nameurl.UrlParse(self.contacts[index])
        return host

    def getContactPort(self, index):
        """
        Get the port part of the contact.
        """
        protocol, host, port, filename = nameurl.UrlParse(self.contacts[index])
        return port

    def setContactHost(self, host, index):
        """
        This is to set only host part of the contact. 
        """
        protocol, host_, port, filename = nameurl.UrlParse(self.contacts[index])
        url = nameurl.UrlMake(protocol, host, port, filename)
        self.contacts[index] = url.encode("ascii").strip()

    def getContactParts(self, index):
        """
        Return tuple with 4 parts of the contact:
            (proto, host, port, filename) 
        """
        return nameurl.UrlParse(self.contacts[index])

    def getProtoParts(self, proto):
        """
        See `getProtoContact`, return a tuple for given `proto`:
            (proto, host, port, filename) 
        """
        contact = self.getProtoContact(proto)
        if contact is None:
            return None, None, None, None
        return nameurl.UrlParse(contact)

    def getProtoHost(self, proto, default=None):
        """
        See `getProtoParts`, return a host of a contact with given `proto`.
        """
        protocol, host, port, filename = self.getProtoParts(proto)
        if host is None:
            return default
        return host

    def setContactParts(self, index, protocol, host, port, filename):
        """
        Set a contact at given position by its 4 parts.
        """
        url = nameurl.UrlMake(protocol, host, port, filename)
        self.contacts[index] = url.encode("ascii").strip()

    def getContactIndex(self, proto):
        """
        Search a first contact with given `proto`.
        """
        for i in range(0, len(self.contacts)):
            if self.contacts[i].find(proto+"://") == 0:
                return i
        return -1

    def setProtoContact(self, proto, contact):
        """
        Found a contact with given `proto` and set its value or append a new contact.
        """
        for i in range(0,len(self.contacts)):
            proto_, host, port, filename = nameurl.UrlParse(self.contacts[i])
            if proto_.strip() == proto.strip():
                self.contacts[i] = contact
                return
        self.contacts.append(contact)

    def getProtoContact(self, proto):
        """
        Search for first found contact with given `proto`. Return None if not found a contact.
        """
        for contact in self.contacts:
            if contact.startswith(proto+"://"):
                return contact
        return None

    def getProtoOrder(self):
        """
        Return a list of "proto" parts of all contacts.
        In other words return a list of all supported protocols.
        This keeps the order of the protos - this is a sort of priority of the transports. 
        """
        orderL = []
        for c in self.contacts:
            proto,host,port,filename = nameurl.UrlParse(c)
            orderL.append(proto)
        return orderL

    def getContactsByProto(self):
        """
        Return a dictionary of all contacts where keys are protos.
        """
        d = {}
        for i in range(len(self.contacts)):
            proto, x, x, x = nameurl.UrlParse(self.contacts[i])
            d[proto] = self.contacts[i]
        return d

    def getContactProto(self, index):
        """
        Return a proto part of the contact at given position.
        """
        c = self.getContact(index)
        if c is None:
            return None
        return nameurl.UrlParse(c)[0]

    def getIP(self, proto=None):
        """
        A smart way to get the IP address of the user.
        Check TCP proto first, than UDP.
        """
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
        """
        Remove all contacts with given `proto`.
        """
        for contact in self.contacts:
            if contact.find(proto+"://") == 0:
                self.contacts.remove(contact)

    def pushProtoContact(self, proto):
        """
        Move given protocol in the bottom of the contacts list.
        First contact in the list have more priority for remote machine,
        so we can manipulate our protos to get more p2p connections.
        Push less reliable protocols to the end of the list.
        This is to decrease its priority. 
        """
        i = self.getContactIndex(proto)
        if i < 0:
            return
        contact = self.contacts[i]
        del self.contacts[i]
        self.contacts.append(contact)

    def popProtoContact(self, proto):
        """
        Move given protocol to the top of the contacts list.
        This is to increase its priority.
        """
        i = self.getContactIndex(proto)
        if i < 0:
            return
        contact = self.contacts[i]
        del self.contacts[i]
        self.contacts.insert(0, contact)

    def makehash(self):
        """
        http://docs.python.org/lib/module-urlparse.html
        Note that certificates and signatures are not part of what is hashed.
        PREPRO 
        Thinking of standard that fields have labels and empty fields are left out,
        including label, so future versions could have same signatures as older which had fewer fields - 
        can just do this for fields after these, so maybe don't need to change anything for now.
        Don't include certificate - so identity server can just add it.
        """
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
        hashcode = dhncrypto.Hash(stufftohash)          
        return hashcode

    def sign(self):
        """
        Make a hash, generate digital signature on it and remember the signature.
        """
        hashcode = self.makehash()
        self.signature = dhncrypto.Sign(hashcode)
##        if self.Valid():
##            dhnio.Dprint(12, "identity.sign tested after making and it looks good")
##        else:
##            dhnio.Dprint(1, "identity.sign ERROR tested after making sign ")
##            raise Exception("sign fails")

    def Valid(self):
        """
        This will make a hash and verify the signature by public key.
        PREPRO - should test certificate too.
        """
        hashcode = self.makehash()
        result = dhncrypto.VerifySignature(
            self.publickey,
            hashcode,
            str(self.signature))
        return result

    def unserialize(self, xmlsrc):
        """
        A smart method to load object fields data from XML content.
        """
        try:
            doc = minidom.parseString(xmlsrc)
        except:
            dhnio.DprintException()
            dhnio.Dprint(2, '\n'+xmlsrc[:256]+'\n')
            return
        self.clear_data()
        self.from_xmlobj(doc.documentElement)

    def unserialize_object(self, xmlobject):
        """
        This is almost same but load data from existing DOM object.
        """
        self.clear_data()
        self.from_xmlobj(xmlobject)

    def serialize(self):
        """
        A method to generate XML content for that identity object. 
        Used to save identity on disk or transfer over network.  
        """
        return self.toxml()[0]

    def serialize_object(self):
        """
        Almost the same but return a DOM object.
        """
        return self.toxml()[1]

    def toxml(self):
        """
        Call this to convert to XML format. 
        """
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
        """
        This is to load identity fields from DOM object - used during `unserialize` procedure.
        """
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

def makeDefaultIdentity(name='', ip=''):
    """
    Use some local settings and config files to create some new identity.
    Nice to provide a user name or it will have a form like: [ip address]_[date].     
    """
    dhnio.Dprint(4, 'identity.makeDefaultIdentity: %s %s' % (name, ip))
    if ip == '':
        ip = dhnio.ReadTextFile(settings.ExternalIPFilename())
    if name == '':
        name = ip.replace('.', '-') + '_' + time.strftime('%M%S')
    servername = settings.IdentityServerName()
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
    """
    Some tests.
    """
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
    """
    More tests.
    """
    ident = makeDefaultIdentity()
    print ident.serialize() 

#------------------------------------------------------------------------------ 


def main():
    """
    This should print a current identity or create a new one.
    """
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
    """
    A good way to check all things - load and sign again.
    """
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



