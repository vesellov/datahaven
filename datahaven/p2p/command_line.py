#!/usr/bin/python
#command_line.py
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
import re

try:
    from twisted.internet import reactor
except:
    dhnio.DprintException()
    sys.exit('Error initializing twisted reactor in command_line.py\n')
from twisted.web.client import getPage
from twisted.internet.defer import fail


import lib.dhnio as dhnio
import lib.misc as misc
import lib.settings as settings
import lib.diskspace as diskspace
import lib.nameurl as nameurl
import lib.contacts as contacts
import lib.dhnpacket as dhnpacket
import lib.packetid as packetid
import lib.commands as commands
import lib.transport_control as transport_control
import lib.schedule as schedule

import webcontrol

#------------------------------------------------------------------------------ 

def run(opts, args, overDict, pars):
    print 'Copyright 2006, DataHaven.NET LTD. of Anguilla. All rights reserved.'
    
    if overDict:
        settings.override_dict(overDict)
    dhnio.init()
    settings.init()
    if not opts or opts.debug is None:
        dhnio.SetDebug(0)

    appList = dhnio.find_process([
        'dhnmain.exe',
        'dhnmain.py',
        'dhn.py',
        'regexp:^/usr/bin/python\ +/usr/bin/datahaven.*$',
        ])
    running = len(appList) > 0
   
    cmd = ''
    if len(args) > 0:
        cmd = args[0].lower()
    
    #---help---
    if cmd in ['help', 'h']:
        import help
        if len(args) >= 2 and args[1].lower() == 'schedule':
            print help.schedule_format()
        elif len(args) >= 2 and args[1].lower() == 'settings':
            print settings.uconfig().print_all()
        else:
            print help.help()
            print pars.format_option_help()
        return 0
    
    #---backup---
    elif cmd in ['backup', 'backups', 'bk']:
        if not running:
            print 'DataHaven.NET is not running at the moment\n'
            return 0
        return cmd_backups(opts, args, overDict)

    #---restore---
    elif cmd in ['restore', 're']:
        if not running:
            print 'DataHaven.NET is not running at the moment\n'
            return 0
        return cmd_restore(opts, args, overDict)

    #---schedule---
    elif cmd in ['schedule', 'shed', 'sched', 'sh']:
        if not running:
            print 'DataHaven.NET is not running at the moment\n'
            return 0
        return cmd_schedule(opts, args, overDict)

    #---suppliers---
    elif cmd in [ 'suppliers', 'supplier', 'sup', 'supp', 'sp', ]:
        if not running:
            print 'DataHaven.NET is not running at the moment\n'
            return 0
        return cmd_suppliers(opts, args, overDict)
    
    #---customers---
    elif cmd in [ 'customers', 'customer', 'cus', 'cust', 'cs', ]:
        if not running:
            print 'DataHaven.NET is not running at the moment\n'
            return 0
        return cmd_customers(opts, args, overDict)

    #---register---
    elif cmd == 'register':
        if running:
            print 'DataHaven.NET already started.\n'
            return 0
        return cmd_register(opts, args, overDict)

    #---recover---
    elif cmd == 'recover':
        if running:
            print 'DataHaven.NET already started.\n'
            return 0
        return cmd_recover(opts, args, overDict)

    #---key---
    elif cmd == 'key':
        return cmd_key(opts, args, overDict)

    #---stats---
    elif cmd in [ 'stats', 'st' ]:
        if not running:
            print 'DataHaven.NET is not running at the moment\n'
            return 0
        return cmd_stats(opts, args, overDict)

    #---version---
    elif cmd in [ 'version', 'v', 'ver' ]:
        revnum = dhnio.ReadTextFile(settings.RevisionNumberFile()).strip()
        repo, location = misc.ReadRepoLocation()
        print 'revision:  ', revnum
        print 'repository:', repo
        return 0

    #---states---
    elif cmd in [ 'states', 'sta', 'automats', 'auto' ]:
        if not running:
            print 'DataHaven.NET is not running at the moment\n'
            return 0
        return cmd_states(opts, args, overDict)

    #---reconnect---
    elif cmd in [ 'reconnect', ]:
        if not running:
            print 'DataHaven.NET is not running at the moment\n'
            return 0
        return cmd_reconnect(opts, args, overDict)
        
    #---set---
    elif cmd == 'set':
        if len(args) == 1 or args[1].lower() in [ 'help', '?' ]:
            import help
            print help.settings_help()
            return 0
        if not running:
            cmd_set_directly(opts, args, overDict)
            return 0
        return cmd_set_request(opts, args, overDict)
    
    #---memory---
    elif cmd == 'memory':
        if not running:
            print 'DataHaven.NET is not running at the moment\n'
            return 0
        return cmd_memory(opts, args, overDict)
    
    #---money---
    elif cmd == 'money':
        if not running:
            print 'DataHaven.NET is not running at the moment\n'
            return 0
        return cmd_money(opts, args, overDict)
    
    elif cmd == 'storage':
        if not running:
            print 'DataHaven.NET is not running at the moment\n'
            return 0
        return cmd_storage(opts, args, overDict)
    
#    elif cmd == 'uninstall':
#        return cmd_uninstall(opts, args, overDict)
    
    return 2

#------------------------------------------------------------------------------ 

def run_url_command(address, stop_reactor_in_errback=True):
    try:
        local_port = int(dhnio.ReadBinaryFile(settings.LocalPortFilename()))
    except:
        print 'can not read local port number from the file %s\n' % settings.LocalPortFilename()
        if stop_reactor_in_errback:
            if reactor.running and not reactor._stopped:
                reactor.stop()
                return 0
        return fail('')
    
    url = 'http://127.0.0.1:'+str(local_port)+'/'+address
    dhnio.Dprint(4, 'command_line.run_url_command url='+url)
    def _eb(x, stop_reactor):
        print x.getErrorMessage()
        if stop_reactor and reactor.running and not reactor._stopped:
            reactor.stop()
    d = getPage(url)
    d.addErrback(_eb, stop_reactor_in_errback)
    return d


def find_comments(output):
    if output is None or str(output).strip() == '':
        return ['empty output']
    if not isinstance(output, str):
        return [output.getErrorMessage()]
    return re.findall('\<\!--\[begin\] (.+?) \[end\]--\>', output, re.DOTALL)

def print_and_stop(src):
    for s in find_comments(src):
        print unicode(s)
    print
    if reactor.running and not reactor._stopped:
        reactor.stop()
    
#------------------------------------------------------------------------------ 

def print_single_setting_and_stop(path, run_reactor=True):
    if path != '':
        url = webcontrol._PAGE_SETTINGS + '/' + path
        run_url_command(url).addCallback(print_and_stop)
        if run_reactor:
            reactor.run()
        return 0
    return 2

def print_all_settings_and_stop():
    url = webcontrol._PAGE_SETTINGS_LIST
    run_url_command(url).addCallback(print_and_stop)
    reactor.run()
    return 0
    
#------------------------------------------------------------------------------ 

def cmd_backups(opts, args, overDict):
    if len(args) < 2 or args[1] == 'list':
        run_url_command(webcontrol._PAGE_BACKUPS+'?action=list').addCallback(print_and_stop)
        reactor.run()
        return 0

    elif len(args) < 2 or args[1] == 'idlist':
        url = webcontrol._PAGE_BACKUPS+'?action=idlist'
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    elif args[1] == 'start' and len(args) >= 3:
        if packetid.Valid(args[2]):
            url = webcontrol._PAGE_BACKUPS+'?action=startid&pathid='+misc.pack_url_param(args[2])
        else:
            if not os.path.exists(os.path.abspath(args[2])):
                print 'path %s not exist\n' % args[2]
                return 1
            url = webcontrol._PAGE_BACKUPS+'?action=startpath&path='+misc.pack_url_param(os.path.abspath(args[2]))
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    elif args[1] == 'add' and len(args) >= 3:
        localpath = os.path.abspath(args[2])
        if not os.path.exists(localpath):
            print 'path %s not exist\n' % args[2]
            return 1
        if os.path.isdir(localpath):
            url = webcontrol._PAGE_BACKUPS+'?action=diradd&opendir='+misc.pack_url_param(localpath)
        else:
            url = webcontrol._PAGE_BACKUPS+'?action=fileadd&openfile='+misc.pack_url_param(localpath)
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0
    
    elif args[1] == 'addtree' and len(args) >= 3:
        localpath = os.path.abspath(args[2])
        if not os.path.isdir(os.path.abspath(args[2])):
            print 'folder %s not exist\n' % args[2]
            return 1
        url = webcontrol._PAGE_BACKUPS+'?action=diraddrecursive&opendir='+misc.pack_url_param(localpath)
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    elif args[1] == 'delete' and len(args) >= 3:
        if args[2] == 'local' and len(args) >= 4:
            url = webcontrol._PAGE_BACKUPS+'/'+args[3].replace('/','_')+'/action=delete.local'
        else:
            if packetid.Valid(args[2]):
                url = webcontrol._PAGE_BACKUPS+'?action=deleteid&pathid='+args[2].replace('/','_')
            else:
                url = webcontrol._PAGE_BACKUPS+'?action=deletepath&path='+misc.pack_url_param(os.path.abspath(args[2]))
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    elif args[1] == 'update':
        url = webcontrol._PAGE_BACKUPS+'?action=update'
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0
    
    return 2


def cmd_restore(opts, args, overDict):
    if len(args) == 2:
        url = webcontrol._PAGE_BACKUPS+'?action=restoresingle&backupid='+args[1]
    elif len(args) == 3:
        url = webcontrol._PAGE_BACKUPS+('?action=restoresingle&backupid=%s&dest=%s' % (
            args[1], misc.pack_url_param(args[2])))
    else:
        return 2
    run_url_command(url).addCallback(print_and_stop)
    reactor.run()
    return 0


def cmd_schedule(opts, args, overDict):
    if len(args) < 2:
        return 2
    if not os.path.isdir(os.path.abspath(args[1])):
        print 'folder %s not exist\n' % args[1]
        return 1
    backupDir = os.path.abspath(args[1])
    if len(args) < 3:
        url = webcontrol._PAGE_BACKUP_SHEDULE + '?backupdir=%s' % (
            misc.pack_url_param(backupDir),)
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0
    shed = schedule.from_compact_string(args[2])
    if shed is None:
        print schedule.format()
        print
        return 0
    url = webcontrol._PAGE_BACKUP_SHEDULE + '?action=save&submit=save&backupdir=%s&type=%s&interval=%s&daytime=%s&details=%s' % (
        misc.pack_url_param(backupDir),
        shed.type, shed.interval, shed.daytime, misc.pack_url_param(shed.details),)
    run_url_command(url).addCallback(print_and_stop)
    reactor.run()
    return 0


def cmd_suppliers(opts, args, overDict):
    def _wait_replace_supplier_and_stop(src, supplier_name, count=0):
        suppliers = []
        for s in find_comments(src):
            if s.count('[online ]') or s.count('[offline]'):
                suppliers.append(s[18:38].strip())
        if supplier_name not in suppliers:
            print '  supplier %s is fired !' % supplier_name
            print_and_stop(src)
            return
        if count >= 20:
            print ' time is out\n'
            reactor.stop()
            return
        else:
            def _check_again(supplier_name, count):
                sys.stdout.write('.')
                run_url_command(webcontrol._PAGE_SUPPLIERS).addCallback(_wait_replace_supplier_and_stop, supplier_name, count)
            reactor.callLater(1, _check_again, supplier_name, count+1)

    if len(args) < 2 or args[1] in [ 'list', 'ls' ]:
        url = webcontrol._PAGE_SUPPLIERS
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    elif args[1] in [ 'call', 'cl' ]:
        url = webcontrol._PAGE_SUPPLIERS + '?action=call'
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    elif args[1] in [ 'replace', 'rep', 'rp' ] and len(args) >= 3:
        contacts.init()
        idurl = args[2].strip()
        if not idurl.startswith('http://'):
            try:
                idurl = contacts.getSupplierID(int(idurl))
            except:
                idurl = 'http://'+settings.IdentityServerName()+'/'+idurl+'.xml'
        if not idurl:
            print 'supplier IDURL is None\n'
            return 0
        name = nameurl.GetName(idurl)
        url = webcontrol._PAGE_SUPPLIERS + '?action=replace&idurl=%s' % misc.pack_url_param(idurl)
        run_url_command(url).addCallback(_wait_replace_supplier_and_stop, name, 0)
        reactor.run()
        return 0
    
    elif args[1] in [ 'change', 'ch' ] and len(args) >= 4:
        contacts.init()
        idurl = args[2].strip()
        if not idurl.startswith('http://'):
            try:
                idurl = contacts.getSupplierID(int(idurl))
            except:
                idurl = 'http://'+settings.IdentityServerName()+'/'+idurl+'.xml'
        if not idurl:
            print 'supplier IDURL is None\n'
            return 0
        newidurl = args[3].strip()
        if not newidurl.startswith('http://'):
            newidurl = 'http://'+settings.IdentityServerName()+'/'+newidurl+'.xml'
        name = nameurl.GetName(idurl)
        newname = nameurl.GetName(newidurl)
        url = webcontrol._PAGE_SUPPLIERS + '?action=change&idurl=%s&newidurl=%s' % (misc.pack_url_param(idurl), misc.pack_url_param(newidurl))
        run_url_command(url).addCallback(_wait_replace_supplier_and_stop, name, 0)
        reactor.run()
        return 0
    
    return 2


def cmd_customers(opts, args, overDict):
    def _wait_remove_customer_and_stop(src, customer_name, count=0):
        customers = []
        for s in find_comments(src):
            if s.count('[online ]') or s.count('[offline]'):
                customers.append(s[18:38].strip())
        if customer_name not in customers:
            print '  customer %s is removed !' % customer_name
            print_and_stop(src)
            return
        if count >= 20:
            print ' time is out\n'
            reactor.stop()
            return
        else:
            def _check_again(customer_name, count):
                sys.stdout.write('.')
                run_url_command(webcontrol._PAGE_CUSTOMERS).addCallback(_wait_remove_customer_and_stop, customer_name, count)
            reactor.callLater(1, _check_again, customer_name, count+1)

    if len(args) < 2 or args[1] in [ 'list', 'ls', ]:
        url = webcontrol._PAGE_CUSTOMERS
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    elif args[1] in [ 'call', 'cl', ]:
        url = webcontrol._PAGE_CUSTOMERS + '?action=call'
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    elif args[1] in [ 'remove', 'rm', ] and len(args) >= 3:
        contacts.init()
        idurl = args[2].strip()
        if not idurl.startswith('http://'):
            try:
                idurl = contacts.getCustomerID(int(idurl))
            except:
                idurl = 'http://'+settings.IdentityServerName()+'/'+idurl+'.xml'
        name = nameurl.GetName(idurl)
        url = webcontrol._PAGE_CUSTOMERS + '?action=remove&idurl=%s' % misc.pack_url_param(idurl)
        run_url_command(url).addCallback(_wait_remove_customer_and_stop, name, 0)
        reactor.run()
        return 0
    
    return 2


def cmd_register(opts, args, overDict):
    if len(args) < 2:
        return 2
    if len(args) >= 3:
        import lib.settings as settings
        settings.uconfig().set('backup.private-key-size', str(args[2]))
        settings.uconfig().update()
    import lib.automat as automat
    import initializer
    import shutdowner
    initializer.A('run-cmd-line-register', args[1])
    reactor.run()
    shutdowner.A('reactor-stopped')
    automat.objects().clear()
    print
    return 0


def cmd_recover(opts, args, overDict):
    if len(args) < 2:
        return 2
    src = dhnio.ReadBinaryFile(args[1])
    if len(src) > 1024*10:
        print 'file is too big for private key'
        return 0
    try:
        lines = src.split('\n')
        idurl = lines[0]
        txt = '\n'.join(lines[1:])
        if idurl != nameurl.FilenameUrl(nameurl.UrlFilename(idurl)):
            idurl = ''
            txt = src
    except:
        #dhnio.DprintException()
        idurl = ''
        txt = src
    if idurl == '' and len(args) >= 3:
        idurl = args[2]
        if not idurl.startswith('http://'):
            idurl = 'http://'+settings.IdentityServerName()+'/'+idurl+'.xml'
    if idurl == '':
        print 'DataHaven.NET need to know your username to recover your account\n'
        return 2
    import lib.automat as automat
    import initializer
    import shutdowner
    initializer.A('run-cmd-line-recover', { 'idurl': idurl, 'keysrc': txt })
    reactor.run()
    #initializer.A('reactor-stopped', use_reactor = False)
    shutdowner.A('reactor-stopped')
    automat.objects().clear()
    print
    return 0


def cmd_key(opts, args, overDict):
    if len(args) == 2:
        if args[1] == 'copy':
            import lib.dhncrypto as dhncrypto 
            TextToSave = misc.getLocalID() + "\n" + dhncrypto.MyPrivateKey()
            misc.setClipboardText(TextToSave)
            print 'now you can "paste" with Ctr+V your private key where you want.'
            del TextToSave
            return 0
        elif args[1] == 'print':
            import lib.dhncrypto as dhncrypto 
            TextToSave = misc.getLocalID() + "\n" + dhncrypto.MyPrivateKey()
            print 
            print TextToSave
            return 0
    elif len(args) == 3:
        if args[1] == 'copy':
            filenameto = args[2]
            import lib.dhncrypto as dhncrypto 
            TextToSave = misc.getLocalID() + "\n" + dhncrypto.MyPrivateKey()
            if not dhnio.AtomicWriteFile(filenameto, TextToSave):
                print 'error writing to', filenameto
                return 1
            print 'your private key were copied to file %s' % filenameto
            del TextToSave
            return 0
    return 2
    
    
def cmd_stats(opts, args, overDict):
    if len(args) == 2:
        if not packetid.Valid(args[1]):
            print 'not valid backup ID'
            return 0
        url = '%s/%s%s' % (webcontrol._PAGE_MAIN, webcontrol._PAGE_BACKUP, args[1].replace('/','_'))
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    elif len(args) >= 3 and args[1] == 'remote': 
        url = '%s/%s%s' % (webcontrol._PAGE_MAIN, webcontrol._PAGE_BACKUP_REMOTE_FILES, args[2].replace('/','_'))
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    elif len(args) >= 3 and args[1] == 'local': 
        url = '%s/%s%s' % (webcontrol._PAGE_MAIN, webcontrol._PAGE_BACKUP_LOCAL_FILES, args[2].replace('/','_'))
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    return 2

def cmd_states(opts, args, overDict):
    url = '%s' % (webcontrol._PAGE_AUTOMATS)
    run_url_command(url).addCallback(print_and_stop)
    reactor.run()
    return 0
    
def cmd_reconnect(opts, args, overDict):
    url = webcontrol._PAGE_MAIN + '?action=reconnect'
    run_url_command(url).addCallback(print_and_stop)
    reactor.run()
    return 0
    
def option_name_to_path(name, default=''):
    path = default
    if name in [ 'donated', 'shared', 'given', ]:
        path = 'central-settings.shared-megabytes'
    elif name in [ 'needed', ]:
        path = 'central-settings.needed-megabytes'
    elif name in [ 'suppliers', ]:
        path = 'central-settings.desired-suppliers'
    elif name in [ 'debug' ]:
        path = 'logs.debug-level'
    elif name in [ 'tcp' ]:
        path = 'transport.transport-tcp.transport-tcp-enable'
    elif name in [ 'tcp-port' ]:
        path = 'transport.transport-tcp.transport-tcp-port'
    elif name in [ 'udp' ]:
        path = 'transport.transport-udp.transport-udp-enable'
    elif name in [ 'udp-port' ]:
        path = 'transport.transport-udp.transport-udp-port'
    elif name in [ 'cspace' ]:
        path = 'transport.transport-cspace.transport-cspace-enable'
    elif name in [ 'weblog' ]:
        path = 'logs.stream-enable'
    elif name in [ 'weblog-port' ]:
        path = 'logs.stream-port'
    return path

def cmd_set_directly(opts, args, overDict):
    def print_all_settings():
        for path in settings.uconfig().default_order:
            if path.strip() == '':
                continue
            if path not in settings.uconfig().public_options:
                continue
            value = settings.uconfig().data.get(path, '').replace('\n', ' ')
            label = settings.uconfig().labels.get(path, '')
            info = settings.uconfig().infos.get(path, '')
            print '  %s    %s' % (path.ljust(50), value.ljust(20))
        return 0
    name = args[1].lower()
    if name in [ 'list' ]:
        return print_all_settings() 
    path = '' if len(args) < 2 else args[1]
    path = option_name_to_path(name, path)
    if path != '':
        old_is = settings.uconfig().get(path)
        if len(args) > 2:
            value = ' '.join(args[2:])
            settings.uconfig().set(path, unicode(value))
            settings.uconfig().update()
        print '  XML path: %s' % path
        print '  label:    %s' % settings.uconfig().get(path, 'label')
        print '  info:     %s' % settings.uconfig().get(path, 'info')
        print '  value:    %s' % settings.uconfig().get(path)
        if len(args) > 2:
            print '  modified: [%s]->[%s]' % (old_is, value)
        return 0
    
def cmd_set_request(opts, args, overDict):
    name = args[1].lower()
    if name in [ 'list' ]:
        return print_all_settings_and_stop() 
    path = '' if len(args) < 2 else args[1]
    path = option_name_to_path(name, path)    
    if len(args) == 2:
        return print_single_setting_and_stop(path)
    action = 'action='
    leafs = path.split('.')
    name = leafs[-1]
    webcontrol.InitSettingsTreePages()
    cls = webcontrol._SettingsTreeNodesDict.get(name, None)
    input = ' '.join(args[2:])
    #print cls, name, path, input
    if cls is None:
        return 2
    if cls in [ webcontrol.SettingsTreeTextNode,
                webcontrol.SettingsTreeUStringNode,
                webcontrol.SettingsTreePasswordNode,
                webcontrol.SettingsTreeNumericNonZeroPositiveNode,
                webcontrol.SettingsTreeNumericPositiveNode,] :
        action = 'text=' + misc.pack_url_param(input)
    elif cls in [ webcontrol.SettingsTreeDiskSpaceNode, ]:
        number = misc.DigitsOnly(input, '.')
        suffix = input.lstrip('0123456789.-').strip()
        action = 'number=%s&suffix=%s' % (number, suffix)
    elif cls in [ webcontrol.SettingsTreeComboboxNode, ]:
        number = misc.DigitsOnly(input)
        action = 'choice=%s' % number
    elif cls in [ webcontrol.SettingsTreeYesNoNode, ]:
        trueORfalse = 'True' if input.lower().strip() == 'true' else 'False'
        action = 'choice=%s' % trueORfalse
    url = webcontrol._PAGE_SETTINGS + '/' + path + '?' + action
    run_url_command(url).addCallback(lambda src: print_single_setting_and_stop(path, False)) #.addCallback(print_and_stop)
    reactor.run()
    return 0


def cmd_memory(opts, args, overDict):
    url = webcontrol._PAGE_MEMORY
    run_url_command(url).addCallback(print_and_stop)
    reactor.run()
    return 0


def cmd_storage(opts, args, overDict):
    url = webcontrol._PAGE_STORAGE
    run_url_command(url).addCallback(print_and_stop)
    reactor.run()
    return 0


def cmd_money(opts, args, overDict):
    if len(args) == 1:
        url = webcontrol._PAGE_MONEY
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    elif len(args) >= 2 and args[1] == 'receipts': 
        url = webcontrol._PAGE_RECEIPTS
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0

    elif len(args) >= 3 and args[1] == 'receipt': 
        url = '%s/%s' % (webcontrol._PAGE_RECEIPTS, args[2])
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0
    
    elif len(args) >= 4 and args[1] == 'transfer':
        recipient = args[2].strip()
        if not recipient.startswith('http://'):
            recipient = 'http://'+settings.IdentityServerName()+'/'+recipient+'.xml'
        url = '%s?action=commit&recipient=%s&amount=%s' % (webcontrol._PAGE_TRANSFER, misc.pack_url_param(recipient), args[3]) 
        run_url_command(url).addCallback(print_and_stop)
        reactor.run()
        return 0
    
    return 2
    

def cmd_uninstall(opts, args, overDict):
    if not dhnio.Windows():
        print 'This command can be used only under OS Windows.'
        return 0
    if not dhnio.isFrozen():
        print 'You are running DataHaven.NET from sources, uninstall command is available only for binary version.'
        return 0
    def do_uninstall():
        dhnio.Dprint(0, 'command_line.do_uninstall')
        batfilename = misc.MakeBatFileToUninstall()
        misc.UpdateRegistryUninstall(True)
        misc.RunBatFile(batfilename, 'c:/out2.txt')
    def kill():
        dhnio.Dprint(0, 'kill')
        total_count = 0
        found = False
        while True:
            appList = dhnio.find_process([
                'dhnmain.exe',
                'dhnmain.py',
                'dhn.py',
                'regexp:^/usr/bin/python\ +/usr/bin/datahaven.*$',
                'dhnview.exe',
                'dhnview.py',
                'dhnbackup.exe',
                'dhnbackup.py',
                'dhntester.exe',
                'dhntester.py',
                'dhnstarter.exe',
                ])
            if len(appList) > 0:
                found = True
            for pid in appList:
                dhnio.Dprint(0, 'trying to stop pid %d' % pid)
                dhnio.kill_process(pid)
            if len(appList) == 0:
                if found:
                    dhnio.Dprint(0, 'DataHaven.NET stopped\n')
                else:
                    dhnio.Dprint(0, 'DataHaven.NET was not started\n')
                return 0
            total_count += 1
            if total_count > 10:
                dhnio.Dprint(0, 'some DataHaven.NET process found, but can not stop it\n')
                return 1
            time.sleep(1)            
    def wait_than_kill(x):
        dhnio.Dprint(0, 'wait_than_kill')
        total_count = 0
        #while True:
        def _try():
            dhnio.Dprint(0, '_try')
            appList = dhnio.find_process([
                'dhnmain.exe',
                'dhnview.exe',
                'dhnbackup.exe',
                'dhntester.exe',
                'dhnstarter.exe',
                ])
            dhnio.Dprint(0, 'appList:' + str(appList))
            if len(appList) == 0:
                dhnio.Dprint(0, 'finished')
                reactor.stop()
                do_uninstall()
                return 0
            total_count += 1
            dhnio.Dprint(0, '%d' % total_count)
            if total_count > 10:
                dhnio.Dprint(0, 'not responding')
                ret = kill()
                reactor.stop()
                if ret == 0:
                    do_uninstall()
                return ret
            reactor.callLater(1, _try)
        _try()
#            time.sleep(1)
    appList = dhnio.find_process([
        'dhnmain.exe',
        'dhnview.exe',
        'dhnbackup.exe',
        'dhntester.exe',
        'dhnstarter.exe',
        ])
    if len(appList) == 0:
        dhnio.Dprint(0, 'uninstalling DataHaven.NET ...   ')
        do_uninstall()
        return 0
    dhnio.Dprint(0, 'found DataHaven.NET processes ...   ')
    try:
        url = webcontrol._PAGE_ROOT+'?action=exit'
        run_url_command(url).addCallback(wait_than_kill)
        #reactor.addSystemEventTrigger('before', 'shutdown', do_uninstall)
        reactor.run()
        return 0
    except:
        dhnio.DprintException()
        ret = kill()
        if ret == 0:
            do_uninstall()
        return ret
    


#def cmd_msg(opts, args, overDict):
#    if len(dhnio.find_process([
#            'dhnmain.exe', 
#            'dhnmain.py', 
#            'dhn.py', 
#            '/usr/bin/python /usr/bin/datahaven' ])) > 0:
#        dhnio.Dprint(2, 'dhnmain.main DHN already running. EXIT.')
#        return 1
#    idurl = args[1]
#    text = ' '.join(args[2:])
#    dhnio.Dprint(2, 'dhnmain.cmd_msg to: ' + idurl)
#    dhnio.Dprint(2, 'dhnmain.cmd_msg text:')
#    dhnio.Dprint(0, text)
#    import message
#    try:
#        from twisted.internet import reactor
#    except:
#        dhnio.DprintException()
#        sys.exit('Error initializing twisted reactor in dhnmain.py\n')
#
#    def _send():
#        dhnio.Dprint(2, 'dhnmain.cmd_msg._send')
#        msgbody = message.MakeMessage(idurl, 'dhnmain short message', text)
#        message.SendMessage(idurl, msgbody)
#        message.SaveMessage(msgbody)
#
#    dhnio.Dprint(2, 'dhnmain.cmd_msg want to import dhninit')
#    import dhninit
#    dhninit.initDoneFunc = _send
#
#    UI = ''
#    dhnio.Dprint(2, 'dhnmain.cmd_msg want to call dhninit.run("%s")' % UI)
#    dhninit.run(UI, opts, args, overDict)
#    dhnio.Dprint(2, 'dhnmain.cmd_msg will call reactor.run()')
#    reactor.run()
#    return 0
#
#
#def cmd_tc(opts, args, overDict):
#    import lib.dhnio as dhnio
#    import lib.settings as settings
#    import lib.transport_control as transport_control
#    try:
#        from twisted.internet import reactor
#    except:
#        dhnio.DprintException()
#        sys.exit('Error initializing twisted reactor in dhnmain.py\n')
#    if overDict:
#        settings.override_dict(overDict)
#    settings.init()
#    if args[1] == 'init':
#        dhnio.Dprint(2, 'dhnmain.cmd_tc will call transport_control.init()')
#        transport_control.init()
#        reactor.run()
#    elif args[1] == 'ping':
#        from twisted.internet import task
#        import lib.misc as misc
#        import lib.dhnpacket as dhnpacket
#        import lib.packetid as packetid
#        import lib.commands as commands
#        import lib.contacts as contacts
#        idurl = args[2]
#        if not idurl.startswith('http://'):
#            idurl = misc.username2idurl(idurl)
#        interval = float(args[3])
#        dhnio.Dprint(2, 'dhnmain.cmd_tc want to ping %s' % idurl)
#        def _loop():
#            dhnio.Dprint(6, 'dhnmain.cmd_tc._loop')
#            LocalIdentity = misc.getLocalIdentity()
#            data = LocalIdentity.serialize()
#            packet = dhnpacket.dhnpacket(
#                commands.Identity(),
#                misc.getLocalID(),
#                misc.getLocalID(),
#                packetid.UniqueID(),
#                data,
#                idurl,)
#            transport_control.outbox(packet, True)
#            del packet
#        def _init_cb():
#            dhnio.Dprint(4, 'dhnmain.cmd_tc._init_cb')
#            t = task.LoopingCall(_loop)
#            t.start(interval)
#        contacts.init()
#        transport_control.init(_init_cb)
#        reactor.run()
#    else:
#        dhnio.Dprint(2, 'dhnmain.cmd_tc ERROR wrong command line arguments')
#        return 2
#    return 0
#
#
#def cmd_tcp(opts, args, overDict):
#    import lib.dhnio as dhnio
#    import lib.transport_tcp as transport_tcp
#    try:
#        from twisted.internet import reactor
#    except:
#        dhnio.DprintException()
#        sys.exit('Error initializing twisted reactor in dhnmain.py\n')
#    if args[1] == 'receive':
#        port = args[2]
#        dhnio.Dprint(2, 'dhnmain.cmd_tcp receive on port ' + port)
#        transport_tcp.receive(port)
#        reactor.run()
#    elif args[1] == 'send':
#        host = args[2]
#        port = args[3]
#        filename = args[4]
#        dhnio.Dprint(2, 'dhnmain.cmd_tcp send to %s:%s filename=[%s] ' % (host, port, filename))
#        def _send(x):
#            dhnio.Dprint(2, 'dhnmain.cmd_tcp result=[%s]' % str(x))
#            reactor.stop()
#        r = transport_tcp.send(filename, host, port)
#        r.addBoth(_send)
#        reactor.run()
#    else:
#        dhnio.Dprint(2, 'dhnmain.cmd_tcp ERROR wrong command line arguments')
#        return 2
#    return 0
#
#
#def cmd_q2q(opts, args, overDict):
#    import lib.dhnio as dhnio
#    import lib.settings as settings
#    import lib.transport_q2q as transport_q2q
#    try:
#        from twisted.internet import reactor
#    except:
#        dhnio.DprintException()
#        sys.exit('Error initializing twisted reactor in dhnmain.py\n')
#    if overDict:
#        settings.override_dict(overDict)
#    settings.init()
#    if args[1] == 'register':
#        userhost = args[2]
#        password = args[3]
#        dhnio.Dprint(2, 'dhnmain.cmd_q2q register new user ' + userhost)
#        def init_callback(x):
#            dhnio.Dprint(4, 'dhnmain.cmd_q2q.init_callback: ' + str(x))
#            transport_q2q.register(userhost, password).addBoth(lambda x: reactor.stop())
#        transport_q2q.init(False).addBoth(init_callback)
#        reactor.run()
#    elif args[1] == 'receive':
#        dhnio.Dprint(2, 'dhnmain.cmd_q2q receive')
#        def init_callback(x):
#            dhnio.Dprint(4, 'dhnmain.cmd_q2q.init_callback: ' + str(x))
#            transport_q2q.receive()
#        transport_q2q.init(False).addBoth(init_callback)
#        reactor.run()
#    elif args[1] == 'send':
#        to_userhost = args[2]
#        filename = args[3]
#        timeout = None
#        if len(args) > 4:
#            timeout = int(args[4])
#        dhnio.Dprint(2, 'dhnmain.cmd_q2q send to %s file %s' % (to_userhost, filename))
#        def init_callback(x):
#            dhnio.Dprint(4, 'dhnmain.cmd_q2q.init_callback: ' + str(x))
#            if timeout:
#                t = LoopingCall(transport_q2q.send, to_userhost, filename)
#            else:
#                transport_q2q.send(to_userhost, filename).addBoth(lambda x: reactor.stop())
#        transport_q2q.init(False).addBoth(init_callback)
#        reactor.run()
#    elif args[1] == 'clear':
#        transport_q2q.clear_local_db(settings.Q2QDir())
#    else:
#        dhnio.Dprint(2, 'dhnmain.cmd_tcp ERROR wrong command line arguments')
#        return 2
#    return 0

