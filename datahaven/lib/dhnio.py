#!/usr/bin/python
#dhnio.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#
# This is for simple routines that do not require importing any of our code

import os
import sys
import time
import imp
import string
import platform
import traceback
import locale
import threading
import glob
import re

#------------------------------------------------------------------------------

# Code will set 1 for most important and 10 for really minor stuff, and 15 for things we don't think we want to see again
# Can set DebugLevel to 0 for no debug messages
DebugLevel = 0
LogLinesCounter = 0
EnableLog = True
RedirectStdOut = False
NoOutput = False
OriginalStdOut = None
StdOutPrev = None
LogFile = None
LogFileName = None
WebStreamFunc = None
ShowTime = True
LifeBeginsTime = 0
tc_using = True
tc_remove_after = True
LocaleInstalled = False
PlatformInfo = None
X11isRunning = None

#------------------------------------------------------------------------------

def init():
    InstallLocale()
    if Linux():
        UnbufferedSTDOUT()
    # StartCountingOpenedFiles()
        
def shutdown():
    Dprint(2, 'dhnio.shutdown')
    RestoreSTDOUT()

def InstallLocale():
    global LocaleInstalled
    if LocaleInstalled:
        return False
    try:
        import sys
        reload(sys)
        if hasattr(sys, "setdefaultencoding"):
            import locale
            denc = locale.getpreferredencoding()
            if denc != '':
                sys.setdefaultencoding(denc)
        LocaleInstalled = True
    except:
        pass
    return LocaleInstalled

# from here: 
# http://algorithmicallyrandom.blogspot.com/2009/10/python-tips-and-tricks-flushing-stdout.html
# Thanks!!!
def UnbufferedSTDOUT():
    global OriginalStdOut
    OriginalStdOut = sys.stdout
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

def RestoreSTDOUT():
    global OriginalStdOut
    if OriginalStdOut is None:
        return
    try:
        dhn_std_out = sys.stdout
        sys.stdout = OriginalStdOut
        dhn_std_out.close()
    except:
        traceback.print_last(file=open('dhnio.shutdown.error', 'w'))

# http://habrahabr.ru/post/117236/
# import sys
# import codecs
def setup_console(sys_enc="utf-8"):
    reload(sys)
    try:
        if sys.platform.startswith("win"):
            import ctypes
            enc = "cp%d" % ctypes.windll.kernel32.GetOEMCP()
        else:
            enc = (sys.stdout.encoding if sys.stdout.isatty() else
                        sys.stderr.encoding if sys.stderr.isatty() else
                            sys.getfilesystemencoding() or sys_enc)

        sys.setdefaultencoding(sys_enc)

        if sys.stdout.isatty() and sys.stdout.encoding != enc:
            sys.stdout = codecs.getwriter(enc)(sys.stdout, 'replace')

        if sys.stderr.isatty() and sys.stderr.encoding != enc:
            sys.stderr = codecs.getwriter(enc)(sys.stderr, 'replace')

    except:
        pass


#  Also, sys.platform is things like "win32" and "linux2"
#  also  os.name is "posix" for linux, "nt" for "nt" and ____ for windows
#  "Linux", "Windows"
#  don't print anything in ostype because used in dhnbackup.py and stdout goes to tar file
def ostype():
    global PlatformInfo
    if PlatformInfo is None:
        PlatformInfo = platform.uname()
    return PlatformInfo[0]

def osversion():
    global PlatformInfo
    if PlatformInfo is None:
        PlatformInfo = platform.uname()
    return PlatformInfo[2]

def osinfo():
    return str(platform.platform()).strip()

def osinfofull():
    import pprint
    o = ''
    o += '=====================================================\n'
    o += '=====================================================\n'
    o += '=====================================================\n'
    o += 'platform.uname(): ' + str(platform.uname()) + '\n'
    o += 'sys.executable: ' + sys.executable + '\n'
    o += 'os.path.abspath("."): ' + os.path.abspath('.') + '\n'
    o += 'os.path.abspath(sys.argv[0]): ' + os.path.abspath(sys.argv[0]) + '\n'
    o += 'os.path.expanduser("~"): ' + os.path.expanduser('~') + '\n'
    o += 'sys.argv: ' + pprint.pformat(sys.argv) + '\n'
    o += 'sys.path:\n' + pprint.pformat(sys.path) + '\n'
    o += 'os.environ:\n' + pprint.pformat(os.environ.items()) + '\n'
    o += '=====================================================\n'
    o += '=====================================================\n'
    o += '=====================================================\n'
    return o

def windows_version():
    if getattr(sys, 'getwindowsversion', None) is not None:
        return sys.getwindowsversion()[0]
    return 0

def Linux():
    return ostype() == "Linux"

def Windows():
    return ostype() == "Windows"

def Mac():
    return ostype() == "Darwin"

def isFrozen():
    return main_is_frozen()

def FrozenIsDebug():
    if not main_is_frozen():
        return False
    return os.path.basename(sys.executable) == 'dhnmaind.exe'

def SetDebug(level):
    global DebugLevel
    if DebugLevel > level:
        Dprint(level, "dhnio.SetDebug DebugLevel=" + str(level))
    DebugLevel = level

def LifeBegins():
    global LifeBeginsTime
    LifeBeginsTime = time.time()

# return True if something at this level should be reported given current DebugLevel
def Debug(level):
    global DebugLevel
    return level <= DebugLevel

def Dprint(level, s, nl='\n'):
    global WebStreamFunc
    global LogFile
    global RedirectStdOut
    global ShowTime
    global LifeBeginsTime
    global NoOutput
    global LogLinesCounter
    global EnableLog
    global DebugLevel
    if not EnableLog:
        return
    if isinstance(s, unicode):
        s = s.encode('utf-8')
    s_ = s
    if level % 2:
        level -= 1
    if level:
        s = ' ' * level + s
    if ShowTime and level > 0:
        if LifeBeginsTime != 0:
            dt = time.time() - LifeBeginsTime
            mn = dt // 60
            sc = dt - mn * 60
            if DebugLevel>=8:
                s = ('%02d:%02d.%02d' % (mn, sc, (sc-int(sc))*100)) + s
            else:
                s = ('%02d:%02d' % (mn, sc)) + s
        else:
            s = time.strftime('%H:%M:%S') + s
    if Debug(18):
        currentThreadName = threading.currentThread().getName()
        # if currentThreadName.find('MainThread') >= 0:
        s = s + ' {%s}' % currentThreadName.lower()
    if Debug(level):
        if LogFile is not None:
            LogFile.write(s + nl)
            LogFile.flush()
        #else:
        if not RedirectStdOut and not NoOutput:
            # sys.stdout.write(s + nl)
            #print s
            if nl == '\n':
                print s
            else:
                sys.stdout.write(s + nl)
    if WebStreamFunc is not None:
        #WebStreamFunc(level, s_.rstrip())
        WebStreamFunc(level, s_ + nl)
    LogLinesCounter += 1
    if LogLinesCounter % 10000 == 0:
        Dprint(2, '[%s]' % time.asctime())

def DprintStd(level, s):
    s_ = s
    level_ = level
    if level_ % 2:
        level_ -= 1
    if level == 1:
        level_ = 1
    if level_:
        s_ = ' ' * level_ + s_
        s_ = time.strftime('%H:%M:%S') + s_
    print s_

def Dglobals(level, glob_dict):
    global DebugLevel
    if (level>DebugLevel):
        return
    keys = glob_dict.keys()
    keys.sort()
    for k in keys:
        if k != '__builtins__':
            print k, glob_dict[k]

_TimePush = 0.0
_TimeTotalDict = {}
_TimeDeltaDict = {}
_TimeCountsDict = {}
def DTimePush(t):
    global _TimeTotalDict
    global _TimeDeltaDict
    global _TimeCountsDict
    tm = time.time()
    if not _TimeTotalDict.has_key(t):
        _TimeTotalDict[t] = 0.0
        _TimeCountsDict[t] = 0
    _TimeDeltaDict[t] = tm

def DTimePop(t):
    global _TimeTotalDict
    global _TimeDeltaDict
    global _TimeCountsDict
    tm = time.time()
    if not _TimeTotalDict.has_key(t):
        return
    dt = tm - _TimeDeltaDict[t]
    _TimeTotalDict[t] += dt
    _TimeCountsDict[t] += 1

def DprintTotalTime():
    global _TimeTotalDict
    global _TimeDeltaDict
    global _TimeCountsDict
    for t in _TimeTotalDict.keys():
        total = _TimeTotalDict[t]
        counts = _TimeCountsDict[t]
        Dprint(2, 'total=%f sec. count=%d, avarage=%f: %s' % (total, counts, total/counts, t))

def exceptionName(value):
    try:
        excStr = unicode(value)
    except:
        try:
            excStr = repr(value)
        except:
            try:
                excStr = str(value)
            except:
                try:
                    excStr = value.message
                except:
                    excStr = type(value).__name__
    return excStr

def formatExceptionInfo(maxTBlevel=100, exc_info=None):
    if exc_info is None:
        cla, value, trbk = sys.exc_info()
    else:
        cla, value, trbk = exc_info
    try:
        excArgs = value.__dict__["args"]
    except KeyError:
        excArgs = ''
    excTb = traceback.format_tb(trbk, maxTBlevel)
    tbstring = 'Exception: <' + exceptionName(value) + '>\n'
    if excArgs:
        s += '  args:' + excArgs + '\n' 
    for s in excTb:
        tbstring += s + '\n'
    return tbstring

def DprintException(level=0, maxTBlevel=100, exc_info=None):
    global LogFileName
    if exc_info is None:
        cla, value, trbk = sys.exc_info()
    else:
        cla, value, trbk = exc_info
    try:
        excArgs = str(value.__dict__["args"])
    except KeyError:
        excArgs = ''
    excTb = traceback.format_tb(trbk, maxTBlevel)
    s = 'Exception: <' + exceptionName(value) + '>\n'
    Dprint(level, s.strip())
    if excArgs:
        s += '  args:' + excArgs + '\n'
        Dprint(level, '  args:' + excArgs)
    s += '\n'
    excTb.reverse()
    for l in excTb:
        Dprint(level, l.replace('\n', ''))
        s += l + '\n'
    try:
        file = open(os.path.join(os.path.dirname(LogFileName), 'exception.log'), 'w')
        file.write(s)
        file.close()
    except:
        pass

def ExceptionHook(type, value, traceback):
    DprintException(exc_info=(type, value, traceback))

#------------------------------------------------------------------------------

def SetWebStream(webstreamfunc):
    global WebStreamFunc
    WebStreamFunc = webstreamfunc

def WebStream():
    global WebStreamFunc
    return WebStreamFunc

def OpenLogFile(filename, append_mode=False):
    global LogFile
    global LogFileName
    if LogFile:
        return
    try:
        if not os.path.isdir(os.path.dirname(os.path.abspath(filename))):
            os.makedirs(os.path.dirname(os.path.abspath(filename)))
        if append_mode:
            LogFile = open(os.path.abspath(filename), 'a')
        else:
            LogFile = open(os.path.abspath(filename), 'w')
        #sys.stderr = LogFile
        #sys.stdout = LogFile
        LogFileName = os.path.abspath(filename)
    except:
        Dprint(0, 'cant open ' + filename)
        DprintException()

def CloseLogFile():
    global LogFile
    if not LogFile:
        return
    LogFile.flush()
    LogFile.close()
    LogFile = None

class DHN_stdout:
    softspace = 0
    def read(self): pass
    def write(self, s):
        # Dprint(0, s.rstrip())
        Dprint(0, unicode(s).rstrip())
    def flush(self): pass
    def close(self): pass

class DHN_black_hole:
    softspace = 0
    def read(self): pass
    def write(self, s):  pass
    def flush(self): pass
    def close(self): pass


def StdOutRedirectingStart():
    global RedirectStdOut
    global StdOutPrev
    RedirectStdOut = True
    StdOutPrev = sys.stdout
    sys.stdout = DHN_stdout()

def StdOutRedirectingStop():
    global RedirectStdOut
    global StdOutPrev
    RedirectStdOut = False
    if StdOutPrev is not None:
        sys.stdout = StdOutPrev

def DisableOutput():
    global RedirectStdOut
    global StdOutPrev
    global NoOutput
    NoOutput = True
    RedirectStdOut = True
    StdOutPrev = sys.stdout
    sys.stdout = DHN_black_hole()

def DisableLogs():
    global EnableLog
    EnableLog = False

#-------------------------------------------------------------------------------

def list_dir_recursive(dir):
    r = []
    for name in os.listdir(dir):
        full_name = os.path.join(dir, name)
        if os.path.isdir(full_name):
            r.extend(list_dir_recursive(full_name))
        else:
            r.append(full_name)
    return r

def traverse_dir_recursive(callback, basepath, relpath=''):
    for name in os.listdir(basepath):
        realpath = os.path.join(basepath, name)
        subpath = name if relpath == '' else relpath+'/'+name
        go_down = callback(realpath, subpath, name)
        if os.path.isdir(realpath) and go_down:
            traverse_dir_recursive(callback, realpath, subpath)

#http://mail.python.org/pipermail/python-list/2000-December/060960.html
def rmdir_recursive(dirpath, ignore_errors=False, pre_callback=None):
    """Remove a directory, and all its contents if it is not already empty."""
    for name in os.listdir(dirpath):
        full_name = os.path.join(dirpath, name)
        # on Windows, if we don't have write permission we can't remove
        # the file/directory either, so turn that on
        if not os.access(full_name, os.W_OK):
            try:
                os.chmod(full_name, 0600)
            except:
                pass
        if os.path.isdir(full_name):
            rmdir_recursive(full_name, ignore_errors, pre_callback)
        else:
            if pre_callback:
                if not pre_callback(full_name):
                    continue   
            if os.path.isfile(full_name):             
                if not ignore_errors:
                    os.remove(full_name)
                else:
                    try:
                        os.remove(full_name)
                    except:
                        Dprint(6, 'dhnio.rmdir_recursive can not remove file ' + full_name)
    if pre_callback:
        if not pre_callback(dirpath):
            return
    if not ignore_errors:
        os.rmdir(dirpath)
    else:
        try:
            os.rmdir(dirpath)
        except:
            Dprint(6, 'dhnio.rmdir_recursive can not remove dir ' + dirpath)

def getDirectorySize(directory, include_subfolders=True):
    if Windows():
        import win32file
        import win32con
        import pywintypes
        DIR_EXCLUDES = set(['.', '..'])
        MASK = win32con.FILE_ATTRIBUTE_DIRECTORY | win32con.FILE_ATTRIBUTE_SYSTEM
        REQUIRED = win32con.FILE_ATTRIBUTE_DIRECTORY
        FindFilesW = win32file.FindFilesW
        def _get_dir_size(path):
            total_size = 0
            try:
                items = FindFilesW(path + r'\*')
            except pywintypes.error, ex:
                return total_size
            for item in items:
                total_size += item[5]
                if item[0] & MASK == REQUIRED and include_subfolders:
                    name = item[8]
                    if name not in DIR_EXCLUDES:
                        total_size += _get_dir_size(path + '\\' + name)
            return total_size
        return _get_dir_size(directory)

    dir_size = 0
    if  not include_subfolders:
        for filename in os.listdir(directory):
            filepath = os.path.abspath(os.path.join(directory, filename))
            if os.path.isfile(filepath):
                try:
                    dir_size += os.path.getsize(filepath)
                except:
                    pass
    else:
        for (path, dirs, files) in os.walk(directory):
            for file in files:
                filename = os.path.join(path, file)
                if os.path.isfile(filename):
                    try:
                        dir_size += os.path.getsize(filename)
                    except:
                        pass
    return dir_size

def getHomeDirectory():
    if not Windows():
        return os.path.expanduser('~')
    try:
        from win32com.shell import shell
        df = shell.SHGetDesktopFolder()
        pidl = df.ParseDisplayName(0, None,
            "::{450d8fba-ad25-11d0-98a8-0800361b1103}")[1]
        mydocs = shell.SHGetPathFromIDList(pidl)
##        another one method:
##        import win32com.client
##        objShell = win32com.client.Dispatch("WScript.Shell")
##        mydocs = objShell.SpecialFolders("MyDocuments")
##             Other available folders:
##             AllUsersDesktop, AllUsersStartMenu, AllUsersPrograms,
##             AllUsersStartup, Desktop, Favorites, Fonts, MyDocuments,
##             NetHood, PrintHood, Recent, SendTo, StartMenu, Startup & Templates
        return mydocs
    except:
        return os.path.expanduser('~')


#-------------------------------------------------------------------------------


### AtomicSave:  Save either all of data to file, or don't make file
##def AtomicSave(filename, data):
##    tmp = '%s.tmp' % filename
##    f = file(tmp, 'wb')
##    f.write(data)
##    os.fsync(f)
##    f.close()
##    os.rename(tmp, filename)

def AtomicWriteFile(filename, data):
    try:
        tmpfilename = filename + ".new"
        f = open(tmpfilename, "wb")
        f.write(data)
        f.flush()
        #from http://docs.python.org/library/os.html on os.fsync
        os.fsync(f.fileno())
        f.close()
        #in Unix the rename will overwrite an existing file,
        #but in Windows it fails, so have to remove existing
        if Windows() and os.path.exists(filename):
            os.remove(filename)
        os.rename(tmpfilename, filename)
    except:
        Dprint(1, 'dhnio.AtomicWriteFile ERROR ' + str(filename))
        DprintException()
        try:
            f.close() # make sure file gets closed
        except:
            pass
        return False
    return True

def AtomicAppendFile(filename, data, mode='a'): # TODO, this is not atomic
    try:
        f = open(filename, mode)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
        f.close()
    except:
        Dprint(1, 'dhnio.AtomicAppendFile ERROR ' + str(filename))
        DprintException()
        try:
            f.close() # make sure file gets closed
        except:
            DprintException()
        return False
    return True

# PREPRO - probably all writes should be Atomic, so we should write to temp file then rename
def WriteFile(filename, data):
    return AtomicWriteFile(filename, data)

def WriteFileSimple(filename, data, mode="w"):
    try:
        file = open(filename, mode)
        file.write(data)
        file.close()
    except:
        DprintException()
        return False
    return True

def ReadTextFile(filename):
    if not os.path.isfile(filename):
        return ''
    if not os.access(filename, os.R_OK):
        return ''
    try:
        file=open(filename,"r")
        data=file.read()
        file.close()
        # Windows/Linux trouble with text files
        return data.replace('\r\n','\n')
    except:
        DprintException()
        return ''

def ReadBinaryFile(filename):
    if not os.path.isfile(filename):
        return ''
    if not os.access(filename, os.R_OK):
        return ''
    try:
        file = open(filename,"rb")
        data = file.read()
        file.close()
        return data
    except:
        DprintException()
        return ''

#-------------------------------------------------------------------------------

def _read_data(path):
    if not os.path.exists(path):
        return None
    if not os.access(path, os.R_OK):
        return None
    fin = open(path, 'r')
    src = fin.read()
    fin.close()
    return src

def _write_data(path, src):
    temp_path = path + '.tmp'
    if os.path.exists(temp_path):
        if not os.access(temp_path, os.W_OK):
            return False
    if os.path.exists(path):
        if not os.access(path, os.W_OK):
            return False
        try:
            os.remove(path)
        except:
            Dprint(1, 'dhnio._write_data ERROR removing ' + str(path))
    fout = open(temp_path, 'wb')
    fout.write(src)
    fout.flush()
    os.fsync(fout)
    fout.close()
    try:
        os.rename(temp_path, path)
    except:
        Dprint(1, 'dhnio._write_data ERROR renaming %s to %s' % (str(temp_path), str(path)))
    return True

def _append_data(path, src):
    if os.path.exists(path):
        if not os.access(path, os.W_OK):
            return False
    fout = open(path, 'a')
    fout.write(src)
    fout.flush()
    os.fsync(fout)
    fout.close()
    return True

#-------------------------------------------------------------------------------

def _pack_list(lst):
    return str(len(lst))+'\n'+'\n'.join(lst)

def _unpack_list(src):
    if src.strip() == '':
        return list(), None
    words = src.splitlines()
    if len(words) == 0:
        return list(), None
    try:
        length = int(words[0])
    except:
        return words, None
    res = words[1:]
    if len(res) < length:
        res += [''] * (length - len(res))
    elif len(res) > length:
        return res[:length], res[length:]
    return res, None

def _read_list(path):
    src = _read_data(path)
    if src is None:
        return None
    return _unpack_list(src)[0]

def _write_list(path, lst):
    return _write_data(path, _pack_list(lst))

#-------------------------------------------------------------------------------

def _pack_dict(dictionary, sort=False):
    src = ''
    if sort:
        for k in sorted(dictionary.keys()):
            src += k + ' ' + str(dictionary[k]) + '\n'
    else:
        for k in sorted(dictionary.keys()):
            src += k + ' ' + str(dictionary[k]) + '\n'
    return src

def _unpack_dict_from_list(lines):
    dct = {}
    for line in lines:
        words = line.split(' ')
        if len(words) < 2:
            continue
        dct[words[0]] = ' '.join(words[1:])
    return dct

def _unpack_dict(src):
    lines = src.split('\n')
    return _unpack_dict_from_list(lines)

def _read_dict(path, default=None):
    src = _read_data(path)
    if src is None:
        return default
    return _unpack_dict(src.strip())

def _write_dict(path, dictionary, sort=False):
    data = _pack_dict(dictionary, sort)
    return _write_data(path, data)

def _dir_exist(path):
    return os.path.isdir(path)

def _dir_make(path):
    os.mkdir(path, 0777)

def _dirs_make(path):
    os.makedirs(path, 0777)

def _dir_remove(path):
    rmdir_recursive(path)

def backup_and_remove(path):
    bkpath = path + '.backup'
    if not os.path.exists(path):
        return
    if os.path.exists(bkpath):
        try:
            os.remove(bkpath)
        except:
            Dprint(1, 'dhnio.backup_and_remove ERROR can not remove file ' + bkpath)
            DprintException()

    try:
        os.rename(path, bkpath)
    except:
        Dprint(1, 'dhnio.backup_and_remove ERROR can not rename file %s to %s' % (path, bkpath))
        DprintException()

    if os.path.exists(path):
        try:
            os.remove(path)
        except:
            Dprint(1, 'dhnio.backup_and_remove ERROR can not remove file ' + path)
            DprintException()

def restore_and_remove(path, overwrite_existing = False):
    bkpath = path + '.backup'
    if not os.path.exists(bkpath):
        return

    if os.path.exists(path):
        if not overwrite_existing:
            return
        try:
            os.remove(path)
        except:
            Dprint(1, 'dhnio.restore_and_remove ERROR can not remove file ' + path)
            DprintException()

    try:
        os.rename(bkpath, path)
    except:
        Dprint(1, 'dhnio.restore_and_remove ERROR can not rename file %s to %s' % (path, bkpath))
        DprintException()

def remove_backuped_file(path):
    bkpath = path + '.backup'
    if not os.path.exists(bkpath):
        return
    try:
        os.remove(bkpath)
    except:
        Dprint(1, 'dhnio.remove_backuped_file ERROR can not remove file ' + bkpath)
        DprintException()

#  Lower the priority of the running process
def LowerPriority():
    try:
        sys.getwindowsversion()
    except:
        isWindows = False
    else:
        isWindows = True

    if isWindows:
        # Based on:
        #   "Recipe 496767: Set Process Priority In Windows" on ActiveState
        #   http://code.activestate.com/recipes/496767/
        import win32api
        import win32process
        import win32con
        pid = win32api.GetCurrentProcessId()
        handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
        win32process.SetPriorityClass(handle, win32process.BELOW_NORMAL_PRIORITY_CLASS)
    else:
        import os
        os.nice(20)

#-------------------------------------------------------------------------------

def shortPath(path):
    #get Absolute Short Path in Unicode
    #convert to 8.3 windows filenames
    path_ = os.path.abspath(path)
    if not Windows():
        if type(path_) != unicode:
            return unicode(path_)
        return path_

    if not os.path.exists(path_):
        if os.path.isdir(os.path.dirname(path_)):
            res = shortPath(os.path.dirname(path_))
            return unicode(os.path.join(res, os.path.basename(path_)))
        return unicode(path_)

    try:
        import win32api
        spath = win32api.GetShortPathName(path_)
        return unicode(spath)
    except:
        DprintException()
        return unicode(path_)

def longPath(path):
    #get Absolute Long Path in Unicode
    #convert to full path. even if it was in 8.3 format
    path_ = os.path.abspath(path)
    if not Windows():
        if type(path_) != unicode:
            return unicode(path_)
        return path_

    if not os.path.exists(path_):
        return unicode(path_)

    try:
        import win32api
        lpath = win32api.GetLongPathName(path_)
        return unicode(lpath)
    except:
        DprintException()
    return unicode(path_)

def _encode(s):    
    if isinstance(s, unicode):
        return s.encode('utf-8')
    return s

def portablePath(path):
    p = path
    if isinstance(p, unicode):
        return p.encode('utf-8')
    if Windows():
        # for Windows we change all separators to Linux format: \\->/ \=>/
        p = p.replace('\\\\', '/').replace('\\', '/')
    return p

#------------------------------------------------------------------------------ 

# http://www.py2exe.org/index.cgi/HowToDetermineIfRunningFromExe
def main_is_frozen():
    return (hasattr(sys, "frozen") or # new py2exe
            hasattr(sys, "importers") or# old py2exe
            imp.is_frozen("__main__")) # tools/freeze

def X11_is_running():
    global X11isRunning
    if not Linux():
        return False
    if X11isRunning is not None:
        return X11isRunning
    try:
        # http://stackoverflow.com/questions/1027894/detect-if-x11-is-available-python
        from subprocess import Popen, PIPE
        p = Popen(["xset", "-q"], stdout=PIPE, stderr=PIPE)
        p.communicate()
        result = p.returncode == 0
    except:
        result = False
    X11isRunning = result 
    return X11isRunning

#------------------------------------------------------------------------------ 

def getExecutableDir():
    if main_is_frozen():
        path = os.path.dirname(os.path.abspath(sys.executable))
    else:
        path = os.path.dirname(os.path.abspath(sys.argv[0]))
#    if Windows():
#        return shortPath(path)
    return unicode(path)

def getExecutableFilename():
    if main_is_frozen():
        path = os.path.abspath(sys.executable)
    else:
        path = os.path.abspath(sys.argv[0])
#    if Windows():
#        return shortPath(path)
    return unicode(path)

def getExecutableP2PDir():
    execdir = getExecutableDir()
    if os.path.isdir(os.path.join(execdir, 'p2p')):
        return os.path.join(execdir, 'p2p')
    return execdir

def getUserName():
    return os.path.basename(unicode(os.path.expanduser('~')))

#------------------------------------------------------------------------------

def listHomeDirLinux():
    if Windows():
        return []
    rootlist = []
    homedir = os.path.expanduser('~')
    for dirname in os.listdir(homedir):
        if os.path.isdir(os.path.join(homedir, dirname)):
            rootlist.append(dirname)
    return rootlist

def listLocalDrivesWindows():
    if not Windows():
        return []
    rootlist = []
    try:
        import win32api
        import win32file
        drives = (drive for drive in win32api.GetLogicalDriveStrings().split ("\000") if drive)
        for drive in drives:
            if win32file.GetDriveType(drive) == 3:
                rootlist.append(drive)
    except:
        DprintException()
    return rootlist

# def listRemovableDrivesWindowsOld():
#     l = []
#    try:
#        import wmi
#        c = wmi.WMI()
#        for d in c.Win32_LogicalDisk(DriveType=2):
#            l.append(d.Name+'\\')
#        del c
#    except:
#        DprintException()
#     return l

def listRemovableDrivesWindows():
    l = []
    try:
        import win32file
        drivebits = win32file.GetLogicalDrives()
        for d in range(1, 26):
            mask = 1 << d
            if drivebits & mask:
                # here if the drive is at least there
                drname='%c:\\' % chr(ord('A')+d)
                t = win32file.GetDriveType(drname)
                # print drname, t
                # drive_type = ctypes.windll.kernel32.GetDriveTypeA(drname)                    
                if t == win32file.DRIVE_REMOVABLE:
                    l.append(drname)
    except:
        DprintException()
    return l

def listRemovableDrivesLinux():
    try:
        return map(lambda x: os.path.join('/media', x), os.listdir('/media'))
    except:
        return []

def listRemovableDrives():
    if Linux():
        return listRemovableDrivesLinux()
    elif Windows():
        return listRemovableDrivesWindows()
    return []

def listMountPointsLinux():
    mounts = os.popen('mount')
    result = []
    for line in mounts.readlines():
        mo = re.match('^(.+?) on (.+?) type .+?$', line)
        if mo:
            device = mo.group(1)
            mount_point = mo.group(2)
            if device.startswith('/dev/'):
                result.append(mount_point)
    return result
        
def getMountPointLinux(path):
    path = os.path.abspath(path)
    while not os.path.ismount(path):
        path = os.path.dirname(path)
    return path

#-------------------------------------------------------------------------------

def find_process(applist):
    pidsL = []
    ostype = platform.uname()[0]
    if ostype == "Windows":
        return find_process_win32(applist)
    else:
        return find_process_linux(applist)
    return pidsL


def kill_process(pid):
    ostype = platform.uname()[0]
    if ostype == "Windows":
        kill_process_win32(pid)
    else:
        kill_process_linux(pid)


def list_processes_linux():
    """
    This function will return an iterator with the process pid/cmdline tuple

    :return: pid, cmdline tuple via iterator
    :rtype: iterator

    >>> for procs in list_processes():
    >>>     print procs
    ('5593', '/usr/lib/mozilla/kmozillahelper')
    ('6353', 'pickup -l -t fifo -u')
    ('6640', 'kdeinit4: konsole [kdeinit]')
    ('6643', '/bin/bash')
    ('7451', '/usr/bin/python /usr/bin/ipython')
    """
    for pid_path in glob.glob('/proc/[0-9]*'):
        try:
            # cmdline represents the command whith which the process was started
            f = open("%s/cmdline" % pid_path)
            pid = pid_path.split("/")[2] # get the PID
            # we replace the \x00 to spaces to make a prettier output from kernel
            cmdline = f.read().replace("\x00", " ").rstrip()
            f.close()
    
            yield (pid, cmdline)
        except:
            pass


def find_process_linux(applist):
    pidsL = []
    for pid, cmdline in list_processes_linux():
        try:
            pid = int(pid)
        except:
            continue
        if pid == os.getpid():
            continue
        for app in applist:
            if app.startswith('regexp:'):
                if re.match(app[7:], cmdline) is not None:
                    pidsL.append(pid)
            else:
                if cmdline.find(app) > -1:
                    pidsL.append(pid)
    return pidsL


def find_process_win32(applist):
    pidsL = []
    try:
        import win32com.client
        objWMI = win32com.client.GetObject("winmgmts:\\\\.\\root\\CIMV2")
        colProcs = objWMI.ExecQuery("SELECT * FROM Win32_Process")
        for Item in colProcs:
            pid = int(Item.ProcessId)
            if pid == os.getpid():
                continue
            cmdline = Item.Caption.lower()
            if Item.CommandLine:
                cmdline += Item.CommandLine.lower()
            for app in applist:
                if app.startswith('regexp:'):
                    if re.match(app[7:], cmdline) is not None:
                        pidsL.append(pid)
                else:
                    if cmdline.find(app) > -1:
                        pidsL.append(pid)
    except:
        DprintException()
    return pidsL


def kill_process_linux(pid):
    try:
        import signal
        os.kill(pid, signal.SIGTERM)
    except:
        DprintException()


def kill_process_win32(pid):
    try:
        from win32api import TerminateProcess, OpenProcess, CloseHandle
    except:
        DprintException()
        return False
    try:
        PROCESS_TERMINATE = 1
        handle = OpenProcess(PROCESS_TERMINATE, False, pid)
    except:
        Dprint(2, 'dhnio.kill_process_win32 can not open process %d' % pid)
        return False
    try:
        TerminateProcess(handle, -1)
    except:
        Dprint(2, 'dhnio.kill_process_win32 can not terminate process %d' % pid)
        return False
    try:
        CloseHandle(handle)
    except:
        DprintException()
        return False
    return True



    

