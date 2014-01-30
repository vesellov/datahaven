#!/usr/bin/python
#settings.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

import os


import userconfig
import dhnio
import eccmap
import dhnmath
import diskspace
import nameurl


_BaseDirPath = ''   # location for ".datahaven" folder, lets keep all program DB in one place
                    # however you can setup your donated location in another place, second disk ...
                    # Linux: /home/$USER/.datahaven
                    # WindowsXP: c:\\Document and Settings\\[user]\\Application Data\\DataHaven.NET
                    # Windows7: c:\\Users\\[user]\\AppData\\Roaming\\DataHaven.NET 
_UserConfig = None  # user settings read from file .datahaven/metadata/user-config
_OverrideDict = {}  # list of values to replace some of user settings 
_BandwidthLimit = None 
_BackupBlockSize = None
_BackupMaxBlockSize = None
_InitDone = False    

#---INIT----------------------------------------------------------------------------

def init(base_dir=None):
    global _InitDone
    if _InitDone:
        return
    _InitDone = True
    _init(base_dir)

#---USER CONFIG---------------------------------------------------------------------------

def uconfig(key=None):
    global _UserConfig
    global _OverrideDict
    #init()
    if _UserConfig is None:
        if os.path.exists(os.path.join(MetaDataDir(),"user-config")) and not os.path.exists(os.path.join(MetaDataDir(),"userconfig")):
            dhnio.Dprint(4, 'settings.uconfig rename "user-config" to "userconfig"')
            try:
                os.rename(os.path.join(MetaDataDir(),"user-config"), os.path.join(MetaDataDir(),"userconfig"))
            except:
                pass
        dhnio.Dprint(6, 'settings.uconfig loading user configuration from: ' + UserConfigFilename())
        _UserConfig = userconfig.UserConfig(UserConfigFilename())
    if key is None:
        return _UserConfig
    else:
        if key in _OverrideDict:
            return _OverrideDict[key]
        res = _UserConfig.get(key)
        if res is None:
            return ''
        return res

# this (key, value) pairs will be used instead values from  _UserConfig
def override(key, value):
    global _OverrideDict
    dhnio.Dprint(4, 'settings.override %s=%s' % (key, value))
    _OverrideDict[key] = value

def override_dict(d):
    for key, value in d.items():
        override(key, value)

#---NUMBERS---------------------------------------------------------------------------

def DefaultPrivateKeySize():
    return 1024

# Dropbox have a 10$/month for 100-500 GB
# so let's have 10$ for 1Tb. this is 0.01 
def BasePricePerGBmonth():
    return 0.01

def BasePricePerGBDay():
    return BasePricePerGBmonth() / 30.0

def defaultDebugLevel():
    return 6

def IntSize():
    return 4

def MinimumSendingDelay():
    return 0.01

def MaximumSendingDelay():
    return 2.0 

def MinimumReceivingDelay():
    return 0.05

def MaximumReceivingDelay():
    return 4.0

# Should be a function of disk space available  PREPRO
def MaxPacketsOutstanding():
    return 100

# if sending below this speed - we count this supplier as failed
# if we sending too slow to all nodes - it's our problems
def SendingSpeedLimit():
    return 3 * 1024 # 1KB/sec is about 3.5MB/hour

# in kilo bytes per second
def DefaultBandwidthInLimit():
    return 0

# in kilo bytes per second, 0 - unlimited
def DefaultBandwidthOutLimit():
    return 0

def SendTimeOut():
    # return 600                   # 600 seconds send timeout for ssh/tcp/q2q
    return 60                     # 60 seconds send timeout for ssh/tcp/udp/q2q/cspace
    #return 30

def MaxRetries():                 # "exponential backoff" - double each time so 1024*SendTimeOut seconds or 7 days
#    return(10)
    return 1                      # Veselin put only 3 retries (3*SendTimeOut) in thought we do not need too old packets

def DefaultSendTimeOutEmail():
    return 300                    # timeout for email sending

def DefaultSendTimeOutHTTP():
    return 60                     # timeout for http sending

def DefaultAlivePacketTimeOut():
    return 60 * 60                  #lets send alive packets every hour

def DefaultBandwidthReportTimeOut():
    return 60 * 60 * 24                #send BandwidthReport every 24 hours

def DefaultNeedSuppliersPacketTimeOut():
    return 60                     #if we need suppliers we will send it every 60 sec.

def DefaultSuppliersNumber():
    return 4

def DefaultDesiredSuppliers():
    return 4

def DefaultLocaltesterLoop():
    return 20                   #every 20 sec

def DefaultLocaltesterValidateTimeout():
    return 120 * 60               #every 120 min

def DefaultLocaltesterUpdateCustomersTimeout():
    return 5 * 60                 #every 5 min

def DefaultLocaltesterSpaceTimeTimeout():
    return 5 * 60                 #every 10 min

def DefaultSignerSendingDelay():
    return 0.05

def DefaultSignerReceivingDelay():
    return 0.1

def DefaultSignerPingDelay():
    return 1.0

def MinimumUsernameLength():
    return 3

def MaximumUsernameLength():
    return 20

def DefaultDonatedMb():
    return 8*1024

def DefaultNeededMb():
    return 4*1024

def MinimumNeededMb():
    return 1

def MinimumDonatedMb():
    return 2

def DefaultBackupBlockSize():
    return 256 * 1024

def DefaultBackupMaxBlockSize():
    return 10 * 1024 * 1024

def MinimumBandwidthInLimitKBSec():
    return 10

def MinimumBandwidthOutLimitKBSec():
    return 10

def CentralKillNotAliveUserAfter():
    return 60 #kill user after X days

def FireHireMinimumDelay():
    return 60 * 15 # do not want to fire suppliers too often, 15 minutes interval 

def BackupDBSynchronizeDelay():
    # TEST
    # return 5
    return 60 * 5 # save backup index database no more than one time per 5 min

def MaxDeletedBackupIDsToKeep():
    return 100 # how many deleted backupIDs do we want to hold on to in backup db?

def DefaultBitCoinCostPerDHNCredit():
    # let's calculate this.:
    # 1 DHN ~ 1 US $ - this is our default exchange rate
    # 1 BTC ~ 130 $ US on 26 Sep 2013 and still going up 
    # so 1 DHN is about 0.00769 BTC if we want to keep DHN to $ US exchange rate
    # let's decrease it 10 times or even more so people can have flexible market
    # and let's trade at least 1 DHN at once, lower values seems very small
    # another one thing is that BitCoins have minimum transaction amount: 0.00005430 BTC
    return 0.0005 

#---STRINGS----------------------------------------------------------------------------

def ApplicationName():
    return 'DataHaven.NET'

def CentralID():
    return 'http://identity.datahaven.net/dhncentral.xml'

def MoneyServerID():
    # TODO should be something like dhnpayments
    return 'http://identity.datahaven.net/offshore.xml'

def MarketServerID():
    # TODO dhnmarket seems to be fine
    # return 'http://identity.datahaven.net/wwww.xml'
    # return 'http://identity.datahaven.net/veselin-ubuntu-1024.xml'
    return 'http://identity.datahaven.net/dhnmarket.xml'

def MarketPlaceURL():
    return 'http://datahaven.net:%d/' % MarketServerWebPort()

def MarketServerBitCoinAddress():
    return "1467zVrKrexBQTM3uyQCZCgAzKa5AFBcm3" # veselin Dell
    return "1QAhYF3n1vvpZRh6nxkicERtmiHVL5tJbP" # caesarion.ru

def ListFilesFormat():         #  argument to ListFiles command to say format to return the data in
    return "Compressed"        #  "Text", "Compressed" 

def DefaultEccMapName():
    return 'ecc/4x4'

def HMAC_key_word():
    return 'Vince+Veselin+Derek=BigMoneyAndSuccess'

def DefaultRepo(): 
    return 'devel'

def UpdateLocationURL(repo=DefaultRepo()):
    if repo == 'devel':
        return 'http://datahaven.net/repo/devel/'
    elif repo == 'stable':
        return 'http://datahaven.net/repo/stable/'
    else: 
        return 'http://identity.datahaven.net/downloads/'

def CurrentVersionDigestsFilename():
    return 'version.txt'

def FilesDigestsFilename():
    return 'info.txt'

def UpdateFolder():
    return 'windows/'

def LegalUsernameChars():
    return set("abcdefghijklmnopqrstuvwxyz0123456789-_")

def NotRealUsers():
    return ('http://identity.datahaven.net/cate2gpa.xml',
            'http://identity.datahaven.net/dcdemo.xml',
            'http://identity.datahaven.net/dctest23.xml',
            'http://identity.datahaven.net/derekcate.xml',
            'http://identity.datahaven.net/derekcatewin.xml',
            'http://identity.datahaven.net/dhncentral.xml',
            'http://identity.datahaven.net/ethan.xml',
            'http://identity.datahaven.net/ekaterina.xml',
            'http://identity.datahaven.net/gazebo.xml',
            'http://identity.datahaven.net/gazebo4.xml',
            'http://identity.datahaven.net/guesthouse.xml',
            'http://identity.datahaven.net/hcate2.xml',
            'http://identity.datahaven.net/mediapc2.xml',
            'http://identity.datahaven.net/offshore.xml',
            'http://identity.datahaven.net/terynlinux.xml',
            'http://identity.datahaven.net/terynvista.xml',
            'http://identity.datahaven.net/veseleeypc.xml',
            'http://identity.datahaven.net/veselin-macos.xml',
            'http://identity.datahaven.net/veselin.xml',
            'http://identity.datahaven.net/veselinux.xml',
            'http://identity.datahaven.net/veselonflash.xml',
            'http://identity.datahaven.net/vinceworkstation.xml',
            'http://identity.datahaven.net/vista3.xml',
            'http://identity.datahaven.net/workoffshoreai.xml',)

#---DIRECTORY PATHS----------------------------------------------------------------------------

def BaseDirDefault():
    return os.path.join(os.path.expanduser('~'), '.datahaven')

# PREPRO - all of the paths below should be under some base directory
def BaseDirLinux():
    new_path = os.path.join(os.path.expanduser('~'), '.datahaven')
    if os.path.isdir(new_path):
        return new_path
    old_path = os.path.join(os.path.expanduser('~'), 'datahavennet')
    if os.path.isdir(old_path):
        return old_path
    return new_path

def BaseDirWindows():
    if not dhnio.Windows():
        return BaseDirDefault()
    #return os.path.join(os.path.expanduser('~'), 'Application Data', 'DataHavenNet')
    default_path = os.path.join(os.path.expanduser('~'), 'Application Data')
    return os.path.join(os.environ.get('APPDATA', default_path), 'DataHaven.NET')

def BaseDirMac():
    return os.path.join(os.path.expanduser('~'), '.datahaven')

def DefaultBaseDir():
    if dhnio.Windows():
        return BaseDirWindows()
    elif dhnio.Linux():
        return BaseDirLinux()
    elif dhnio.Mac():
        return BaseDirMac()
    return BaseDirDefault()

def BaseDir():
    global _BaseDirPath
    init()
    return _BaseDirPath

def BaseDirPathFileName():
    return os.path.join(dhnio.getExecutableDir(), 'basedir.txt')

_NeighbourBaseDirPath = ''
def NeighbourBaseDir():
    global _NeighbourBaseDirPath
    if _NeighbourBaseDirPath == '':
        _NeighbourBaseDirPath = str(os.path.abspath(os.path.join(
            dhnio.getExecutableDir(),
            '..',
            '.datahaven')))
    return _NeighbourBaseDirPath

def RestoreDir():
    return os.path.expanduser('~')
    #return BaseDir()

def WindowsBinDir():
    return os.path.join(BaseDir(), 'bin')

def RaidDir():
    return os.path.join(BaseDir(), "raiddir")

def MetaDataDir():
    return os.path.join(BaseDir(), "metadata")

def TempDir():
    return os.path.join(BaseDir(), "temp")

def IdentityCacheDir():
    return os.path.join(BaseDir(), "identitycache")

def BackupsDBDir():
    return os.path.join(BaseDir(), 'backups')

def Q2QDir():
    return os.path.join(BaseDir(), 'q2qcerts')

def LogsDir():
    return os.path.join(BaseDir(), 'logs')

def SuppliersDir():
    return os.path.join(BaseDir(), 'suppliers')

def BandwidthInDir():
    return os.path.join(BaseDir(),"bandin")

def BandwidthOutDir():
    return os.path.join(BaseDir(),"bandout")

def RatingsDir():
    return os.path.join(BaseDir(), 'ratings')

def CSpaceDir():
    return os.path.join(BaseDir(), 'cspace')

def CSpaceSettingsDir():
    if dhnio.Windows():
        return os.path.join(CSpaceDir(), '_CSpace', 'Settings')
    else:
        return os.path.join(CSpaceDir(), '.CSpace', 'Settings')

def CSpaceProfilesDir():
    if dhnio.Windows():
        return os.path.join(CSpaceDir(), '_CSpaceProfiles')
    else:
        return os.path.join(CSpaceDir(), '.CSpaceProfiles')

#---FILES PATHS--------------------------------------------------------------------------- 

def KeyFileName():
    return os.path.join(MetaDataDir(), "mykeyfile")

def KeyFileNameLocation():
    return KeyFileName() + '_location'

def SupplierIDsFilename():
    # IDs for places that store data for us
    return os.path.join(MetaDataDir(), "supplierids")

def CustomerIDsFilename():
    # IDs for places we store data for
    return os.path.join(MetaDataDir(), "customerids")

def CorrespondentIDsFilename():
    # people we get messages from
    return os.path.join(MetaDataDir(), "correspondentids")

def LocalIdentityFilename():
    return os.path.join(MetaDataDir(), "localidentity")

def LocalIPFilename():
    # file contains string like 192.168.100.33
    return os.path.join(MetaDataDir(), "localip")

def ExternalIPFilename():
    # file contains string like 207.42.133.2
    return os.path.join(MetaDataDir(), "externalip")

def DefaultTransportOrderFilename():
    return os.path.join(MetaDataDir(), "torder")

def UserNameFilename():
    # file contains something like "guesthouse"
    return os.path.join(MetaDataDir(), "username")

def UserConfigFilename():
    return os.path.join(MetaDataDir(), "userconfig")

def GUIOptionsFilename():
    return os.path.join(MetaDataDir(), "guioptions")

def UpdateSheduleFilename():
    return os.path.join(MetaDataDir(), "updateshedule")

def LocalPortFilename():
    return os.path.join(MetaDataDir(), 'localport')

def BackupInfoFileNameOld():
    return "backup_info.xml"

def BackupInfoFileName():
    # return "backup_info.xml"
    return 'backup_db'

def BackupInfoEncryptedFileName():
    return 'backup_info'

def BackupIndexFileName():
    return 'index'

def BackupInfoFileFullPath():
    return os.path.join(MetaDataDir(), BackupInfoFileName())

def BackupInfoFileFullPathOld():
    return os.path.join(MetaDataDir(), BackupInfoFileNameOld())

def BackupIndexFilePath():
    return os.path.join(MetaDataDir(), BackupIndexFileName()) 

def InstalledDateFileName():
    return os.path.join(MetaDataDir(), 'installed')

def SupplierPath(idurl, filename=None):
    if filename is not None:
        return os.path.join(SuppliersDir(), nameurl.UrlFilename(idurl), filename)
    return os.path.join(SuppliersDir(), nameurl.UrlFilename(idurl))

def SupplierListFilesFilename(idurl):
    return os.path.join(SupplierPath(idurl), 'listfiles')

def TransportLogFile():
    return (os.path.join(LogsDir(), 'transport.log'))

def DebugLogFile():
    return (os.path.join(LogsDir(), 'debug.log'))

def LocalTesterLogFilename():
    return os.path.join(LogsDir(), 'dhntester.log')

def MiniupnpcLogFilename():
    return os.path.join(LogsDir(), 'miniupnpc.log')

def MainLogFilename():
    return os.path.join(LogsDir(), 'dhn')

def TwistedLogFilename():
    return os.path.join(LogsDir(), 'twisted.log')

def UpdateLogFilename():
    return os.path.join(LogsDir(), 'dhnupdate.log')

def RunUpdateLogFilename():
    return os.path.join(LogsDir(), 'runupdate.log')

def SignerLogFilename():
    return os.path.join(LogsDir(), 'dhnsigner.log')

def RunupnpcLogFilename():
    return os.path.join(LogsDir(), 'runupnpc.log')

def FireHireLogFilename():
    return os.path.join(LogsDir(), 'fire_hire.log')

def CSpaceLogFilename():
    return os.path.join(LogsDir(), 'cspace.log')

def AutomatsLog():
    return os.path.join(LogsDir(), 'automats.log')

def RepoFile():
    return os.path.join(MetaDataDir(), 'repo')

def VersionFile():
    return os.path.join(MetaDataDir(), 'version')

def InfoFile():
    return os.path.join(MetaDataDir(), 'info')

def RevisionNumberFile():
    return os.path.join(dhnio.getExecutableDir(), 'revnum.txt')

def CustomersSpaceFile():
    return os.path.join(MetaDataDir(), 'space')

def BalanceFile():
    return os.path.join(MetaDataDir(), 'balance')

def CertificateFiles():
    return [    os.path.join(MetaDataDir(), 'dhn.cer'),
                os.path.join('.', 'dhn.cer'),
                os.path.join(dhnio.getExecutableDir() ,'dhn.cer'),]

def CSpaceSavedProfileFile():
    return os.path.join(CSpaceSettingsDir(), 'SavedProfile') 

def CSpaceSavedPasswordFile():
    return os.path.join(CSpaceSettingsDir(), 'SavedPassword') 

def CSpaceRememberKeyFile():
    return os.path.join(CSpaceSettingsDir(), 'RememberKey') 

#---BINARY FILES PATHS--------------------------------------------------------------------------- 

def WindowsStarterFileName():
    return 'dhnstarter.exe'

def WindowsStarterFileURL(repo=DefaultRepo()):
    return UpdateLocationURL(repo) + 'windows/' + WindowsStarterFileName()

def getAutorunFilename():
    if dhnio.Windows() and dhnio.isFrozen():
        path = os.path.join(dhnio.getExecutableDir(), WindowsStarterFileName())
        if not os.path.isfile(path):
            path = dhnio.getExecutableFilename()
    else:
        path = dhnio.getExecutableFilename()
    return path

def getIconLaunchFilename():
    #return os.path.join(dhnio.getExecutableDir(), WindowsStarterFileName())
    return os.path.join(dhnio.getExecutableDir(), 'dhnmain.exe')

def getIconLinkFilename():
    return 'Data Haven .NET.lnk'

def IconFilename():
    return 'dhnicon.ico'

def IconsFolderPath():
    return os.path.join(dhnio.getExecutableDir(), 'icons')

def FontsFolderPath():
    return os.path.join(dhnio.getExecutableDir(), 'fonts')

def FontImageFile():
    return os.path.join(FontsFolderPath(), 'Arial_Narrow.ttf')

#---MERCHANT ID AND LINK----------------------------------------------------------------------------

def MerchantID():
    return 'AXA_DH_02666084001'
##    return 'AXA_DH_TESTKEY1'

def MerchantURL():
    return 'https://merchants.4csonline.com/TranSvcs/tp.aspx'
##    return 'https://merchants.4csonline.com/DevTranSvcs/tp.aspx'

#---SERVER HOST NAMES----------------------------------------------------------------------------

def IdentityServerName():
    return "identity.datahaven.net"

def DefaultIdentityServer():
    return "identity.datahaven.net"

def DefaultQ2QServer():
    # return 'work.offshore.ai'
    return 'datahaven.net'

def MoneyServerName():
##    return 'localhost'
##    return '67.207.147.183' #central
##    return "central.net"
##    return "central.datahaven.net"
##    return "209.59.119.34" #offshore.ai
#    return 'datahaven.net'
    return "offshore.ai"

def UpdateServerName():
    return 'localhost'

def CentralStatsURL():
#    return 'http://work.offshore.ai/~veselin/' - #that's old location
    return 'http://identity.datahaven.net/statistics/'

#---PORT NUMBERS----------------------------------------------------------------------------

def DefaultSSHPort():
    return 5022

# This should be same for all identity servers everywhere
def IdentityServerPort():
    return 7773

def IdentityWebPort():
    return 80

def MarketServerWebPort():
    return 8085

def MoneyServerPort():
    return 9898

def DefaultTCPPort():
    return 7771

def DefaultUDPPort():
    return 0

def UpdateServerPort():
    return 8301

def DefaultHTTPPort():
    return 9786

def DefaultWebLogPort():
    return 9999

def DefaultWebTrafficPort():
    return 9997

#---USER FOLDERS----------------------------------------------------------------------------

##def CustomersDataDir():
##    return uconfig("other.CustomerDataDirectory").strip()

##def MessagesDir():
##    return uconfig("other.MessagesDirectory").strip()
##
##def ReceiptsDir():
##    return uconfig("other.ReceiptsDirectory").strip()

def getCustomersFilesDir():
    return uconfig('folder.folder-customers').strip()

def getCustomerFilesDir(idurl):
    return os.path.join(getCustomersFilesDir(), nameurl.UrlFilename(idurl))

def getLocalBackupsDir():
    return uconfig('folder.folder-backups').strip()

def getRestoreDir():
    return uconfig('folder.folder-restore').strip()

def getMessagesDir():
    return uconfig('folder.folder-messages').strip()

def getReceiptsDir():
    return uconfig('folder.folder-receipts').strip()

def getTempDir():
    #if value is empty value - let's use default (system) temporary folder
    #return uconfig('folder.folder-temp').strip()
    return TempDir()

#---PROXY SERVER OPTIONS---------------------------------------------------------------------------

def enableProxy(enable=None):
    if enable is None:
        return uconfig('network.network-proxy.network-proxy-enable').lower() == 'true'
    uconfig().set('network.network-proxy.network-proxy-enable', str(enable))
    uconfig().update()

def getProxyHost():
    return uconfig('network.network-proxy.network-proxy-host').strip()

def getProxyPort():
    return uconfig('network.network-proxy.network-proxy-port').strip()

def setProxySettings(d):
    if d.has_key('host'):
        uconfig().set('network.network-proxy.network-proxy-host', str(d.get('host','')))
    if d.has_key('port'):
        uconfig().set('network.network-proxy.network-proxy-port', str(d.get('port','')))
    if d.has_key('username'):
        uconfig().set('network.network-proxy.network-proxy-username', str(d.get('username','')))
    if d.has_key('password'):
        uconfig().set('network.network-proxy.network-proxy-password', str(d.get('password','')))
    if d.has_key('ssl'):
        uconfig().set('network.network-proxy.network-proxy-ssl', str(d.get('ssl','False')))
    uconfig().update()

def getProxySettingsDict():
    return {
         'host':        uconfig('network.network-proxy.network-proxy-host').strip(),
         'port':        uconfig('network.network-proxy.network-proxy-port').strip(),
         'username':    uconfig('network.network-proxy.network-proxy-username').strip(),
         'password':    uconfig('network.network-proxy.network-proxy-password').strip(),
         'ssl':         uconfig('network.network-proxy.network-proxy-ssl').strip(), }

def update_proxy_settings():
    import dhnnet
    dhnnet.init()
    if enableProxy():
        if getProxyHost() == '' or getProxyPort() == '':
            d = dhnnet.detect_proxy_settings()
            dhnnet.set_proxy_settings(d)
            setProxySettings(d)
            enableProxy(d.get('host', '') != '')
            dhnio.Dprint(2, 'settings.update_proxy_settings UPDATED!!!')
        else:
            dhnnet.set_proxy_settings(getProxySettingsDict())
        dhnio.Dprint(4, 'settings.update_proxy_settings')
        dhnio.Dprint(4, 'HOST:      ' + dhnnet.get_proxy_host())
        dhnio.Dprint(4, 'PORT:      ' + str(dhnnet.get_proxy_port()))
        dhnio.Dprint(4, 'USERNAME:  ' + dhnnet.get_proxy_username())
        dhnio.Dprint(4, 'PASSWORD:  ' + ('*' * len(dhnnet.get_proxy_password())))
        dhnio.Dprint(4, 'SSL:       ' + dhnnet.get_proxy_ssl())


#---OTHER USER CONFIGURATIONS---------------------------------------------------------------------------

def getBandOutLimit(): # in kilo bytes per second
    try:
        return int(uconfig('network.network-send-limit'))
    except:
        return 0

def getBandInLimit(): # in kilo bytes per second
    try:
        return int(uconfig('network.network-receive-limit'))
    except:
        return 0

def FireInactiveSupplierIntervalHours():  # after a supplier hasn't been heard from in
    return uconfig('other.FireInactiveSupplierIntervalHours')

def ShowBarcode():  # do we want to show barcode stuff?  At the moment only for debuggers
    return uconfig('other.ShowBarcode')

def getTransportPort(proto):
    if proto == 'tcp':
        return getTCPPort()
    if proto == 'udp':
        return getUDPPort()
    if proto == 'ssh':
        return getSSHPort()
    if proto == 'http':
        return getHTTPPort()

def getTCPPort():
    return uconfig("transport.transport-tcp.transport-tcp-port")

def setTCPPort(port):
    uconfig().set("transport.transport-tcp.transport-tcp-port", str(port))
    uconfig().update()

def enableTCP(enable=None):
    if enable is None:
        return uconfig('transport.transport-tcp.transport-tcp-enable').lower() == 'true'
    uconfig().set('transport.transport-tcp.transport-tcp-enable', str(enable))
    uconfig().update()

def enableTCPsending(enable=None):
    if enable is None:
        return uconfig('transport.transport-tcp.transport-tcp-sending-enable').lower() == 'true'
    uconfig().set('transport.transport-tcp.transport-tcp-sending-enable', str(enable))
    uconfig().update()
    
def enableTCPreceiving(enable=None):
    if enable is None:
        return uconfig('transport.transport-tcp.transport-tcp-receiving-enable').lower() == 'true'
    uconfig().set('transport.transport-tcp.transport-tcp-receiving-enable', str(enable))
    uconfig().update()

def getUDPPort():
    return uconfig("transport.transport-udp.transport-udp-port")

def setUDPPort(port):
    uconfig().set("transport.transport-udp.transport-udp-port", str(port))
    uconfig().update()

def enableUDP(enable=None):
    if enable is None:
        return uconfig('transport.transport-udp.transport-udp-enable').lower() == 'true'
    uconfig().set('transport.transport-udp.transport-udp-enable', str(enable))
    uconfig().update()

def enableUDPsending(enable=None):
    if enable is None:
        return uconfig('transport.transport-udp.transport-udp-sending-enable').lower() == 'true'
    uconfig().set('transport.transport-udp.transport-udp-sending-enable', str(enable))
    uconfig().update()
    
def enableUDPreceiving(enable=None):
    if enable is None:
        return uconfig('transport.transport-udp.transport-udp-receiving-enable').lower() == 'true'
    uconfig().set('transport.transport-udp.transport-udp-receiving-enable', str(enable))
    uconfig().update()

def getSSHPort():
    return uconfig("transport.transport-ssh.transport-ssh-port")

def setSSHPort(port):
    uconfig().set("transport.transport-ssh.transport-ssh-port", str(port))
    uconfig().update()

def enableSSH(enable=None):
    if enable is None:
        return uconfig('transport.transport-ssh.transport-ssh-enable').lower() == 'true'
    uconfig().set('transport.transport-ssh.transport-ssh-enable', str(enable))
    uconfig().update()

def getQ2Qhost():
    return uconfig("transport.transport-q2q.transport-q2q-host")

def setQ2Qhost(host):
    uconfig().set("transport.transport-q2q.transport-q2q-host", host)
    uconfig().update()

def getQ2Qusername():
    return uconfig("transport.transport-q2q.transport-q2q-username")

def setQ2Qusername(username):
    uconfig().set("transport.transport-q2q.transport-q2q-username", username)
    uconfig().update()

def getQ2Qpassword():
    return uconfig("transport.transport-q2q.transport-q2q-password")

def setQ2Qpassword(password):
    uconfig().set("transport.transport-q2q.transport-q2q-password", password)
    uconfig().update()

def getQ2Quserathost():
    return getQ2Qusername()+'@'+getQ2Qhost()

def setQ2Quserathost(userAThost):
    username, host = userAThost.split('@')
    setQ2Qhost(host)
    setQ2Qusername(username)

def enableQ2Q(enable=None):
    if enable is None:
        return uconfig('transport.transport-q2q.transport-q2q-enable').lower() == 'true'
    uconfig().set('transport.transport-q2q.transport-q2q-enable', str(enable))
    uconfig().update()

def getHTTPPort():
    return uconfig('transport.transport-http.transport-http-server-port')

def setHTTPPort(port):
    uconfig().set("transport.transport-http.transport-http-port", str(port))
    uconfig().update()

def getHTTPDelay():
    return dhnmath.toInt(uconfig('transport.transport-http.transport-http-ping-timeout'), DefaultHTTPDelay())

def enableHTTP(enable=None):
    if enable is None:
        return uconfig('transport.transport-http.transport-http-enable').lower() == 'true'
    uconfig().set('transport.transport-http.transport-http-enable', str(enable))
    uconfig().update()

def enableHTTPServer(enable=None):
    if enable is None:
        return uconfig('transport.transport-http.transport-http-server-enable').lower() == 'true'
    uconfig().set('transport.transport-http.transport-http-server-enable', str(enable))
    uconfig().update()

def enableCSpace(enable=None):
    if enable is None:
        return uconfig('transport.transport-cspace.transport-cspace-enable').lower() == 'true'
    uconfig().set('transport.transport-cspace.transport-cspace-enable', str(enable))
    uconfig().update()

def enableCSPACEsending(enable=None):
    if enable is None:
        return uconfig('transport.transport-cspace.transport-cspace-sending-enable').lower() == 'true'
    uconfig().set('transport.transport-cspace.transport-cspace-sending-enable', str(enable))
    uconfig().update()
    
def enableCSPACEreceiving(enable=None):
    if enable is None:
        return uconfig('transport.transport-cspace.transport-cspace-receiving-enable').lower() == 'true'
    uconfig().set('transport.transport-cspace.transport-cspace-receiving-enable', str(enable))
    uconfig().update()

def getCSpaceKeyID():
    return uconfig('transport.transport-cspace.transport-cspace-key-id')

def setCSpaceKeyID(key_id):
    uconfig().set('transport.transport-cspace.transport-cspace-key-id', key_id)
    uconfig().update()

def setCSpaceUserName(username):
    uconfig().set('transport.transport-cspace.transport-cspace-username', username)
    uconfig().update()
    
def setCSpacePassword(password):
    uconfig().set('transport.transport-cspace.transport-cspace-password', password)
    uconfig().update()

def SendTimeOutEmail():
    return uconfig("other.emailSendTimeout")

def DefaultReceiveTimeOutEmail():
    return 120                # seconds receive timeout for email

def DefaultHTTPDelay():
    return 5

def ReceiveTimeOutEmail():
    return uconfig("other.emailReceiveTimeout")

def EmailPollingTime():
    return 30

def getEmailAddress():
    return uconfig('transport.transport-email.transport-email-address')

def getPOPHost():
    return uconfig('transport.transport-email.transport-email-pop-host')

def getPOPPort():
    return uconfig('transport.transport-email.transport-email-pop-port')

def getPOPUser():
    return uconfig('transport.transport-email.transport-email-pop-username')

def getPOPPass():
    return uconfig('transport.transport-email.transport-email-pop-password')

def getPOPSSL():
    return uconfig('transport.transport-email.transport-email-pop-ssl')

def getSMTPHost():
    return uconfig('transport.transport-email.transport-email-smtp-host')

def getSMTPPort():
    return uconfig('transport.transport-email.transport-email-smtp-port')

def getSMTPUser():
    return uconfig('transport.transport-email.transport-email-smtp-username')

def getSMTPPass():
    return uconfig('transport.transport-email.transport-email-smtp-password')

def getSMTPSSL():
    return uconfig('transport.transport-email.transport-email-smtp-ssl')

def getSMTPNeedLogin():
    return uconfig('transport.transport-email.transport-email-smtp-need-login').lower() == 'true'

def enableEMAIL(enable=None):
    if enable is None:
        return uconfig('transport.transport-email.transport-email-enable').lower() == 'true'
    uconfig().set('transport.transport-email.transport-email-enable', str(enable))
    uconfig().update()

def enableSKYPE(enable=None):
    if enable is None:
        return uconfig('transport.transport-skype.transport-skype-enable').lower() == 'true'
    uconfig().set('transport.transport-skype.transport-skype-enable', str(enable))
    uconfig().update()

def enableTransport(proto, enable=None):
    key = 'transport.transport-%s.transport-%s-enable' % (proto, proto)
    if uconfig(key) is None:
        return False
    if enable is None:
        return uconfig(key).lower() == 'true'
    uconfig().set(key, str(enable))
    uconfig().update()

def transportIsEnabled(proto):
#    if proto == 'http':
#        return enableHTTPServer() or enableHTTP()
    return enableTransport(proto)

def transportIsInstalled(proto):
#    if proto == 'q2q':
#        return getQ2Qusername().strip() != '' and getQ2Qhost().strip() != ''
#    if proto == 'email':
#        return getEmailAddress().strip() != ''
    if proto == 'cspace':
        return getCSpaceKeyID().strip() != ''
    return True

def transportReceivingIsEnabled(proto):
    key = 'transport.transport-%s.transport-%s-receiving-enable' % (proto, proto)
    if uconfig(key) is None:
        return False
    return uconfig(key).lower() == 'true'

def transportSendingIsEnabled(proto):
    key = 'transport.transport-%s.transport-%s-sending-enable' % (proto, proto)
    if uconfig(key) is None:
        return False
    return uconfig(key).lower() == 'true'

#debug level info
def getDebugLevelStr(): # this is just for checking if it is set, the int() would throw an error
#    return uconfig("other.DebugLevel")
    return uconfig("logs.debug-level")

def getDebugLevel():
    try:
#        res = int(uconfig("other.DebugLevel"))
        res = int(getDebugLevelStr())
    except:
        res = dhnio.DebugLevel
    return res

def setDebugLevel(level):
    uconfig().set("logs.debug-level", str(level))
    uconfig().update()

def enableWebStream(enable=None):
    if enable is None:
        return uconfig('logs.stream-enable').lower() == 'true'
    uconfig().set('logs.stream-enable', str(enable))
    uconfig().update()

def enableWebTraffic(enable=None):
    if enable is None:
        return uconfig('logs.traffic-enable').lower() == 'true'
    uconfig().set('logs.traffic-enable', str(enable))
    uconfig().update()

def getWebStreamPort():
    try:
        return int(uconfig('logs.stream-port'))
    except:
        return DefaultWebLogPort()

def getWebTrafficPort():
    try:
        return int(uconfig('logs.traffic-port'))
    except:
        return DefaultWebTrafficPort()
    
def enableMemoryProfile(enable=None):
    if enable is None:
        return uconfig('logs.memprofile-enable').lower() == 'true'
    uconfig().set('logs.memprofile-enable', str(enable))
    uconfig().update()

def getDozerStr():
    return uconfig('other.Dozer')

def getDoBackupMonitor():
    return uconfig('other.DoBackupMonitor')

def getECC():
    snum = getCentralNumSuppliers()
    if snum < 0:
        return DefaultEccMapName()
    ecc = eccmap.GetEccMapName(snum)
    if isValidECC(ecc):
        return ecc
    else:
        return DefaultEccMapName()

def getECCSuppliersNumbers():
    return [2, 4, 7, 13]
    # return eccmap.SuppliersNumbers()

def getCentralNumSuppliers():
    try:
        return int(uconfig('central-settings.desired-suppliers'))
    except:
        return -1

def getCentralMegabytesNeeded():
    return uconfig('central-settings.needed-megabytes')

def getCentralMegabytesDonated():
    return uconfig('central-settings.shared-megabytes')

def getEmergencyEmail():
    return uconfig('emergency.emergency-email')

def getEmergencyPhone():
    return uconfig('emergency.emergency-phone')

def getEmergencyFax():
    return uconfig('emergency.emergency-fax')

def getEmergencyOther():
    return uconfig('emergency.emergency-text')

def getEmergency(method):
    if method not in getEmergencyMethods():
        return ''
    return uconfig('emergency.emergency-' + method)

def getEmergencyFirstMethod():
    return uconfig('emergency.emergency-first')

def getEmergencySecondMethod():
    return uconfig('emergency.emergency-second')

def getEmergencyMethods():
    return (
        'email',
        'phone',
        'fax',
        'other',)

def getUpdatesMode():
    return uconfig('updates.updates-mode')

def getUpdatesModeValues():
    return  (
        'install automatically',
#        'ask before install',
        'only notify',
        'turn off updates', )

def getUpdatesSheduleData():
    return uconfig('updates.updates-shedule')

def setUpdatesSheduleData(raw_shedule):
    uconfig().set('updates.updates-shedule', raw_shedule)
    uconfig().update()

def getGeneralBackupsToKeep():
    try:
        return int(uconfig('general.general-backups'))
    except:
        return 2

def getGeneralLocalBackups():
    return uconfig('general.general-local-backups-enable').lower() == 'true'

def getGeneralWaitSuppliers():
    return uconfig('general.general-wait-suppliers-enable').lower() == 'true'

def getGeneralAutorun():
    return uconfig('general.general-autorun').lower() == 'true'

def getGeneralDisplayMode():
    return uconfig('general.general-display-mode')

def getGeneralDisplayModeValues():
    return ('iconify window', 'normal window', 'maximized window',)

##def getGeneralShowProgress():
##    return uconfig('general.general-show-progress').lower() == 'true'

def getGeneralDesktopShortcut():
    return uconfig('general.general-desktop-shortcut').lower() == 'true'

def getGeneralStartMenuShortcut():
    return uconfig('general.general-start-menu-shortcut').lower() == 'true'

def getBackupBlockSize():
    global _BackupBlockSize
    if _BackupBlockSize is None:
        try:
            _BackupBlockSize = int(uconfig('backup.backup-block-size'))
        except:
            _BackupBlockSize = DefaultBackupBlockSize()
    return _BackupBlockSize

def getBackupMaxBlockSize():
    global _BackupMaxBlockSize
    if _BackupMaxBlockSize is None:
        try:
            _BackupMaxBlockSize = int(uconfig('backup.backup-max-block-size'))
        except:
            _BackupMaxBlockSize = DefaultBackupMaxBlockSize()
    return _BackupMaxBlockSize

def setBackupBlockSize(block_size):
    global _BackupBlockSize
    _BackupBlockSize = int(block_size)

def setBackupMaxBlockSize(block_size):
    global _BackupMaxBlockSize
    _BackupMaxBlockSize = int(block_size)
     
def getPrivateKeySize():
    try:
        return int(uconfig('backup.private-key-size'))
    except:
        return DefaultPrivateKeySize()
    
def setPrivateKeySize(pksize):
    uconfig().set('backup.private-key-size', str(pksize))
    uconfig().update()
     
def getSystemUserDataPathList():
    return uconfig().get_childs('system.system-user-data-paths')

def enableUPNP(enable=None):
    if enable is None:
        return uconfig('other.upnp-enabled').lower() == 'true'
    uconfig().set('other.upnp-enabled', str(enable))
    uconfig().update()

def getUPNPatStartup():
    return uconfig('other.upnp-at-startup').lower() == 'true'

def setUPNPatStartup(enable):
    uconfig().set('other.upnp-at-startup', str(enable))
    uconfig().update()

def isValidECC(ecc):
    if ecc in eccmap.EccMapNames():
        return True
    else:
        return False

def getBitCoinServerHost():
    return uconfig('other.bitcoin.bitcoin-host')

def getBitCoinServerPort():
    return uconfig('other.bitcoin.bitcoin-port')

def getBitCoinServerUserName():
    return uconfig('other.bitcoin.bitcoin-username')

def getBitCoinServerPassword():
    return uconfig('other.bitcoin.bitcoin-password')

def getBitCoinServerIsLocal():
    return uconfig('other.bitcoin.bitcoin-server-is-local').lower() == 'true' 

def getBitCoinServerConfigFilename():
    return uconfig('other.bitcoin.bitcoin-config-filename')

#---INITIALIZE BASE DIR----------------------------------------------------------------------------

def RenameBaseDir(newdir):
    global _BaseDirPath
    olddir = _BaseDirPath
    try:
#        os.renames(_BaseDirPath, newdir) # - this not fit for us.
        import shutil
        shutil.copytree(olddir, newdir)
    except:
        dhnio.DprintException()
        return False
    _BaseDirPath = newdir
    dhnio.Dprint(2, 'settings.RenameBaseDir  directory was copied,  BaseDir='+BaseDir())
    pathfilename = BaseDirPathFileName()
    dhnio.WriteFile(pathfilename, _BaseDirPath)
    dhnio.Dprint(4, 'settings.RenameBaseDir  BaseDir path was saved to ' + pathfilename)
    logfilename = dhnio.LogFileName
    dhnio.CloseLogFile()
    try:
        dhnio.rmdir_recursive(olddir, True)
        dhnio.Dprint(4, 'settings.RenameBaseDir  old directory was removed: ' + olddir)
    except:
        dhnio.DprintException()
    dhnio.OpenLogFile(logfilename, True)
    return True

def _initBaseDir(base_dir=None):
    global _BaseDirPath
    
    # if we already know the place - we are done
    if base_dir is not None:
        _BaseDirPath = base_dir
        if not os.path.exists(_BaseDirPath):
            dhnio._dirs_make(_BaseDirPath)
        return

    # if we have a file 'basedir.txt' in current folder - take the place from there
    if os.path.isfile(BaseDirPathFileName()):
        path = dhnio.ReadBinaryFile(BaseDirPathFileName())
        if os.path.isdir(path):
            _BaseDirPath = path
            if not os.path.exists(_BaseDirPath):
                dhnio._dirs_make(_BaseDirPath)
            return

    # get the default place for thet machine
    default_path = DefaultBaseDir()

    # we can use folder ".datahaven" placed on the same level with binary folder:
    # /..
    #   /.datahaven - data files
    #   /datahaven  - binary files
    path1 = str(os.path.abspath(os.path.join(dhnio.getExecutableDir(), '..', '.datahaven')))
    # and default path will have lower priority
    path2 = default_path
    
    # if default path exists - use it
    if os.path.isdir(path2):
        _BaseDirPath = path2
    # but .datahaven on same level will have bigger priority
    if os.path.isdir(path1):
        _BaseDirPath = path1

    # if we did not found "metadata" subfolder - use default path, new copy of DHN
    if not os.path.isdir(MetaDataDir()):
        _BaseDirPath = path2
        if not os.path.exists(_BaseDirPath):
            dhnio._dirs_make(_BaseDirPath)
        return
    
    # if we did not found our key - use default path, new copy of DHN
    if not os.access(KeyFileName(), os.R_OK) or not os.access(KeyFileNameLocation(), os.R_OK):
        _BaseDirPath = path2
        if not os.path.exists(_BaseDirPath):
            dhnio._dirs_make(_BaseDirPath)
        return
    
    # if we did not found our identity - use default path, new copy of DHN
    if not os.access(LocalIdentityFilename(), os.R_OK):
        _BaseDirPath = path2
        if not os.path.exists(_BaseDirPath):
            dhnio._dirs_make(_BaseDirPath)
        return

    # if we did not found our config - use default path, new copy of DHN
    if not os.access(UserConfigFilename(), os.R_OK):
        _BaseDirPath = path2
        if not os.path.exists(_BaseDirPath):
            dhnio._dirs_make(_BaseDirPath)
        return

    # if we did not found our suppliers - use default path, new copy of DHN
    if not os.access(SupplierIDsFilename(), os.R_OK):
        _BaseDirPath = path2
        if not os.path.exists(_BaseDirPath):
            dhnio._dirs_make(_BaseDirPath)
        return

    # if we did not found our customers - use default path, new copy of DHN
    if not os.access(CustomerIDsFilename(), os.R_OK):
        _BaseDirPath = path2
        if not os.path.exists(_BaseDirPath):
            dhnio._dirs_make(_BaseDirPath)
        return

#---BE SURE USER SETTINGS IS VALID--------------------------------------------------------------------------- 

def _checkMetaDataDirectory():
    # check that the metadata directory exists
    if not os.path.exists(MetaDataDir()): 
        dhnio.Dprint(8, 'settings.init want to create metadata folder: ' + MetaDataDir())
        #dhnio._dirs_make(MetaDataDir())
        os.makedirs(MetaDataDir())

def _checkSettings():
    if getCentralNumSuppliers() < 0:
        uconfig().set("central-settings.desired-suppliers", str(DefaultDesiredSuppliers()))

    if getCentralMegabytesDonated() == '':
        uconfig().set("central-settings.shared-megabytes", str(DefaultDonatedMb())+' Mb')
    donatedV, donatedS = diskspace.SplitString(getCentralMegabytesDonated())
    if not donatedS:
        uconfig().set("central-settings.shared-megabytes", str(getCentralMegabytesDonated())+' Mb')

    if getCentralMegabytesNeeded() == '':
        uconfig().set("central-settings.needed-megabytes", str(DefaultNeededMb())+' Mb')
    neededV, neededS = diskspace.SplitString(getCentralMegabytesNeeded())
    if not neededS:
        uconfig().set("central-settings.needed-megabytes", str(getCentralMegabytesNeeded())+' Mb')

    if getDebugLevelStr() == "":
        uconfig().set("logs.debug-level", str(defaultDebugLevel()))

    if SendTimeOutEmail() == "":
        uconfig().set("other.emailSendTimeout", str(DefaultSendTimeOutEmail()))

    if ReceiveTimeOutEmail() == "":
        uconfig().set("other.emailReceiveTimeout", str(DefaultReceiveTimeOutEmail()))

    if getTCPPort() == "":
        uconfig().set("transport.transport-tcp.transport-tcp-port", str(DefaultTCPPort()))

    if getUDPPort() == "":
        uconfig().set("transport.transport-udp.transport-udp-port", str(DefaultUDPPort()))

    if getSSHPort() == "":
        uconfig().set("transport.transport-ssh.transport-ssh-port", str(DefaultSSHPort()))

    if getHTTPPort() == "":
        uconfig().set("transport.transport-http.transport-http-port", str(DefaultHTTPPort()))

    if getUpdatesMode().strip() not in getUpdatesModeValues():
        uconfig().set('updates.updates-mode', getUpdatesModeValues()[0])

    if getGeneralDisplayMode().strip() not in getGeneralDisplayModeValues():
        uconfig().set('general.general-display-mode', getGeneralDisplayModeValues()[0])

    if getEmergencyFirstMethod() not in getEmergencyMethods():
        uconfig().set('emergency.emergency-first', getEmergencyMethods()[0])

    if getEmergencySecondMethod() not in getEmergencyMethods():
        uconfig().set('emergency.emergency-second', getEmergencyMethods()[1])

    if getEmergencyFirstMethod() == getEmergencySecondMethod():
        methods = list(getEmergencyMethods())
        methods.remove(getEmergencyFirstMethod())
        uconfig().set('emergency.emergency-second', methods[0])

    uconfig().update()


def _checkStaticDirectories():
#    # check that the base directory exists
#    if not os.path.isdir(BaseDir()):
#        dhnio.Dprint(8, 'settings.init want to create folder: ' + BaseDir())
#        dhnio._dirs_make(BaseDir())
#        if dhnio.Windows(): # ??? !!!
#            _initBaseDir()  # ??? !!!

    if not os.path.exists(TempDir()):
        dhnio.Dprint(6, 'settings.init want to create folder: ' + TempDir())
        os.makedirs(TempDir())

    if not os.path.exists(BandwidthInDir()):
        dhnio.Dprint(6, 'settings.init want to create folder: ' + BandwidthInDir())
        os.makedirs(BandwidthInDir())

    if not os.path.exists(BandwidthOutDir()):
        dhnio.Dprint(6, 'settings.init want to create folder: ' + BandwidthOutDir())
        os.makedirs(BandwidthOutDir())

    if not os.path.exists(LogsDir()):
        dhnio.Dprint(6, 'settings.init want to create folder: ' + LogsDir())
        os.makedirs(LogsDir())

    if not os.path.exists(IdentityCacheDir()):
        dhnio.Dprint(6, 'settings.init want to create folder: ' + IdentityCacheDir())
        os.makedirs(IdentityCacheDir())

    if not os.path.exists(SuppliersDir()):
        dhnio.Dprint(6, 'settings.init want to create folder: ' + SuppliersDir())
        os.makedirs(SuppliersDir())

    if not os.path.exists(RatingsDir()):
        dhnio.Dprint(6, 'settings.init want to create folder: ' + RatingsDir())
        os.makedirs(RatingsDir())

    if not os.path.exists(CSpaceDir()):
        dhnio.Dprint(6, 'settings.init want to create folder: ' + CSpaceDir())
        os.makedirs(CSpaceDir())


def _checkCustomDirectories():
    if getCustomersFilesDir() == '':
        uconfig().set('folder.folder-customers', os.path.join(BaseDir(), "customers"))
    if not os.path.exists(getCustomersFilesDir()):
        dhnio.Dprint(6, 'settings.init want to create folder: ' + getCustomersFilesDir())
        os.makedirs(getCustomersFilesDir())

    if getLocalBackupsDir() == '':
        uconfig().set('folder.folder-backups', os.path.join(BaseDir(), "backups"))
    if not os.path.exists(getLocalBackupsDir()):
        dhnio.Dprint(6, 'settings.init want to create folder: ' + getLocalBackupsDir())
        os.makedirs(getLocalBackupsDir())

    if getMessagesDir() == '':
        uconfig().set('folder.folder-messages', os.path.join(BaseDir(), 'messages'))
    if not os.path.exists(getMessagesDir()):
        dhnio.Dprint(6, 'settings.init want to create folder: ' + getMessagesDir())
        os.makedirs(getMessagesDir())

    if getReceiptsDir() == '':
        uconfig().set('folder.folder-receipts', os.path.join(BaseDir(), 'receipts'))
    if not os.path.exists(getReceiptsDir()):
        dhnio.Dprint(6, 'settings.init want to create folder: ' + getReceiptsDir())
        os.makedirs(getReceiptsDir())

    if getRestoreDir() == '':
        uconfig().set('folder.folder-restore', RestoreDir())

#---INIT----------------------------------------------------------------------------

def _init(base_dir=None):
    dhnio.Dprint(4, 'settings._init')
    _initBaseDir(base_dir)
    dhnio.Dprint(2, 'settings._init data location: ' + BaseDir())
    _checkMetaDataDirectory()
    uconfig()
    _checkStaticDirectories()
    _checkSettings()
    _checkCustomDirectories()

#-------------------------------------------------------------------------------

if __name__ == '__main__':
    init()





