# service.py - CSpace Service
# Utilities
from bisect import bisect
import StringIO
import logging, sys
# PID, path
import os, os.path
import atexit

logger = logging.getLogger('cspace.main.service')

# Local command XMLRPC server
from SimpleXMLRPCServer import SimpleXMLRPCServer

# Select socket event dispatcher
from nitro.selectreactor import SelectReactor, SelectStoppedError
from nitro.async import AsyncOp
from nitro.http import HttpRequest

# RSA Key management
from ncrypt0.rsa import RSAKey, RSAError

# Event dispatcher
from cspace.util.eventer import Eventer
# Session management
from cspace.main.session import UserSession
# Profile management
from cspace.main.profile import listProfiles, loadProfile, saveProfileContacts, Contact
# from cspace.main.app import Reconnector, LogFile
from cspace.main.common import isValidUserName, localSettings
from cspace.main.appletserver import AppletServer, ActionConfig
from cspace.util.hexcode import hexEncode


class Reconnector( object ) :
    def __init__( self, profile, timerCallback, reactor ) :
        self.reconnecting = False
        self.profile = profile
        self.timerCallback = timerCallback 
        self.reactor = reactor
        self.timerOp = None
        self.timeLeft = 0

    def startReconnectTimer( self, errorMsg ) :
        self.errorMsg = errorMsg
        self.reconnecting = True
        self.timeLeft = 20
        self.timerOp = self.reactor.addTimer( 1, self._onTimer )

    def shutdown( self ) :
        if self.timerOp :
            self.timerOp.cancel()
            self.timerOp = None
        self.reconnecting = False

    def _onTimer( self ) :
        self.timeLeft -= 1
        if self.timeLeft == 0 :
            self.shutdown()
        self.timerCallback()


class LogFile( object ) :
    def __init__( self, settings=None, appName="CSpace" ) :
        if settings is None:
            settings = localSettings()
        configDir = settings.getConfigDir()
        logFile = os.path.join( configDir, '%s.log'%appName )
        try :
            if os.path.getsize(logFile) >= 1024*1024 :
                os.remove( logFile )
        except OSError :
            pass
        self.f = file( logFile, 'a' )

    def write( self, s ) :
        self.f.write( s )
        self.f.flush()

    def flush( self ) :
        pass


##########
## Contact action management
##
class ActionManager:
    def __init__(self):
        global logger
        self.nextActionId = 0
        self.actions = []
        self.defaultActionId = -1
        self.activeActions = ActionConfig().listActiveActions()

    def registerAction( self, action, actionCallback, actionOrder ):
        actionId = self.nextActionId
        self.nextActionId += 1
        actionDir = [adir for adir, aname, acmd, apri in self.activeActions
                          if aname == action ][0]
        info = [actionOrder,action,actionId,actionCallback,actionDir]
        pos = bisect( self.actions, info )
        self.actions.insert( pos, info )
        return actionId

    def setDefaultAction( self, actionId ) :
        if self.defaultActionId >= 0 : return False
        self.defaultActionId = actionId
        return True

    def unregisterAction( self, actionId ) :
        for pos,info in enumerate(self.actions) :
            if info[2] == actionId :
                del self.actions[pos]
                if self.defaultActionId == actionId :
                    self.defaultActionId = -1
                return True
        assert False

    def execAction( self, actionDir, contactName ) :
        global logger
        for info in self.actions :
            if info[4] == actionDir :
                # logger.info("Executing action %s on contact %s, callback id is %d" % (actionDir, contactName, id(info[3])))
                info[3]( contactName )
                return True
            else:
                logger.debug( "Not action %s" % str(info[1]) )
        return False, "Action %s not found." % actionDir

    def execDefaultAction( self, contactName ) :
        for info in self.actions :
            if info[2] is self.defaultActionId :
                info[3]( contactName )
                return


##########
## Auto-contact status prober
##
class ContactStatusChecker:
    LONGTIME = 2 * 60
    SHORTTIME = 1

    ONLINE = UserSession.ONLINE
    OFFLINE = UserSession.OFFLINE
    UNKNOWN = -1

    def __init__(self, service, reactor):
        self.service = service
        self.reactor = reactor
        self.dispatcher = self.service.dispatcher
        self.dispIdAdd = None
        self.dispIdRem = None
        self.probeOps = {}

    def startProbing(self):
        self.contacts = self.service.profile.contactNames.keys()
        self.dispIdRem = self.dispatcher.register( "contact.remove",
                                                    self.onContactRemoved )
        self.dispIdAdd = self.dispatcher.register( "contact.add",
                                                    self.onContactAdded )
        self.nextOp = self.reactor.addTimer(self.LONGTIME, self.probeContactsStatus)
        self.probeContactsStatus()

    def onContactRemoved(self, contact):
        if self.probeOps.has_key(contact.name):
            del self.probeOps[contact.name]

    def onContactAdded(self, contact):
        self.contacts.append(contact.name)
        self.probeContactStatus(contact.name)

    def stopProbing(self):
        if self.dispIdAdd:
            self.service.dispatcher.remove( self.dispIdAdd )
        if self.dispIdRem:
            self.service.dispatcher.remove( self.dispIdRem )
        self.probeOps = {}
        if self.nextOp:
            self.nextOp.cancel()

    def probeContactsStatus(self):
        if self.service.status != self.ONLINE:
            return

        self.dispatcher.trigger( "contacts.probing", self.contacts )

        for contactToProbe in self.service.profile.contactNames:
            self.probeContactStatus(contactToProbe)

    def probeContactStatus(self, cname):
        contact = self.service.profile.getContactByName(cname)
        keyID = contact.publicKey
        # logger.debug("Probing status of contact %s..." % contact.name)
        self.service.session.probeUserOnline(keyID,
                    lambda s: self.onStatusProbed(cname, s) )
        self.probeOps[cname] = True

    def onStatusProbed(self, cname, status, forceNotify=True):
        contact = self.service.profile.getContactByName(cname)
        if contact:
            oldstatus = hasattr(contact, 'status') and contact.status or self.UNKNOWN
            if status:
                contact.status = self.ONLINE
            else:
                contact.status = self.OFFLINE

            if status != oldstatus or forceNotify:
                if contact.status == self.ONLINE:
                    self.service.dispatcher.trigger("contact.online", contact)
                elif contact.status == self.OFFLINE:
                    self.service.dispatcher.trigger("contact.offline", contact)

            # logger.debug("Contact %s status: %s" % (contact.name, self.service.STATII[contact.status]))
        else:
            logger.debug("Contact removed before status returned.")

        if self.probeOps.has_key(cname):
            del self.probeOps[cname]
        if len(self.probeOps) == 0:
            self.dispatcher.trigger( "contacts.probed", self.contacts )


class CSpaceService:
    OFFLINE = UserSession.OFFLINE
    CONNECTING = UserSession.CONNECTING
    ONLINE = UserSession.ONLINE
    DISCONNECTING = UserSession.DISCONNECTING
    UNKNOWN = -1

    STATII = {
        OFFLINE: "Offline",
        CONNECTING: "Connecting",
        ONLINE: "Online",
        DISCONNECTING: "Disconnecting",
        UNKNOWN: "Unknown"
        }


    ##########
    ## Service initialization
    ##
    def __init__(self, seedNodes, settings=None, reactor=None):
        global logger
        logger.info('CSpaceService init')
        if reactor is None:
            reactor = SelectReactor()

        if settings is None:
            settings = localSettings()

        self.reactor = reactor
        self.settings = settings
        self.dispatcher = Eventer()
        self.seedNodes = seedNodes

        # Session Manager
        self.session = UserSession( self.seedNodes, reactor )

        # Our user profile
        self.profile = None

        # Session status State Machine
        self.sm = self.session.sm
        # Make sure we handle the edges/state transitions
        self.sm.insertCallback( self._onStateChange )
        # Manage actions
        self.actionManager = ActionManager()
        # Loads applets in subprocesses
        self.appletServer = AppletServer( self.session, self.actionManager,
                                          self.reactor )

        # Our contacts' statii
        self.statusProbe = ContactStatusChecker(self, reactor)

        # Our current status
        self.status = self.sm.current()
        self.statusmsg = self.STATII[self.status]
        self.exitAfterOffline = False

        self.reactor.callLater(0, self._onStarted)

    def _onStarted(self):
        self.dispatcher.trigger("service.start")

    def _error(self, msg):
        logger.error(msg)
        self.dispatcher.trigger("error", msg)
        return (False, msg)

    def run(self):
        self.reactor.run()
        try:
            self.appletServer.bridgeThread.reactor.stop()
        except AttributeError:
            pass

    def svcstatus(self):
        return self.statusmsg

    def stop(self):
        # offline first
        if self.status != self.OFFLINE:
            self.exitAfterOffline = True
            return self.offline()

        for reactor in (self.appletServer.bridgeThread.reactor,
                        self.reactor):
            reactor.stop()

        self.dispatcher.trigger("service.stop")
        return True

    ##########
    ## Go online and offline, change profiles
    ##
    def switch(self, profile, password):
        if self.status is not self.OFFLINE:
            return self._error("Not currently offline.")

        st = self.settings
        logger.debug("Changing profile...")
        profiles = [userName for userName,keyId,entry in listProfiles()]
        if not st.getInt('Settings/RememberKey',0):
            return self._error("No key found.")

        if not profile in entries:
            return self._error("No profile %s found.")

        profile = loadProfile( profile, password )
        if not profile:
            return self._error("Profile couldn't be loaded.")

        st.setString("Settings/SavedProfile", profile.name)
        st.setString("Settings/SavedPassword", password)
        saveLocalSettings()

        self.dispatcher.trigger("profile.switch", profile)
        return True


    def online(self):
        global logger
        if self.status is not self.OFFLINE:
            return self._error("Not currently offline.")

        st = self.settings
        logger.debug("Going online...")
        entries = [entry for userName,keyId,entry in listProfiles()]
        if not st.getInt('Settings/RememberKey',0):
            return self._error("No key found.")

        entry = st.getString('Settings/SavedProfile')
        password = st.getString('Settings/SavedPassword')
        if not (entry and password and (entry in entries)):
            return self._error("No profile or password.")

        profile = loadProfile( entry, password )
        if not profile:
            return self._error("Profile couldn't be loaded.")

        self.profile = profile
        logger.debug("Going online as %s keyID=%s ..." % (profile.name, profile.keyId))
        self.session.goOnline( self.profile )
        self.reconnector = Reconnector( self.profile,
                self._onReconnectTimer, self.reactor )

        return True

    def _onReconnectTimer( self ) :
        assert self.reconnector
        if self.reconnector.timeLeft > 0 :
            return
        self.profile = self.reconnector.profile
        self.reconnector.shutdown()
        if self.session.sm.current() == 0:
            self.session.goOnline( self.profile )
            self.reconnector = Reconnector( self.profile,
                self._onReconnectTimer, self.reactor )
            self.dispatcher.trigger("profile.reconnecting", self.profile)

    def offline(self):
        if self.status is not self.ONLINE:
            return self._error("Not currently online.")
        self.session.goOffline()
        self.profile = None
        self.reconnector.shutdown()
        self.reconnector = None
        return True


    def _onStateChange(self):
        """ Respond to connecting/online/disconnecting/offline notices """

        self.status = self.sm.current()
        self.statusmsg = None

        # No longer online
        if self.sm.previous() == self.ONLINE:
            # Stop checking contact statii
            self.statusProbe.stopProbing()
            # Clean up any open applets
            self.appletServer.clearConnections()

        # Now offline
        if self.sm.current() == self.OFFLINE:
            profile = self.profile
            self.profile = None
            if self.reconnector:
                if self.sm.previous() == self.CONNECTING :
                    msg = 'Connect failed.'
                else :
                    msg = 'Disconnected.'
                self.reconnector.startReconnectTimer( msg )
                self.statusmsg = msg
            self.dispatcher.trigger("profile.offline", profile)
            if self.exitAfterOffline:
                self.stop()


        # Now online
        elif self.sm.current() == self.ONLINE:
            # Restart checking contact statii
            self.dispatcher.trigger("profile.online", self.profile)
            self.statusProbe.startProbing()

        # Now connecting
        elif self.sm.current() == self.CONNECTING:
            self.dispatcher.trigger("profile.connecting", self.profile)
        elif self.sm.current() == self.DISCONNECTING:
            self.dispatcher.trigger("profile.disconnecting", self.profile)

        if not self.statusmsg:
            self.statusmsg = self.STATII[self.status]

        logger.info("STATUS: " + self.statusmsg)



    ##########
    ## List, add and remove contacts
    ##
    def list(self):
        if self.status != self.ONLINE:
            return self._error("Not connected.")

        contactsByName = self.profile.contactNames
        statii = []
        STATII = CSpaceService.STATII
        for key in contactsByName:
            contact = contactsByName[key]
            if hasattr(contact, "status"):
                buddystatus = (key, contact.status, STATII[contact.status])
            else:
                buddystatus = (key, -1, STATII[-1])
            statii.append(buddystatus)

        statii.sort()
        return statii

    def add(self, cname, keyid):
        # Lookup the contact info and call _doAddContact
        if self.status != self.ONLINE:
            return self._error("Can't lookup buddy while not online.")
        httpOp = HttpRequest( self.reactor ).get(
                # 'http://cspace.in/pubkey/%s' % keyid,
                'http://identity.datahaven.net/cspacekeys/%s' % keyid,
                self._onLookupResponse )
        self._addOp = AsyncOp( self._onAddContact, httpOp.cancel )
        self._addOp.cname = cname
        return True

    def addKey(self, cname, key):
        if cname and not isValidUserName(cname) :
            return self._error("Bad username.")

        k = RSAKey()
        try :
            k.fromPEM_PublicKey( pemPublicKey )
        except RSAError :
            return self._error("Bad PEM-encoded key.")

        contact = Contact( k, cname )
        self._onAddContact( contact )


    def _onLookupResponse(self, responseCode, data):
        if responseCode != 200 :
            self._addOp.notify( None )
            return
        inp = StringIO.StringIO( data )
        name = inp.readline().strip()
        pemPublicKey = inp.read()
        if name and not isValidUserName(name) :
            self._addOp.notify( None )
            return

        k = RSAKey()
        try :
            k.fromPEM_PublicKey( pemPublicKey )
        except RSAError :
            self._addOp.notify( None )

        contact = Contact( k, self._addOp.cname )
        self._addOp.notify( contact )

    def _onAddContact(self, contact):
        del self._addOp
        if contact == None:
            # Contact lookup failed.
            return

        self.profile.addContact( contact )
        saveProfileContacts( self.profile )
        self.dispatcher.trigger('contact.add', contact)

    def remove(self, cname=None):
        if self.status != self.ONLINE:
            return self._error("Can't modify contact list while not online.")
        # Lookup the contact in profile and remove it
        contact = self.profile.getContactByName(cname)
        if contact is None:
            return self._error("No such contact.")
        self.profile.removeContact(contact)
        saveProfileContacts( self.profile )
        self.dispatcher.trigger('contact.remove', contact)
        return True


    #########
    ## Perform contact action
    ##
    def action(self, buddy, action):
        if self.status != self.ONLINE:
            return False

        actionManager = self.actionManager
        if buddy not in self.profile.contactNames:
            return self._error("Bad buddy name: %s" % buddy)

        for actionItem in actionManager.actions:
            if actionItem[4] == action:
                logger.info("Running action %s on %s" % (action, buddy))
                retVal = actionManager.execAction(action, buddy)
                self.dispatcher.trigger("contact.action",
                                        self.profile.contactNames[buddy],
                                        action, retVal)
                return retVal
            else:
                logger.info("Not action %s" % actionItem[4])

        return self._error("Bad action name: %s" % action)

    def probe(self, buddy):
        if self.status != self.ONLINE:
            return self._error("Not online.")

        if buddy not in self.profile.contactNames:
            return self._error("Bad buddy name: %s" % buddy)

        self.statusProbe.probeContactStatus(buddy)
        return True

    def contactinfo(self, buddy):
        if self.status != self.ONLINE:
            return self._error("Not online.")

        if buddy not in self.profile.contactNames:
            return self._error("Bad buddy name: %s" % buddy)

        contact = self.profile.contactNames[buddy]
        contactKey = hexEncode(contact.publicKeyData)
        if hasattr(contact, 'status'):
            contactStatus = contact.status
        else:
            contactStatus = -1
        return [ contact.name, contactKey, self.STATII[contactStatus] ]

def _parseCommandLine():
    import optparse
    # Construct the command line argument handling
    oparser = optparse.OptionParser()

    oparser.add_option("-n", "--node", dest="dhtnode",
                        help="connect to DHT node at address", metavar="DHTIP")
    oparser.add_option("-p", "--port", dest="dhtport", type="int",
                        help="connect to DHT node on port", metavar="DHTPORT")
    oparser.add_option("-l", "--local", dest="localdht", action="store_true",
                        help="connect to DHT on localhost:10001")
    oparser.add_option("-x", "--xmlrpc", dest="rpcport", metavar="XMLPORT",
                        help="listen for local XMLRPC commands on port",
                        type="int")
    oparser.add_option("-d", "--debug", dest="debug", action="store_true",
                        help="don't redirect stderr/stdout")

	# I started a "CSpaceNetwork.py -b 208.78.96.185" command on our "datahaven.net" machine
	# So CSpace users may use it for some time.
	# Would be nice if some one else do the same to have more seed nodes
    oparser.set_default('dhtnode', '208.78.96.185') # "210.210.1.102" - that is old "dead" cspace,in server
    oparser.set_default('dhtport', 10001)
    oparser.set_default('debug', False)
    oparser.set_default('xmlport', 0)
    oparser.set_default('localdht', False)

    # Parse the command line
    (options, args) = oparser.parse_args()


    if options.localdht == True:
        from cspace.network import localip
        localip.USE_LOCALHOST = True
        options.dhtnode = "127.0.0.1"
        options.dhtport = 10001

    options.dhtport = int(options.dhtport)
    options.xmlport = int(options.xmlport)

    return options, args

def getPIDpath(appName="CSpace"):
    pidfile = "%s.run" % appName
    pidpath = os.path.join("~", ".CSpace")
    pidpath = os.path.expanduser(pidpath)
    if not os.path.exists(pidpath):
        os.makedirs(pidpath)
    pidpath = os.path.join(pidpath, pidfile)
    return pidpath

def _writePID(xmlrpcport, appletport):
    pidpath = getPIDpath()
    pidfile = file(pidpath, "wb")
    pidfile.write("%i\n%i\n%i\n" % (os.getpid(), xmlrpcport, appletport))
    pidfile.close()

def _deletePID():
    pidpath = getPIDpath()
    os.unlink(pidpath)

def main():
    global logger, reactor
    options, args = _parseCommandLine()
    settings = localSettings()

    if not options.debug:
        sys.stdout = sys.stderr = LogFile( settings )
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)
    logger.addHandler( logging.StreamHandler() )
    logging.getLogger('nitro.selectreactor').addHandler( logging.StreamHandler() )

    reactor = SelectReactor()
    seedNodes = [(options.dhtnode, options.dhtport)]
    service = CSpaceService(seedNodes, settings, reactor)
    server = SimpleXMLRPCServer(('localhost', options.xmlport))
    reactor.addReadCallback(server, server.handle_request)
    server.register_instance(service, allow_dotted_names = True)

    xmlrpcport = server.socket.getsockname()[1]
    logger.info("rpcserver listenport = %i" % xmlrpcport)
    appletport = service.appletServer.listenPort
    logger.info("seed nodes = (%s:%i)" % (options.dhtnode, options.dhtport))
    _writePID(xmlrpcport, appletport)
    service.run()
    _deletePID()
    logger.info("server stopped.")
