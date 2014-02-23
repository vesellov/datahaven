from cspace.util.settings import LocalSettings, AppSettings
import logging
logger = logging.getLogger('cspace.common')
SETTINGS_VERSION = 3

_localSettings = None
def localSettings(location='CSpace') :
    global _localSettings
    if _localSettings is None :
        _localSettings = LocalSettings(location)
        logger.info('setup local settings in ' + _localSettings.configDir)
    if not _localSettings.configDir.rstrip('//\/').endswith(location):
        return LocalSettings(location)
    return _localSettings

_profileSettings = None
def profileSettings(location='CSpaceProfiles'):
    global _profileSettings
    if _profileSettings is None :
        _profileSettings = LocalSettings(location)
        logger.info('setup profile settings in ' + _profileSettings.configDir)
    if not _profileSettings.configDir.rstrip('//\/').endswith(location):
        return LocalSettings(location)
    return _profileSettings

_appSettings = None
def appSettings() :
    global _appSettings
    if _appSettings is None :
        _appSettings = AppSettings()
        logger.info('setup app settings in ' + _appSettings.configDir)
    return _appSettings

MAX_NAME_LENGTH = 32

def _init() :
    global validUserChars, validServiceChars
    validUserChars = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
    validServiceChars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
_init()

def isValidUserName( name ) :
    if not (0 < len(name) <= MAX_NAME_LENGTH) : return False
    for x in name :
        if not x in validUserChars : return False
    return True

def isValidServiceName( name ) :
    if not (0 < len(name) <= MAX_NAME_LENGTH) : return False
    for x in name :
        if not x in validServiceChars : return False
    return True
