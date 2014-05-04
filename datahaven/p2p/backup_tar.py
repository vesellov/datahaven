#!/usr/bin/python
#backup_tar.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

"""
We want a pipe output or input so we don't need to store intermediate data.
Our backup code only takes data from this pipe when it is ready and form blocks one by one.

The class `lib.nonblocking.Popen` starts another process - that process can block but we don't.

We call that "tar" because standard TAR utility is used
to read data from files and folders and create a single data stream.
This data stream is passed via `Pipe` to the main process.
 
This module execute a sub process "dhnbackup" - pretty simple TAR compressor, 
see `p2p.dhnbackup` module.
"""

import os
import sys
# import subprocess

try:
    import lib.dhnio as dhnio
except:
    dirpath = os.path.dirname(os.path.abspath(sys.argv[0]))
    sys.path.insert(0, os.path.abspath('datahaven'))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..')))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..', '..')))
    try:
        import lib.dhnio as dhnio
    except:
        sys.exit()

# import lib.nonblocking as nonblocking
import lib.child_process as child_process

#------------------------------------------------------------------------------ 

def backuptar(directorypath, recursive_subfolders=True, compress=None):
    """
    Returns file descriptor for process that makes tar archive.
    In other words executes a child process and create a Pipe to communicate with it.
    """
    if not os.path.isdir(directorypath):
        dhnio.Dprint(1, 'backup_tar.backuptar ERROR %s not found' % directorypath)
        return None
    subdirs = 'subdirs'
    if not recursive_subfolders:
        subdirs = 'nosubdirs'
    if compress is None:
        compress = 'none'
    # dhnio.Dprint(14, "backup_tar.backuptar %s %s compress=%s" % (directorypath, subdirs, compress))
    if dhnio.Windows():
        if dhnio.isFrozen():
            commandpath = "dhnbackup.exe"
            cmdargs = [commandpath, subdirs, compress, directorypath]
        else:
            commandpath = "dhnbackup.py"
            cmdargs = [sys.executable, commandpath, subdirs, compress, directorypath]
    else:
        commandpath = "dhnbackup.py"
        cmdargs = [sys.executable, commandpath, subdirs, compress, directorypath]
    if not os.path.isfile(commandpath):
        dhnio.Dprint(1, 'backup_tar.backuptar ERROR %s not found' % commandpath)
        return None
    # dhnio.Dprint(14, "backup_tar.backuptar going to execute %s" % str(cmdargs))
    # p = run(cmdargs)
    p = child_process.pipe(cmdargs)
    return p


def backuptarfile(filepath, compress=None):
    """
    Almost same - returns file descriptor for process that makes tar archive.
    But tar archive is created from single file, not folder.
    """
    if not os.path.isfile(filepath):
        dhnio.Dprint(1, 'backup_tar.backuptarfile ERROR %s not found' % filepath)
        return None
    if compress is None:
        compress = 'none'
    # dhnio.Dprint(14, "backup_tar.backuptarfile %s compress=%s" % (filepath, compress))
    if dhnio.Windows():
        if dhnio.isFrozen():
            commandpath = "dhnbackup.exe"
            cmdargs = [commandpath, 'nosubdirs', compress, filepath]
        else:
            commandpath = "dhnbackup.py"
            cmdargs = [sys.executable, commandpath, 'nosubdirs', compress, filepath]
    else:
        commandpath = "dhnbackup.py"
        cmdargs = [sys.executable, commandpath, 'nosubdirs', compress, filepath]
    if not os.path.isfile(commandpath):
        dhnio.Dprint(1, 'backup_tar.backuptarfile ERROR %s not found' % commandpath)
        return None
    # dhnio.Dprint(12, "backup_tar.backuptarfile going to execute %s" % str(cmdargs))
    # p = run(cmdargs)
    p = child_process.pipe(cmdargs)
    return p


def extracttar(tarfile, outdir):
    """
    Opposite method, run dhnbackup to extract files and folders from ".tar" file.
    """
    if not os.path.isfile(tarfile):
        dhnio.Dprint(1, 'backup_tar.extracttar ERROR %s not found' % tarfile)
        return None
    # dhnio.Dprint(12, "backup_tar.extracttar %s %s" % (tarfile, outdir))
    if dhnio.Windows():
        if dhnio.isFrozen():
            commandpath = 'dhnbackup.exe'
            cmdargs = [commandpath, 'extract', tarfile, outdir]
        else:
            commandpath = "dhnbackup.py"
            cmdargs = [sys.executable, commandpath, 'extract', tarfile, outdir]
    else:
        commandpath = "dhnbackup.py"
        cmdargs = [sys.executable, commandpath, 'extract', tarfile, outdir]
    if not os.path.isfile(commandpath):
        dhnio.Dprint(1, 'backup_tar.extracttar ERROR %s is not found' % commandpath)
        return None
    # p = run(cmdargs)
    p = child_process.pipe(cmdargs)
    return p


#------------------------------------------------------------------------------ 

if __name__ == "__main__":
    dhnio.SetDebug(20)
    p = backuptar(sys.argv[1])
    p.make_nonblocking()
    print p
    print p.wait()
    
