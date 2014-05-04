#!/usr/bin/python
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

"""
This python code can be used to replace the Unix tar command
and so be portable to non-unix machines.
There are other python tar libraries, but this is included with Python.
So that file is starter as child process of DHN to prepare data for backup.

TODO:
If we kept track of how far we were through a list of files, and broke off
new `dhnblocks` at file boundaries, we could restart a backup and continue
were we left off if a crash happened while we were waiting to send a block
(most of the time is waiting so good chance).

*************  WARNING ***************
Note that we should not print things here because tar output goes to standard out.
If we print anything else to stdout the .tar file will be ruined.
We must also not print things in anything this calls.
*************  WARNING ***************

Inspired from examples here:
    http://docs.python.org/lib/tar-examples.html
    http://code.activestate.com/recipes/299412/
"""

import os
import sys
import platform
import tarfile

try:
    import msvcrt
    msvcrt.setmode(1, os.O_BINARY)
except:
    pass

#------------------------------------------------------------------------------ 

def logfilepath():
    """
    A method to detect where is placed the log file for `dhnbackup` child process.
    """
    if platform.uname()[0] == 'Windows':
        logspath = os.path.join(os.environ['APPDATA'], 'DataHaven.NET', 'logs')
    else:
        logspath = os.path.join(os.path.expanduser('~'), '.datahaven', 'logs')
    if not os.path.isdir(logspath):
        return 'dhnbackup.log'
    return os.path.join(logspath, 'dhnbackup.log')

def printlog(txt):
    """
    Write a line to the log file.
    """
    LogFile = open(logfilepath(), 'a')
    LogFile.write(txt)
    LogFile.close()

#------------------------------------------------------------------------------ 

def _LinuxExcludeFunction(filename):
    """
    Return True if given file must not be included in the backup.  
    Filename comes in with the path relative to the start path, so: 
        "dirbeingbackedup/photos/christmas2008.jpg"
        
    PREPRO:
    On linux we should test for the attribute meaning "nodump" or "nobackup"
    This is set with:
        chattr +d <file>
    And listed with: 
        lsattr <file>
    Also should test that the file is readable and maybe that directory is executable. 
    If tar gets stuff it can not read - it just stops and we the whole process is failed.
    """
    if filename.count("datahavennet"):
        return True
    if filename.count(".datahaven"):
        return True
    if not os.access(filename, os.R_OK):
        return True
    return False # don't exclude the file

def _WindowsExcludeFunction(filename):
    """
    Same method for Windows platforms.
    Filename comes in with the path relative to the start path, so: 
        "Local Settings\Application Data\Microsoft\Windows\UsrClass.dat"
    
    PREPRO:
    On windows I run into some files that Windows tells me 
    I don't have permission to open (system files), 
    I had hoped to use 
        os.access(filename, os.R_OK) == False 
    to skip a file if I couldn't read it, but I did not get it to work every time. DWC.
    """
    if (filename.lower().find("local settings\\temp") != -1) or (filename.lower().find("datahaven.net") != -1) :
        return True
    return False # don't exclude the file

_ExcludeFunction = _LinuxExcludeFunction
if platform.uname()[0] == 'Windows':
    _ExcludeFunction = _WindowsExcludeFunction

#------------------------------------------------------------------------------
 
def writetar(sourcepath, subdirs=True, compression='none', encoding=None):
    """
    Create a tar archive from given `sourcepath` location.
    """
    mode = 'w|'
    if compression != 'none':
        mode += compression
    basedir, filename = os.path.split(sourcepath)
    tar = tarfile.open('', mode, fileobj=sys.stdout, encoding=encoding)
    # if we have python 2.6 then we can use an exclude function, filter parameter is not available
    if sys.version_info[:2] == (2, 6):
        tar.add(sourcepath, unicode(filename), subdirs, _ExcludeFunction) 
        if not subdirs and os.path.isdir(sourcepath): # the True is for recursive, if we wanted to just do the immediate directory set to False
            for subfile in os.listdir(sourcepath):
                subpath = os.path.join(sourcepath, subfile)
                if not os.path.isdir(subpath): 
                    tar.add(subpath, unicode(os.path.join(filename, subfile)), subdirs, _ExcludeFunction)
    # for python 2.7 we should have a filter parameter, which should be used instead of exclude function 
    elif sys.version_info[:2] == (2, 7):
        def _filter(tarinfo, basedir):
            global _ExcludeFunction
            if _ExcludeFunction(os.path.join(basedir,tarinfo.name)):
                return None
            return tarinfo
        tar.add(sourcepath, unicode(filename), subdirs, filter=lambda tarinfo: _filter(tarinfo, basedir)) 
        if not subdirs and os.path.isdir(sourcepath):
            # the True is for recursive, if we wanted to just do the immediate directory set to False
            for subfile in os.listdir(sourcepath):
                subpath = os.path.join(sourcepath, subfile)
                if not os.path.isdir(subpath): 
                    tar.add(subpath, unicode(os.path.join(filename, subfile)), subdirs, filter=_filter) 
    # otherwise no exclude function
    else: 
        tar.add(sourcepath, unicode(filename), subdirs)
        if not subdirs and os.path.isdir(sourcepath):
            for subfile in os.listdir(sourcepath):
                subpath = os.path.join(sourcepath, subfile)
                if not os.path.isdir(subpath): 
                    tar.add(subpath, unicode(os.path.join(filename, subfile)), subdirs) 
    tar.close()

#------------------------------------------------------------------------------ 

def readtar(archivepath, outputdir, encoding=None):
    """
    Extract tar file from `archivepath` location into local `outputdir` folder.
    """
    mode = 'r:*'
    tar = tarfile.open(archivepath, mode, encoding=encoding)
    tar.extractall(outputdir)
    tar.close()

#------------------------------------------------------------------------------ 

def main():
    """
    The entry point of the `dhnbackup` child process. 
    Use command line arguments to get the command from `dhnmain`. 
    """
    try:
        import sys
        reload(sys)
        if hasattr(sys, "setdefaultencoding"):
            import locale
            denc = locale.getpreferredencoding()
            if denc != '':
                sys.setdefaultencoding(denc)
    except:
        pass

#    if len(sys.argv) < 4:
#        printlog('sys.argv: %s\n' % str(sys.argv))
#        printlog('dhnbackup ["subdirs"/"nosubdirs"/"extract"] ["none"/"bz2"/"gz"] [folder path]\n')
#        return 2

    # printlog(str(sys.argv) + '\n')

    try:
        cmd = sys.argv[1].strip().lower()
        if cmd == 'extract':
            readtar(sys.argv[2], sys.argv[3])
        else:
            writetar(sys.argv[3], cmd == 'subdirs', sys.argv[2], encoding=locale.getpreferredencoding())
    except:
        import traceback
        printlog('\n'+traceback.format_exc()+'\n')
        return 1
    
    return 0

#------------------------------------------------------------------------------ 

if __name__ == "__main__":
    main()


