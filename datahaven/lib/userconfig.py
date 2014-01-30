#!/usr/bin/python
#userconfig.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#
#
#to add a single item in the user configuration:
#1. edit userconfig.py: UserConfig.default_xml_src
#   do not forget to add tag "label" and "info".
#2. edit settings.py
#   you can add access functions like getECC() or getCentralNumSuppliers()
#3. edit guisettings.py if you wish user to be able to edit this item:
#   add key pair to dictionary CSettings.items
#   you can define your own Widget (for example: XMLTreeEMailSettingsNode or XMLTreeQ2QSettingsNode)
#   if you are using ComboBox Widget (xmltreenodes.XMLTreeComboboxNode)
#   you need to add his definition after line comment "#define combo boxes"
#4. finally, you need to read this value using lib.settings and do something...


import os
import locale

from xml.dom import minidom
from xml.dom import Node
from xml.dom.minidom import getDOMImplementation

#-------------------------------------------------------------------------------

InfosDict = {
    'general':                      "General options.",
    'general-backups':              'How many backup copies of each directory to keep, oldest will be removed automatically? ( 0 = unlimited )',
    'general-autorun':              "Starting the application during system startup.",
    'general-display-mode':         "Specifies how you want the window to display when you start the software.",
    'general-desktop-shortcut':     "Place shortcut on the Desktop?",
    'general-start-menu-shortcut':  "Add shortcut to the Start Menu?",
    'general-local-backups-enable': "Also keep a copy of your backups on local HDD?",
    'general-wait-suppliers-enable':"Wait 24 hours and check suppliers status before removing the locally backed up data.",
    'updates':                      "Software updates options.",
    'updates-mode':                 "You can choose one of the install modes. Software must be restarted after installation of the new version.",
    'updates-shedule':              "You can setup updating schedule here.",
    'central-settings':             "Central Server Settings. Here you can manage your settings stored on the DataHaven.NET Central Server (c).",
    'desired-suppliers':            "Number of remote suppliers which keeps your backups.<br><font color=red>WARNING!</font> You will lost all your backups after changing suppliers number.",
    'needed-megabytes':             "How many megabytes you need to store your files?",
    'shared-megabytes':             "How many megabytes you ready to donate to other users?",
    'folder-backups':               "Place for your local backups files.",
    'folder-restore':               'Location where your restored files should be placed.',
    'folder-customers':             'Place for donated space, other users will keep their files here.',
    'folder-messages':              'Folder to store your messages.',
    'folder-receipts':              'Folder to store receipts.',
    'emergency':                    "We can contact you if your account balance is running low, if your backups are not working, or if your machine appears to not be working.",
    'emergency-first':              "What is your preferred method for us to contact you if there are problems?",
    'emergency-second':             "What is the second best method to contact you?",
    'emergency-email':              "What email address should we contact you at? Email contact is free.",
    'emergency-phone':              "If you would like to be contacted by phone, what number can we reach you at? ($1 per call for our time and costs)",
    'emergency-fax':                "If you would like to be contacted by fax, what number can we reach you at? ($0.50 per fax for our time and costs)",
    'emergency-text':               "Other method we should contact you by? Cost will be based on our costs.",
    'personal':                     'Your personal information.',
    'personal-name':                'Your name',
    'personal-surname':             'Your surname',
    'personal-nickname':            'Nickname',
    'personal-betatester':          'Are you agree to participate in the DataHaven.NET project testing?',
    'network':                      'Network settings.',
    'network-send-limit':           'The value in kilobytes per second to decrease network load. At the moment the maximum sending speed that DataHaven.NET can support is about half megabyte per second. 0 - no limit.',
    'network-receive-limit':        'Limit incoming traffic with a value in kilobytes per second. 0 - no limit.',
    'backup':                       'Backups setting',
    'backup-block-size':            'Preferred block size in bytes when doing a backup.',
    'backup-max-block-size':        'Maximum block size in bytes when doing a backup, if you plan to do a huge backups - set higher values to increase the speed.',
    'transport':                    'You can use different protocols to transfer packets, called "transports". Here you can customize your transport settings.',
    'transport-tcp':                "transport_tcp uses the standard TCP protocol to transfer packets.",
    'transport-tcp-port':           "Enter the TCP port number for the transport_tcp, it will be used to connect with your machine.",
    'transport-tcp-enable':         "transport_tcp uses the standard TCP protocol to transfer packets.<br>Do you want to use transport_tcp?",
    'transport-tcp-sending-enable': 'Do you want to use transport_tcp for sending packets?',
    'transport-tcp-receiving-enable': 'Do you want to use transport_tcp for receiving packets?',
    'transport-udp':                'transport_udp provides NAT traversing functionality',
    'transport-udp-enable':         'transport_udp provides NAT traversing functionality,<br>Do you want to use transport_udp?',
    'transport-udp-port':           'Enter the UDP port number for the transport_tcp, it will be used to connect with your machine. Enter 0 and your OS will choose the port automatically.',
    'transport-udp-sending-enable': 'Do you want to use transport_udp for sending packets?',
    'transport-udp-receiving-enable': 'Do you want to use transport_udp for receiving packets?',
    'transport-cspace':             'CSpace provides a platform for secure, decentralized, user-to-user communication over the internet.<br>Go to <a href="https://code.google.com/p/cspace/" target=_blank>https://code.google.com/p/cspace/</a> for more details.',
    'transport-cspace-enable':      'CSpace provides a platform for secure, decentralized, user-to-user communication over the internet.<br>Go to <a href="https://code.google.com/p/cspace/" target=_blank>https://code.google.com/p/cspace/</a> for more details.<br>Do you want to use transport_cspace?',
    'transport-cspace-key-id':      'CSpace provides a platform for secure, decentralized, user-to-user communication over the internet.<br>Go to <a href="https://code.google.com/p/cspace/" target=_blank>https://code.google.com/p/cspace/</a> for more details.<br>This is your CSpace user id, it should be set automatically during startup.',
    'transport-cspace-sending-enable': 'Do you want to use transport_cspace for sending packets?',
    'transport-cspace-receiving-enable': 'Do you want to use transport_cspace for receiving packets?',
    'upnp-enabled':                 'Do you want to use UPnP to configure port forwarding?',
    'debug-level':                  "Higher values will produce more log messages.",
    'stream-enable':                "Go to http://127.0.0.1:[logs port number] to browse the program log.",
    'memdebug-enable':              'Go to http://127.0.0.1:[memdebug port number] to see memory usage.',
    'memprofile-enable':            'Use guppy to profile memory usage.',
    'bitcoin-host':                 'address of the BitCoin RPC server',
    'bitcoin-port':                 'remote port of the BitCoin RPC server',
    'bitcoin-username':             'username to authenticate on the BitCoin RPC server',
    'bitcoin-password':             'password to authenticate on the BitCoin RPC server',
    'bitcoin-server-is-local':      'use local BitCoin JSON-RPC server instead of remote',
    'bitcoin-config-filename':      'path to the bitcoin.conf file with info to access the local BitCoin JSON-RPC server',
    }

LabelsDict = {
    'general':                              'general',
    'general-backups':                      'backup copies',
    'general-local-backups-enable':         'local backups',
    'general-wait-suppliers-enable':        'wait suppliers',
    'general-autorun':                      'autorun',
    'general-display-mode':                 'display mode',
    'general-desktop-shortcut':             'desktop shortcut',
    'general-start-menu-shortcut':          'start menu shortcut',
    'backup':                               'backup',
    'backup-block-size':                    'backup block size',
    'backup-max-block-size':                'maximum block size',
    'updates':                              'updates',
    'updates-mode':                         'mode',
    'updates-shedule':                      'schedule',
    'central-settings':                     'central server',
    'desired-suppliers':                    'number of suppliers',
    'needed-megabytes':                     'needed space',
    'shared-megabytes':                     'donated space',
    'folder':                               'folders',
    'folder-customers':                     'donated space',
    'folder-backups':                       'local backups',
    'folder-restore':                       'restored files',
    'folder-messages':                      'messages',
    'folder-receipts':                      'receipts',
    'emergency':                            'emergency',
    'emergency-first':                      'primary',
    'emergency-second':                     'secondary',
    'emergency-email':                      'email',
    'emergency-phone':                      'phone',
    'emergency-fax':                        'fax',
    'emergency-text':                       'other',
    'personal':                             'personal information',
    'personal-name':                        'name',
    'personal-surname':                     'surname',
    'personal-nickname':                    'nickname',
    'personal-betatester':                  'betatester',
    'network':                              'network',
    'network-send-limit':                   'outgoing bandwidth limit',
    'network-receive-limit':                'incoming bandwidth limit',
    'transport':                            'transports',
    'transport-tcp':                        'transport_tcp',
    'transport-tcp-port':                   'TCP port',
    'transport-tcp-enable':                 'transport_tcp enable',
    'transport-tcp-sending-enable':         'transport_tcp sending enable',
    'transport-tcp-receiving-enable':       'transport_tcp receiving enable',
    'transport-udp':                        'transport_udp',
    'transport-udp-port':                   'UDP port',
    'transport-udp-enable':                 'transport_udp enable',
    'transport-udp-sending-enable':         'transport_udp sending enable',
    'transport-udp-receiving-enable':       'transport_udp receiving enable',
    'transport-cspace':                     'transport_cspace',
    'transport-cspace-enable':              'transport_cspace enable',
    'transport-cspace-key-id':              'CSpace user id',
    'transport-cspace-sending-enable':      'transport_cspace sending enable',
    'transport-cspace-receiving-enable':    'transport_cspace receiving enable',
    'logs':                                 'logs',
    'debug-level':                          'debug level',
    'stream-enable':                        'enable logs',
    'stream-port':                          'logs port number',
    'memdebug-enable':                      'enable memdebug',
    'memdebug-port':                        'memdebug port number',
    'memprofile-enable':                    'enable memory profiler',
    'traffic-enable':                       'enable packets traffic',
    'traffic-port':                         'traffic port number',
    'other':                                'other',
    'upnp-enabled':                         'UPnP enable',
    'upnp-at-startup':                      'check UPnP at startup',
    'bitcoin-host':                         'BitCoin server hostname',
    'bitcoin-port':                         'BitCoin server port',
    'bitcoin-username':                     'BitCoin server username',
    'bitcoin-password':                     'BitCoin server password',
    'bitcoin-server-is-local':              'use local BitCoin server',
    'bitcoin-config-filename':              'path to the bitcoin.conf file',
    }

#------------------------------------------------------------------------------ 

class UserConfig:
    default_xml_src = ur"""<settings>
 <general>
  <general-backups>
   2
  </general-backups>
  <general-local-backups-enable>
   True
  </general-local-backups-enable>
  <general-wait-suppliers-enable>
   True
  </general-wait-suppliers-enable>
  <general-autorun>
   True
  </general-autorun>
  <general-display-mode>
   iconify window
  </general-display-mode>
  <general-desktop-shortcut>
   True
  </general-desktop-shortcut>
  <general-start-menu-shortcut>
   True
  </general-start-menu-shortcut>
 </general>
 <backup>
  <private-key-size>
   1024
  </private-key-size>
  <backup-block-size>
   262144
  </backup-block-size>
  <backup-max-block-size>
   10485760
  </backup-max-block-size>
 </backup>
 <updates>
  <updates-mode>
   install automatically
  </updates-mode>
  <updates-shedule>
1
12:00:00
6

  </updates-shedule>
 </updates>
 <central-settings>
  <desired-suppliers>
   7
  </desired-suppliers>
  <needed-megabytes>
   4GB
  </needed-megabytes>
  <shared-megabytes>
   8GB
  </shared-megabytes>
 </central-settings>
 <folder>
  <folder-customers>

  </folder-customers>
  <folder-backups>

  </folder-backups>
  <folder-restore>

  </folder-restore>
  <folder-messages>

  </folder-messages>
  <folder-receipts>

  </folder-receipts>
 </folder>
 <emergency>
  <emergency-first>
   email
  </emergency-first>
  <emergency-second>
   phone
  </emergency-second>
  <emergency-email>

  </emergency-email>
  <emergency-phone>

  </emergency-phone>
  <emergency-fax>

  </emergency-fax>
  <emergency-text>

  </emergency-text>
 </emergency>
 <network>
  <network-proxy>
   <network-proxy-enable>
    False
   </network-proxy-enable>
   <network-proxy-host>

   </network-proxy-host>
   <network-proxy-port>

   </network-proxy-port>
   <network-proxy-username>

   </network-proxy-username>
   <network-proxy-password>

   </network-proxy-password>
   <network-proxy-ssl>
    False
   </network-proxy-ssl>
  </network-proxy>
  <network-send-limit>
   0
  </network-send-limit>
  <network-receive-limit>
   0
  </network-receive-limit>
 </network>
 <transport>
  <transport-tcp>
   <transport-tcp-port>
    7771
   </transport-tcp-port>
   <transport-tcp-enable>
    True
   </transport-tcp-enable>
   <transport-tcp-sending-enable>
    True
   </transport-tcp-sending-enable>
   <transport-tcp-receiving-enable>
    True
   </transport-tcp-receiving-enable>
  </transport-tcp>
  <transport-udp>
   <transport-udp-port>
    0
   </transport-udp-port>
   <transport-udp-enable>
    True
   </transport-udp-enable>
   <transport-udp-sending-enable>
    True
   </transport-udp-sending-enable>
   <transport-udp-receiving-enable>
    True
   </transport-udp-receiving-enable>
  </transport-udp>
  <transport-cspace>
   <transport-cspace-enable>
    True
   </transport-cspace-enable>
   <transport-cspace-key-id>

   </transport-cspace-key-id>
   <transport-cspace-sending-enable>
    True
   </transport-cspace-sending-enable>
   <transport-cspace-receiving-enable>
    True
   </transport-cspace-receiving-enable>
  </transport-cspace>
 </transport>
 <personal>
  <personal-name>
  
  </personal-name>
  <personal-surname>
  
  </personal-surname>
  <personal-nickname>
  
  </personal-nickname>
  <personal-betatester>
   True
  </personal-betatester>
 </personal>
 <logs>
  <debug-level>
   4
  </debug-level>
  <stream-enable>
   False
  </stream-enable>
  <stream-port>
   9999
  </stream-port>
  <traffic-enable>
   False
  </traffic-enable>
  <traffic-port>
   9997
  </traffic-port>
  <memdebug-enable>
   False
  </memdebug-enable>
  <memdebug-port>
   9996
  </memdebug-port>
  <memprofile-enable>
   False
  </memprofile-enable>
 </logs>
 <other>
  <upnp-enabled>
   True
  </upnp-enabled>
  <upnp-at-startup>
   False
  </upnp-at-startup>
  <bitcoin>
   <bitcoin-host>
   
   </bitcoin-host>
   <bitcoin-port>
    8332
   </bitcoin-port>
   <bitcoin-username>
   
   </bitcoin-username>
   <bitcoin-password>
   
   </bitcoin-password>
   <bitcoin-server-is-local>
    False
   </bitcoin-server-is-local>
   <bitcoin-config-filename> 
    
   </bitcoin-config-filename> 
  </bitcoin>
 </other>
</settings>"""

    public_options = [  'general.general-backups',
                        'general.general-local-backups-enable',
                        'general.general-wait-suppliers-enable',
                        'central-settings.desired-suppliers',
                        'central-settings.needed-megabytes',
                        'central-settings.shared-megabytes',
                        'folder.folder-customers',
                        'folder.folder-backups',
                        'folder.folder-restore',
                        'folder.folder-messages',
                        'folder.folder-receipts',
                        'network.network-send-limit',
                        'network.network-receive-limit',
                        'transport.transport-tcp.transport-tcp-port',
                        'transport.transport-tcp.transport-tcp-enable',
                        'transport.transport-tcp.transport-tcp-sending-enable',
                        'transport.transport-tcp.transport-tcp-receiving-enable',
                        # 'transport.transport-udp.transport-udp-port',
                        'transport.transport-udp.transport-udp-enable',
                        'transport.transport-udp.transport-udp-sending-enable',
                        'transport.transport-udp.transport-udp-receiving-enable',
                        'transport.transport-cspace.transport-cspace-enable',
                        'transport.transport-cspace.transport-cspace-sending-enable',
                        'transport.transport-cspace.transport-cspace-receiving-enable',
                        'logs.debug-level',
                        'logs.stream-enable',
                        'logs.stream-port',
                        'other.upnp-enabled',
                        'other.bitcoin.bitcoin-host',
                        'other.bitcoin.bitcoin-port',
                        'other.bitcoin.bitcoin-username',
                        'other.bitcoin.bitcoin-password',
                        'other.bitcoin.bitcoin-server-is-local',
                        'other.bitcoin.bitcoin-config-filename',
                        ]

    xmlsrc = ''
    data = {}
    labels = {}
    infos = {}
    default_data = {}
    default_order = []

    def __init__(self, filename):
        self.filename = filename
        if os.path.isfile(self.filename):
            self._read()
        else:
            self._create()

        doc1 = self._parse(self.default_xml_src)
        self._load(
            self.default_data,
            doc1.documentElement,
            order=self.default_order, )

        doc2 = self._parse(self.xmlsrc)
        self._load(
            self.data,
            doc2.documentElement)

        self._validate(True)


    def _parse(self, src):
        try:
            s = src.encode('utf-8')
            return minidom.parseString(s)
        except:
            return minidom.parseString(self.default_xml_src.encode('utf-8'))

    def _read(self):
        fin = open(self.filename, 'r')
        src = fin.read()
        fin.close()
        self.xmlsrc = src.decode(locale.getpreferredencoding())

    def _write(self):
        src = self.xmlsrc.encode(locale.getpreferredencoding())
        try:
            fout = open(self.filename, 'w')
            fout.write(src)
            fout.flush()
            os.fsync(fout.fileno())
            fout.close()
        except:
            pass

    def _create(self):
        self.xmlsrc = self.default_xml_src
        self._write()

    # check existing user-config and our template, add nodes if they are missing
    def _validate(self, remove=False):
        changed = False
        for key in self.default_data.keys():
            if not self.data.has_key(key):
                self.data[key] = self.default_data[key]
                changed = True
        if remove:
            for key in self.data.keys():
                if not self.default_data.has_key(key):
                    del self.data[key]
                    changed = True
        if changed:
            self.xmlsrc = self._make_xml()[0]
            self._write()

    def _load(self, data, node, path='', order=None):
        d = get_text(node)
        if path != '':
            data[path] = d
        if order is not None:
            order.append(path)

        if not self.labels.has_key(path):
            l = get_label(node)
            if l is not None:
                self.labels[path] = l
            else:
                self.labels[path] = node.tagName

        if not self.infos.has_key(path):
            i = get_info(node)
            if i is not None:
                self.infos[path] = i

        for subnode in node.childNodes:
            if subnode.nodeType == Node.ELEMENT_NODE:
                name = str(subnode.tagName)
                if path != '':
                    name = path+'.'+name
                self._load(data, subnode, name, order)

    def _from_data(self, parent, doc):
        for path in self.default_order:
            if path.strip() == '':
                continue
            value = self.data.get(path, '')
            leafs = path.split('.')
            prevleaf = parent
            leafnode = None
            for leaf in leafs:
                leafnode = get_child(prevleaf, leaf)
                if leafnode is None:
                    leafnode = doc.createElement(leaf)
                    prevleaf.appendChild(leafnode)
                prevleaf = leafnode
            set_text(leafnode, value)

    def _make_xml(self):
        impl = getDOMImplementation()
        doc = impl.createDocument(None, 'settings', None)
        rootnode = doc.documentElement
        self._from_data(rootnode, doc)
        xmlsrc = doc.toprettyxml("  ","\n")
        return xmlsrc, rootnode

    def update(self, node=None):
        if node is None:
            self.xmlsrc = self.Serialize()
        else:
            self.UnserializeObject(node)
        self._write()

    def Serialize(self):
        doc1 = self._parse(self.xmlsrc)
        self.default_order = []
        self._load(
            self.default_data,
            doc1.documentElement,
            order=self.default_order, )
        return self._make_xml()[0]

    def SerializeObject(self):
        doc1 = self._parse(self.xmlsrc)
        self.default_order = []
        self._load(
            self.default_data,
            doc1.documentElement,
            order=self.default_order, )
        return self._make_xml()[1]

    def Unserialize(self, src):
        doc = self._parse(src)
        node = doc.documentElement
        self.data.clear()
        self._load(self.data, node)
        self.xmlsrc = doc.toprettyxml("  ", "\n") # doubles if put spaces here

    def UnserializeObject(self, xml_object):
        self.data.clear()
        self._load(self.data, xml_object)
        self.xmlsrc = xml_object.toprettyxml("  ", "\n") # doubles if put spaces here

    # use this when user needs to "reset to factory defaults"
    def reset(self):
        self.xmlsrc = self.default_xml_src

    def get(self, key, request=None):
        if not request:
            return self.data.get(key, None)
        elif request=='all':
            return (self.data.get(key, None),
                    self.labels.get(key, None),
                    self.infos.get(key, None),
                    self.default_data.get(key, None),)
        elif request=='data':
            return self.data.get(key, None)
        elif request=='label':
            return self.labels.get(key, None)
        elif request=='info':
            return self.infos.get(key, None)
        elif request=='default':
            return self.default_data.get(key, None)
        return self.data.has_key(key)

    def has(self, key):
        return self.data.has_key(key)

    def set(self, key, value, request=None):
        if request=='data':
            self.data[key] = value
        elif request=='label':
            self.labels[key] = value
        elif request=='info':
            self.infos[key] = value
        else:
            self.data[key] = value

    def get_childs(self, key, request=None):
        d = {}
        if request=='data':
            for k,v in self.data.items():
                if k.startswith(str(key)+'.'): d[k] = v
        elif request=='label':
            for k,v in self.labels.items():
                if k.startswith(str(key)+'.'): d[k] = v
        elif request=='info':
            for k,v in self.labels.items():
                if k.startswith(str(key)+'.'): d[k] = v
        elif request=='default':
            for k,v in self.default_data.items():
                if k.startswith(str(key)+'.'): d[k] = v
        else:
            for k,v in self.data.items():
                if k.startswith(str(key)+'.'): d[k] = v
        return d

    def set_childs(self, key, childs_dict):
        if not self.data.has_key(key):
            return
        for k,v in childs_dict.items():
            _key = k
            if not k.startswith(key+'.'):
                _key = key+'.'+k
            self.data[_key] = v

    def make_child_name(self, key, namebase):
        i = 0
        while True:
            name = unicode(key+'.'+namebase+str(i))
            if not self.data.has_key(name):
                return name
            i += 1

    def print_all(self):
        for path in self.default_order:
            if path.strip() == '':
                continue
            value = self.data.get(path, '')
            label = self.labels.get(path, '')
            print path.ljust(40),
            print label.ljust(20),
            print value

    def print_all_html(self):
        src = ''
        for path in self.default_order:
            if path.strip() == '':
                continue
            value = self.data.get(path, '')
            label = self.labels.get(path, '')
            info = self.infos.get(path, '')
            src += '<li><p><b>%s</b><br>\n' % label
            src += '&nbsp;' * 4 + '\n'
            src += info + '\n'
            src += '</p></li>\n'''
        return src

     

#-------------------------------------------------------------------------------

def get_child(father,childname):
    for son in father.childNodes:
        if son.nodeName == childname:
            return son
    return None

def get_text(xmlnode):
    rc = u''
    for node in xmlnode.childNodes:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data.strip()
    return rc.encode(locale.getpreferredencoding())

def set_text(xmlnode, txt):
    try:
        text = txt.decode(locale.getpreferredencoding())
    except:
        text = ''
    for node in xmlnode.childNodes:
        if node.nodeType == node.TEXT_NODE:
            node.data = u''
    j = 0
    while j < len(xmlnode.childNodes):
        node = xmlnode.childNodes[j]
        if node.nodeType == node.TEXT_NODE:
            node.data = text
            return
        j += 1
    node = xmlnode.ownerDocument.createTextNode(text)#.decode('latin_1'))
    xmlnode.appendChild(node)

def get_label(xmlnode):
    global LabelsDict
    return LabelsDict.get(xmlnode.tagName, xmlnode.tagName)

def get_info(xmlnode):
    global InfosDict
    return InfosDict.get(xmlnode.tagName, '')

#-------------------------------------------------------------------------------

def main():
    import settings
    uc = UserConfig(settings.UserConfigFilename())
    uc.update()
    # import pprint
    # pprint.pprint(uc.data)
    print uc.print_all_html()

##    for path in uc.default_order:
##        if path.strip() == '':
##            continue
##        leafs = path.split('.')
##        print path, len(leafs)


if __name__ == "__main__":
    main()



#  <transport-ssh>
#   <transport-ssh-port>
#    5022
#   </transport-ssh-port>
#   <transport-ssh-enable>
#    False
#   </transport-ssh-enable>
#  </transport-ssh>
#  <transport-q2q>
#   <transport-q2q-host>
#
#   </transport-q2q-host>
#   <transport-q2q-username>
#
#   </transport-q2q-username>
#   <transport-q2q-password>
#
#   </transport-q2q-password>
#   <transport-q2q-enable>
#    True
#   </transport-q2q-enable>
#  </transport-q2q>
#  <transport-email>
#   <transport-email-address>
#
#   </transport-email-address>
#   <transport-email-pop-host>
#
#   </transport-email-pop-host>
#   <transport-email-pop-port>
#
#   </transport-email-pop-port>
#   <transport-email-pop-username>
#
#   </transport-email-pop-username>
#   <transport-email-pop-password>
#
#   </transport-email-pop-password>
#   <transport-email-pop-ssl>
#    False
#   </transport-email-pop-ssl>
#   <transport-email-smtp-host>
#
#   </transport-email-smtp-host>
#   <transport-email-smtp-port>
#
#   </transport-email-smtp-port>
#   <transport-email-smtp-username>
#
#   </transport-email-smtp-username>
#   <transport-email-smtp-password>
#
#   </transport-email-smtp-password>
#   <transport-email-smtp-need-login>
#    False
#   </transport-email-smtp-need-login>
#   <transport-email-smtp-ssl>
#    False
#   </transport-email-smtp-ssl>
#   <transport-email-enable>
#    False
#   </transport-email-enable>
#  </transport-email>
#  <transport-http>
#   <transport-http-server-port>
#    9786
#   </transport-http-server-port>
#   <transport-http-ping-timeout>
#    5
#   </transport-http-ping-timeout>
#   <transport-http-enable>
#    True
#   </transport-http-enable>
#   <transport-http-server-enable>
#    True
#   </transport-http-server-enable>
#  </transport-http>
#  <transport-skype>
#   <transport-skype-enable>
#    False
#   </transport-skype-enable>
#  </transport-skype>
