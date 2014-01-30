#!/usr/bin/python
#dhntester.py

import os
import sys
import platform

import time

#------------------------------------------------------------------------------ 

def logfilepath():
    if platform.uname()[0] == 'Windows':
        logspath = os.path.join(os.environ['APPDATA'], 'DataHaven.NET', 'logs')
    else:
        logspath = os.path.join(os.path.expanduser('~'), '.datahaven', 'logs')
    if not os.path.isdir(logspath):
        return 'dhntester.log'
    return os.path.join(logspath, 'dhntester.log')

def printlog(txt):
    LogFile = open(logfilepath(), 'a')
    LogFile.write(txt+'\n')
    LogFile.close()
    
#------------------------------------------------------------------------------ 

if __name__ == "__main__":
    dirpath = os.path.dirname(os.path.abspath(sys.argv[0]))
    sys.path.insert(0, os.path.abspath('datahaven'))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..')))
    sys.path.insert(0, os.path.abspath(os.path.join(dirpath, '..', '..')))

try:
    import lib.dhnio as dhnio
    from lib.dhnpacket import Unserialize
    from lib.nameurl import FilenameUrl
    from lib.settings import init as settings_init
    from lib.settings import CustomersSpaceFile, getCustomersFilesDir, LocalTesterLogFilename
    from lib.settings import BackupIndexFileName
    from lib.contacts import init as contacts_init
    from lib.commands import init as commands_init
except:
    import traceback
    printlog(traceback.format_exc())
    sys.exit(2)

# need to make sure the dhntester log is in a directory the user has permissions for,
# such as the customer data directory.  Possibly move to temp directory?
# sys.stdout = myoutput
# sys.stderr = myoutput

#-------------------------------------------------------------------------------
#test all packets for each customer.
#check if he use more space than we gave him and if packets is too old.
def SpaceTime():
    printlog('SpaceTime ' + str(time.strftime("%a, %d %b %Y %H:%M:%S +0000")))
    space = dhnio._read_dict(CustomersSpaceFile())
    if space is None:
        printlog('SpaceTime ERROR can not read file ' + CustomersSpaceFile())
        return
    customers_dir = getCustomersFilesDir()
    if not os.path.exists(customers_dir):
        printlog('SpaceTime ERROR customers folder not exist')
        return
    remove_list = {}
    for customer_filename in os.listdir(customers_dir):
        onecustdir = os.path.join(customers_dir, customer_filename)
        if not os.path.isdir(onecustdir):
            remove_list[onecustdir] = 'is not a folder'
            continue
        idurl = FilenameUrl(customer_filename)
        if idurl is None:
            remove_list[onecustdir] = 'wrong folder name'
            continue
        curspace = space.get(idurl, None)
        if curspace is None:
            continue
        try:
            maxspaceV = int(float(curspace) * 1024 * 1024) #in bytes
        except:
            remove_list[onecustdir] = 'wrong space value'
            continue
        timedict = {}
        sizedict = {}
        def cb(path, subpath, name):
            if not os.access(path, os.R_OK | os.W_OK):
                return False
            if not os.path.isfile(path):
                return True
            if name in [BackupIndexFileName(),]:
                return False
            stats = os.stat(path)
            timedict[path] = stats.st_ctime
            sizedict[path] = stats.st_size
        dhnio.traverse_dir_recursive(cb, onecustdir)
        currentV = 0
        for path in sorted(timedict.keys(), key=lambda x:timedict[x], reverse=True):
            currentV += sizedict.get(path, 0)
            if currentV < maxspaceV:
                continue
            try:
                os.remove(path)
                printlog('SpaceTime ' + path + ' file removed (cur:%s, max: %s)' % (str(currentV), str(maxspaceV)) )
            except:
                printlog('SpaceTime ERROR removing ' + path)
            time.sleep(0.1)
        timedict.clear()
        sizedict.clear()
    for path in remove_list.keys():
        if not os.path.exists(path):
            continue
        if os.path.isdir(path):
            try:
                dhnio._dir_remove(path)
                printlog('SpaceTime ' + path + ' dir removed (%s)' % (remove_list[path]))
            except:
                printlog('SpaceTime ERROR removing ' + path)
            continue
        if not os.access(path, os.W_OK):
            os.chmod(path, 0600)
        try:
            os.remove(path)
            printlog('SpaceTime ' + path + ' file removed (%s)' % (remove_list[path]))
        except:
            printlog('SpaceTime ERROR removing ' + path)
    del remove_list

#------------------------------------------------------------------------------
#test packets after list of customers was changed
def UpdateCustomers():
    printlog('UpdateCustomers ' + str(time.strftime("%a, %d %b %Y %H:%M:%S +0000")))
    space = dhnio._read_dict(CustomersSpaceFile())
    if space is None:
        printlog('UpdateCustomers ERROR space file can not read' )
        return
    customers_dir = getCustomersFilesDir()
    if not os.path.exists(customers_dir):
        printlog('UpdateCustomers ERROR customers folder not exist')
        return
    remove_list = {}
    for customer_filename in os.listdir(customers_dir):
        onecustdir = os.path.join(customers_dir, customer_filename)
        if not os.path.isdir(onecustdir):
            remove_list[onecustdir] = 'is not a folder'
            continue
        idurl = FilenameUrl(customer_filename)
        if idurl is None:
            remove_list[onecustdir] = 'wrong folder name'
            continue
        curspace = space.get(idurl, None)
        if curspace is None:
            remove_list[onecustdir] = 'is not a customer'
            continue
    for path in remove_list.keys():
        if not os.path.exists(path):
            continue
        if os.path.isdir(path):
            try:
                dhnio._dir_remove(path)
                printlog('UpdateCustomers ' + path + ' folder removed (%s)' % (remove_list[path]))
            except:
                printlog('UpdateCustomers ERROR removing ' + path)
            continue
        if not os.access(path, os.W_OK):
            os.chmod(path, 0600)
        try:
            os.remove(path)
            printlog('UpdateCustomers ' + path + ' file removed (%s)' % (remove_list[path]))
        except:
            printlog('UpdateCustomers ERROR removing ' + path)

#------------------------------------------------------------------------------
#check all packets to be valid
def Validate():
    printlog('Validate ' + str(time.strftime("%a, %d %b %Y %H:%M:%S +0000")))
    contacts_init()
    commands_init()
    customers_dir = getCustomersFilesDir()
    if not os.path.exists(customers_dir):
        return
    for customer_filename in os.listdir(customers_dir):
        onecustdir = os.path.join(customers_dir, customer_filename)
        if not os.path.isdir(onecustdir):
            continue
        def cb(path, subpath, name):
            if not os.access(path, os.R_OK | os.W_OK):
                return False
            if not os.path.isfile(path):
                return True
            if name in [BackupIndexFileName(),]:
                return False
            packetsrc = dhnio.ReadBinaryFile(path)
            if not packetsrc:
                try:
                    os.remove(path) # if is is no good it is of no use to anyone
                    printlog('Validate ' + path + ' removed (empty file)')
                except:
                    printlog('Validate ERROR removing ' + path)
                    return False
            packet = Unserialize(packetsrc)
            if packet is None:
                try:
                    os.remove(path) # if is is no good it is of no use to anyone
                    printlog('Validate ' + path + ' removed (unserialize error)')
                except:
                    printlog('Validate ERROR removing ' + path)
                    return False
            result = packet.Valid()
            packetsrc = ''
            del packet
            if not result:
                try:
                    os.remove(path) # if is is no good it is of no use to anyone
                    printlog('Validate ' + path + ' removed (invalid packet)')
                except:
                    printlog('Validate ERROR removing ' + path)
                    return False
            time.sleep(0.1)
            return False
        dhnio.traverse_dir_recursive(cb, onecustdir)

#------------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        return
    dhnio.init()
    dhnio.DisableLogs()
    dhnio.DisableOutput()
    settings_init()
    dhnio.SetDebug(0)
    dhnio.LowerPriority()
#    dhnio.OpenLogFile(LocalTesterLogFilename(), True)
#    dhnio.StdOutRedirectingStart()
#    dhnio.LifeBegins()
    commands = {
        'update_customers' : UpdateCustomers,
        'validate' : Validate,
        'space_time' : SpaceTime,
    }
    cmd = commands.get(sys.argv[1], None)
    if not cmd:
        printlog('ERROR wrong command: ' + str(sys.argv))
        return
    cmd()
#    dhnio.StdOutRedirectingStop()
#    dhnio.CloseLogFile()

#------------------------------------------------------------------------------ 

if __name__ == "__main__":
    main()






