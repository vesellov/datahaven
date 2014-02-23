#!/usr/bin/python
#backup_fs.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#


import os
import sys
import stat
import cStringIO

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
        
import lib.misc as misc
import lib.settings as settings        
import lib.packetid as packetid
# import lib.dirsize as dirsize

#------------------------------------------------------------------------------ 

INFO_KEY = 'i'
UNKNOWN = -1
FILE = 0
DIR = 1
PARENT = 2
TYPES = {UNKNOWN:   'UNKNOWN',
         FILE:      'FILE',
         DIR:       'DIR',
         PARENT:    'PARENT',} 

#------------------------------------------------------------------------------ 

_FileSystemIndexByName = {}
_FileSystemIndexByID = {}
_ItemsCount = 0
_FilesCount = 0
_SizeFiles = 0
_SizeBackups = 0

def fs():
    global _FileSystemIndexByName
    return _FileSystemIndexByName

def fsID():
    global _FileSystemIndexByID
    return _FileSystemIndexByID

def counter():
    global _ItemsCount
    return _ItemsCount

def numberfiles():
    global _FilesCount
    return _FilesCount

def sizefiles():
    global _SizeFiles
    return _SizeFiles

def sizebackups():
    global _SizeBackups
    return _SizeBackups

#------------------------------------------------------------------------------ 

def init():
    dhnio.Dprint(4, 'backup_fs.init')
    # fs()[settings.BackupIndexFileName()] = -1
    # fsID()[-1] = FSItemInfo(settings.BackupIndexFileName(), '-1', FILE)
    # backup_fs.SetFile(settings.BackupIndexFileName(), settings.BackupIndexFileName())

def shutdown():
    dhnio.Dprint(4, 'backup_fs.shutdown')

#-------------------------------------------------------------i----------------- 

class FSItemInfo():
    def __init__(self, name='', path='', typ=UNKNOWN):
        if isinstance(name, unicode):
            self.unicodename = name
        else:
            self.unicodename = unicode(name)
        self.path = path
        self.type = typ
        self.size = -1
        self.versions = {} # set()

    def name(self): 
        return self.unicodename

    def exist(self):
        return self.size != -1
    
    def set_size(self, sz):
        self.size = sz
    
    def read_stats(self, path):
        if not pathExist(path):
            self.size = -1
            return
        # if self.type in [DIR, PARENT]:
        if pathIsDir(path):
#            dirsize.ask(path, callback=lambda pth, sz, arg: self.set_size(sz))
            self.size = -1
            return
        try:
            s = os.stat(path)
        except:
            try:
                s = os.stat(path.decode('utf-8'))
            except:
                dhnio.DprintException()
                self.size = -1
                return
        self.size = long(s.st_size)
        
    def read_versions(self, path):
        path = portablePath(path)
        if not pathExist(path):
            return 0
        if not os.access(path, os.R_OK):
            return 0
        totalSize = 0
        for version in os.listdir(path):
            if self.get_version_info(version)[0] >= 0:
                continue
            versionSize = 0
            maxBlock = -1
            if not packetid.IsCanonicalVersion(version):
                continue
            versionpath = os.path.join(path, version)
            if not pathExist(versionpath):
                continue
            if not os.access(versionpath, os.R_OK):
                return 0
            for filename in os.listdir(versionpath):
                filepath = os.path.join(versionpath, filename)
                if not packetid.IsPacketNameCorrect(filename):
                    dhnio.Dprint(4, 'backup_fs.read_versions WARNING incorrect file name found: %s' % filepath)
                    continue
                try:
                    blockNum, supplierNum, dataORparity = filename.split('-')
                    blockNum, supplierNum = int(blockNum), int(supplierNum)
                except:
                    dhnio.Dprint(4, 'backup_fs.read_versions WARNING incorrect file name found: %s' % filepath)
                    continue
                try:
                    sz = long(os.path.getsize(filepath))
                except:
                    dhnio.DprintException()
                # add some bytes because on remote machines all packets are dhnpackets
                # so they have a header and the files size will be bigger than on local machine
                versionSize += sz + 1024   
                maxBlock = max(maxBlock, blockNum)
            self.set_version_info(version, maxBlock, versionSize)
            totalSize += versionSize
        return totalSize
        
    def add_version(self, version):
        # self.versions.add(version)
        self.versions[version] = [-1, -1] # max block num, size in bytes
        
    def set_version_info(self, version, maxblocknum, sizebytes):
        self.versions[version] = [maxblocknum, sizebytes]
        
    def get_version_info(self, version):
        return self.versions.get(version, [-1, -1])
        
    def delete_version(self, version):
        # self.versions.remove(version)
        self.versions.pop(version, None)
        
    def has_version(self, version):
        # return version in self.versions
        return self.versions.has_key(version)
    
    def any_version(self):
        return len(self.versions) > 0
    
    def list_versions(self, sorted=False, reverse=False):
        # return list(self.versions)
        if sorted:
            return misc.sorted_versions(self.versions.keys(), reverse)
        return self.versions.keys()
    
    def get_versions(self):
        return self.versions
    
    def pack_versions(self):
        out = []
        for version in self.list_versions(True):
            info = self.versions[version]
            out.append(version+':'+str(info[0])+':'+str(info[1]))
        return ' '.join(out)
    
    def unpack_versions(self, input):
        for word in input.split(' '):
            if not word.strip():
                continue
            try:
                version, maxblock, sz = word.split(':')
                maxblock, sz = int(maxblock), int(sz)
            except:
                version, maxblock, sz = word, -1, -1
            self.set_version_info(version, maxblock, sz)
        
    def serialize(self, encoding='utf-8'):
        e = self.unicodename.encode(encoding)
        return '%s %d %d %s\n%s\n' % (self.path, 
                                         self.type, 
                                         self.size,
                                         self.pack_versions(),
                                         e,)
        
    def unserialize(self, src, decoding='utf-8'):
        try:
            details, name = src.split('\n')[:2]
        except:
            raise
        if details == '' or name == '':
            raise Exception('Incorrect item format:\n%s' % src) 
        try:
            self.unicodename = name.decode(decoding)
            details = details.split(' ')
            self.path, self.type, self.size = details[:3]
            self.type, self.size = int(self.type), int(self.size)
            self.unpack_versions(' '.join(details[3:])) 
        except:
            raise

    def __repr__(self):
        return '<%s %s %d>' % (TYPES[self.type], misc.unicode_to_str_safe(self.name()), self.size)

#------------------------------------------------------------------------------ 

def portablePath(path):
    """ fix path to fit for our use:
            + do convert to absolute path
            + for Windows: + change all separators to Linux format: \\->/ \=>/
                           + convert disk letter to lower case """
    p = os.path.abspath(path)
    if not isinstance(p, unicode):
        # p = p.encode('utf-8')
        p = unicode(p)
    if dhnio.Windows():
        p = p.replace('\\', '/') # .replace('\\\\', '/')
        if len(p) >= 2 and p[1] == ':':
            p = p[0].lower() + p[1:]
    if p.endswith('/') and len(p) > 1:
        p = p.rstrip('/')
    return p # unicode(p) #.encode('utf-8')

# our own portable version of os.path.exist
def pathExist(localpath):
    if os.path.exists(localpath):
        return True
    p = portablePath(localpath)
    if os.path.exists(p):
        return True
#    if os.path.exists(p.decode('utf-8')):
#        return True
    return False

# assume localpath is exist and is absolute or raise Exception
def pathIsDir(localpath):
    # print 'pathIsDir', type(localpath), str(localpath)
    # try to use the original path
    if os.path.isdir(localpath):
        return True
    if os.path.isfile(localpath):
        return False
    # don't know... let's try portable path
    p = portablePath(localpath)
    if os.path.isdir(p):
        return True
    if os.path.isfile(p):
        return False
    # may be path is not exist at all?
    if not os.path.exists(localpath):
        return False
    if not os.path.exists(p):
        return False
    # ok, on Linux we have devices, mounts, links ...
    if dhnio.Linux():
        try:
            st = os.path.stat(localpath)
            return stat.S_ISDIR(st.st_mode)
        except:
            return False 
    # now we are in really big trouble
    raise Exception('Path not exist: %s' % p)
    return False

def pathIsDriveLetter(path):
    p = path.rstrip('/').rstrip('\\')
    if len(p) != 2:
        return False
    if p[1] != ':':
        return False
    if not p[0].isalpha():
        return False
    return True

#------------------------------------------------------------------------------ 

def MakeID(iter, startID=-1):
    id = 0
    if startID >= 0:
        id = startID
    while id in map(lambda k: '' if k == 0 else (iter[k] if isinstance(iter[k], int) else iter[k][0]), iter.keys()):
        id += 1
    return id

#------------------------------------------------------------------------------ 

def AddFile(path, read_stats=False, iter=None, iterID=None):
    # here path must be portable - only '/' allowed
    # assume path is a file, not dir
    if not os.path.isfile(path):
        raise Exception('File not exist')
    parts = portablePath(path).split('/')
    if not iter:
        iter = fs()
    if not iterID:
        iterID = fsID()
    resultID = ''
    # build all tree, skip the last part
    for i in range(len(parts)-1):
        name = parts[i]
        if not name:
            continue
        p = '/'.join(parts[:i+1])
        if not pathIsDir(p):
            raise Exception('Directory not exist: %s' % str(p))
        if not iter.has_key(name):
            # made a new ID for this folder, ID starts from 0. new folders will get the last ID +1 
            # or it may find a free place in the middle, if some folders or files were removed before
            # this way we try to protect the files and directories names. we store index in the encrypted files
            id = MakeID(iter)
            # build a unique backup id for that file including all indexed ids
            resultID += '/' + str(id)
            # make new sub folder 
            ii = FSItemInfo(name, resultID.lstrip('/'), PARENT)
            if read_stats:
                ii.read_stats(p)
            # we use 0 key as decimal value, all files and folders are strings - no conflicts possible 0 != '0'
            iter[ii.name()] = {0: id}
            # also save index from opposite side
            iterID[id] = {INFO_KEY: ii}
        else:
            # get an existing ID from the index
            id = iter[name][0]
            # go down into the existing forest
            resultID += '/' + str(id)
        # move down to the next level
        iter = iter[name]
        iterID = iterID[id]
    # the last part of the path is a filename
    filename = parts[-1] 
    # make an ID for the filename
    id = MakeID(iter)
    resultID += '/' + str(id)
    ii = FSItemInfo(filename, resultID, FILE)
    if read_stats:
        ii.read_stats(path)
    iter[ii.name()] = id
    iterID[id] = ii
    # finally make a complete backup id - this a relative path to the backed up file
    return resultID.lstrip('/'), iter, iterID

def AddDir(path, read_stats=False, iter=None, iterID=None):
    parts = portablePath(path).split('/')
    if not iter:
        iter = fs()
    if not iterID:
        iterID = fsID()
    resultID = ''
    for i in range(len(parts)):
        name = parts[i]
        if not name:
            continue
        p = '/'.join(parts[:i+1])
        if not pathIsDir(p):
            raise Exception('Directory not exist: %s' % str(p))
        if not iter.has_key(name):
            id = MakeID(iter)
            resultID += '/' + str(id)
            ii = FSItemInfo(name, resultID.lstrip('/'), PARENT)
            if read_stats:
                ii.read_stats(p) 
            iter[ii.name()] = {0: id}
            iterID[id] = {INFO_KEY: ii}
        else:
            id = iter[name][0]
            resultID += '/' + str(id)
        iter = iter[name]
        iterID = iterID[id]
        if i == len(parts) - 1:
            iterID[INFO_KEY].type = DIR
    return resultID.lstrip('/'), iter, iterID

def AddLocalPath(localpath, read_stats=False):
    def recursive_read_dir(path, path_id, iter, iterID):
        c = 0
        lastID = -1
        path = portablePath(path)
        if not os.access(path, os.R_OK):
            return c
        for localname in os.listdir(path):
            p = os.path.join(path, localname)  # .encode("utf-8")
            name = unicode(localname) 
            if pathIsDir(p):
                if not iter.has_key(name):
                    id = MakeID(iter, lastID)
                    ii = FSItemInfo(name, path_id+'/'+str(id), DIR)
                    iter[ii.name()] = {0: id}
                    if read_stats:
                        ii.read_stats(p)
                    iterID[id] = {INFO_KEY: ii}
                    lastID = id
                else:
                    id = iter[name][0]
                c += recursive_read_dir(p, path_id+'/'+str(id), iter[name], iterID[id])
            else:
                id = MakeID(iter, lastID)
                ii = FSItemInfo(name, path_id+'/'+str(id), FILE)
                if read_stats:
                    ii.read_stats(p)
                iter[ii.name()] = id
                iterID[id] = ii
                c += 1
                lastID = id
        return c    
    localpath = portablePath(localpath) 
    if pathIsDir(localpath):
        path_id, iter, iterID = AddDir(localpath, read_stats)
        num = recursive_read_dir(localpath, path_id, iter, iterID)
        return path_id, iter, iterID, num
    else:
        path_id, iter, iterID = AddFile(localpath, read_stats)
        return path_id, iter, iterID, 1
    return None, None, None, 0

#------------------------------------------------------------------------------ 

def SetFile(item, iter=None, iterID=None):
    if iter is None:
        iter = fs()
    if iterID is None:
        iterID = fsID()
    parts = item.path.split('/')
    for j in range(len(parts)):
        id = int(parts[j])
        if j == len(parts) - 1:
            if not iter.has_key(item.name()):
                iter[item.name()] = id
                iterID[id] = item
            return True
        found = False
        for name in iter.keys():
            if name == 0:
                continue
            if isinstance(iter[name], dict):
                if iter[name][0] == id:
                    iter = iter[name]
                    iterID = iterID[id]
                    found = True
                    break
                continue
        if not found:
            return False
    return False

def SetDir(item, iter=None, iterID=None):
    if iter is None:
        iter = fs()
    if iterID is None:
        iterID = fsID()
    parts = item.path.split('/')
    itemname = item.name()
    for j in range(len(parts)):
        id = int(parts[j])
        if j == len(parts)-1:
            if not iter.has_key(itemname):
                iter[itemname] = {}
            iter[itemname][0] = int(id)
            if not iterID.has_key(id):
                iterID[id] = {}
            iterID[id][INFO_KEY] = item
            return True
        found = False
        for name in iter.keys():
            if name == 0:
                continue
            if isinstance(iter[name], int):
                continue
            if isinstance(iter[name], dict):
                if iter[name][0] == id:
                    iter = iter[name]
                    iterID = iterID[id]
                    found = True
                    break
                continue
            raise Exception('Wrong data type in the index')
        if not found:
            return False
    return False

#------------------------------------------------------------------------------ 

def WalkByPath(path, iter=None):
    if iter is None:
        iter = fs()
    path_id = ''
    parts = portablePath(path).split('/')
    for j in range(len(parts)):
        name = parts[j]
        if not iter.has_key(name):
            return None
        if isinstance(iter[name], dict):
            if not iter[name].has_key(0):
                raise Exception('Error, file or directory ID missed in the index')
            path_id += '/' + str(iter[name][0])
        elif isinstance(iter[name], int):
            if j != len(parts) - 1:
                return None
            path_id += '/' + str(iter[name])
        else:
            raise Exception('Wrong data type in the index')
        if j == len(parts) - 1:
            return iter[name], path_id.lstrip('/')
        iter = iter[name]
    return None   

def WalkByID(pathID, iterID=None):
    if iterID is None:
        iterID = fsID()
    if pathID is None:
        return None
    if pathID.strip() == '':
        return iterID, ''
    path = ''
    parts = pathID.strip('/').split('/')
    for j in range(len(parts)):
        try:
            id = int(parts[j])
        except:
            return None
        if not iterID.has_key(id):
            return None
        if isinstance(iterID[id], dict):
            if not iterID[id].has_key(INFO_KEY):
                raise Exception('Error, directory info missed in the index')
            name = iterID[id][INFO_KEY].name()
            if pathIsDriveLetter(name):
                path += name
            else:
                path += '/' + name 
        elif isinstance(iterID[id], FSItemInfo):
            if j != len(parts) - 1:
                return None
            path += '/' + iterID[id].name()
        else:
            raise Exception('Wrong data type in the index')
        if j == len(parts) - 1:
            return iterID[id], path
        iterID = iterID[id]
    return None

#------------------------------------------------------------------------------ 

def DeleteByID(pathID, iter=None, iterID=None):
    if iter is None:
        iter = fs()
    if iterID is None:
        iterID = fsID()
    path = ''
    parts = pathID.strip('/').split('/')
    for j in range(len(parts)):
        id = int(parts[j])
        if not iterID.has_key(id):
            return None
        if isinstance(iterID[id], dict):
            if not iterID[id].has_key(INFO_KEY):
                raise Exception('Error, directory info missed in the index')
            name = iterID[id][INFO_KEY].name()
            if pathIsDriveLetter(name):
                path += name
            else:
                path += '/' + name 
        elif isinstance(iterID[id], FSItemInfo):
            name = iterID[id].name()
            path += '/' + name
            if j != len(parts) - 1:
                return None
        else:
            raise Exception('Wrong data type in the index')
        if not iter.has_key(name):
            raise Exception('Can not found target name in the index')
        if j == len(parts) - 1:
            iterID.pop(id)
            iter.pop(name)
            return path
        iterID = iterID[id]
        iter = iter[name]
    return None
    
def DeleteByPath(path, iter=None, iterID=None):
    if iter is None:
        iter = fs()
    if iterID is None:
        iterID = fsID()
    path_id = ''
    parts = portablePath(path).split('/')
    for j in range(len(parts)):
        name = parts[j]  # .encode('utf-8') # parts[j]
        if not iter.has_key(name):
            return None
        if isinstance(iter[name], dict):
            if not iter[name].has_key(0):
                raise Exception('Error, directory ID missed in the index')
            id = iter[name][0]
            path_id += '/' + str(id)
        elif isinstance(iter[name], int):
            id = iter[name]
            path_id += '/' + str(id)
            if j != len(parts) - 1:
                return None
        else:
            raise Exception('Wrong data type in the index')
        if not iterID.has_key(id):
            raise Exception('Can not found target ID in the index')
        if j == len(parts) - 1:
            iter.pop(name)
            iterID.pop(id)
            return path_id.lstrip('/')
        iter = iter[name]
        iterID = iterID[id]
    return None

def DeleteBackupID(backupID):
    pathID, versionName = packetid.SplitBackupID(backupID)
    if pathID is None:
        return False
    info = GetByID(pathID)
    if info is None:
        return False
    if not info.has_version(versionName):
        dhnio.Dprint(4, 'backup_fs.DeleteBackupID WARNING %s do not have version %s' % (pathID, versionName))
        return False 
    info.delete_version(versionName)
    return True
    
#------------------------------------------------------------------------------ 

def ToID(localPath, iter=None):
    iter_and_id = WalkByPath(localPath, iter)
    if iter_and_id is None:
        return None
    return iter_and_id[1]

def ToPath(pathID, iterID=None):
    """ get a full relative path from ID 
    /0/0/12/1 -> /home/veselin/Documents/somefile.txt
    return None if that path not exist
    """
    iter_and_path = WalkByID(pathID, iterID=None)
    if iter_and_path is None:
        return None
    return iter_and_path[1]

#------------------------------------------------------------------------------ 

def GetByID(pathID):
    iter_and_path = WalkByID(pathID)
    if iter_and_path is None:
        return None
    if isinstance(iter_and_path[0], dict):
        return iter_and_path[0][INFO_KEY]
    return iter_and_path[0]

def GetByPath(path):
    path_id = ToID(path)
    if path_id is None:
        return None
    return GetByID(path_id)

#------------------------------------------------------------------------------ 

def IsDir(path):
    iter_and_id = WalkByPath(path)
    if iter_and_id is None:
        return False
    iter, pathid = iter_and_id
    if not isinstance(iter, dict):
        return False
    if not iter.has_key(0):
        raise Exception('Error, directory ID missed in the index')
    return True    

def IsFile(path):
    iter_and_id = WalkByPath(path)
    if iter_and_id is None:
        return False
    iter, pathid = iter_and_id
    if not isinstance(iter, int):
        return False
    return True    

def IsDirID(pathID):
    iter_and_path = WalkByID(pathID)
    if iter_and_path is None:
        return False
    iterID, path = iter_and_path
    if isinstance(iterID, FSItemInfo):
        return False
    if not iterID.has_key(INFO_KEY):
        raise Exception('Error, directory info missed in the index')
    return True

def IsFileID(pathID):
    iter_and_path = WalkByID(pathID)
    if iter_and_path is None:
        return False
    iterID, path = iter_and_path
    if not isinstance(iterID, FSItemInfo):
        return False
    return True
    

def Exists(path):
    iter_and_id = WalkByPath(path)
    if iter_and_id is None:
        return False
    return True    

def ExistsID(pathID):
    iter_and_path = WalkByID(pathID)
    if iter_and_path is None:
        return False
    return True   

def ExistsBackupID(backupID):
    pathID, version = packetid.SplitBackupID(backupID)
    if not pathID:
        return False
    iter_and_path = WalkByID(pathID)
    if iter_and_path is None:
        return False
    iter, path = iter_and_path
    return iter.has_version(version)

#------------------------------------------------------------------------------ 

def HasChilds(path):
    iter_and_id = WalkByPath(path)
    if iter_and_id is None:
        return False
    iter, pathid = iter_and_id
    if not isinstance(iter, dict):
        return False
    if not iter.has_key(0):
        raise Exception('Error, directory ID missed in the index')
    return len(iter) > 1

def HasChildsID(pathID):
    iter_and_path = WalkByID(pathID)
    if iter_and_path is None:
        return False
    iterID, path = iter_and_path
    if not isinstance(iterID, dict):
        return False
    if not iterID.has_key(INFO_KEY):
        raise Exception('Error, directory info missed in the index')
    return len(iterID) > 1
    
#------------------------------------------------------------------------------ 

def TraverseByID(callback, iterID=None): 
    '''     call callback(path_id, path, info) for every item in the index    '''
    def recursive_traverse(i, path_id, path, cb):
        name = None
        if path not in ['', '/']:
            path += '/'
        if isinstance(i, FSItemInfo):
            cb(path_id, path, i)
            return
        if i.has_key(INFO_KEY):
            name = i[INFO_KEY].name()
            path += name
            cb(path_id, path, i[INFO_KEY])
        for id in i.keys():
            if id == INFO_KEY:
                continue
            if isinstance(i[id], dict):
                recursive_traverse(i[id], path_id+'/'+str(id) if path_id else str(id), path, cb)
            elif isinstance(i[id], FSItemInfo):
                cb(path_id+'/'+str(id) if path_id else str(id), path+'/'+i[id].name() if path else i[id].name(), i[id])
            else:
                raise Exception('Error, wrong item type in the index')
    if iterID is None:
        iterID = fsID()
    startpth = '' if dhnio.Windows() else '/'
    recursive_traverse(iterID, '', startpth, callback)
    
def TraverseByIDSorted(callback, iterID=None): 
    def recursive_traverse(i, path_id, path, cb):
        name = None
        if path not in ['', '/']:
            path += '/'
        if i.has_key(INFO_KEY):
            name = i[INFO_KEY].name()
            path += name
            cb(path_id, path, i[INFO_KEY])
        dirs = []
        files = []
        for id in i.keys():
            if id == INFO_KEY:
                continue
            if isinstance(i[id], dict):
                dirs.append((id, path+'/'+i[id][INFO_KEY].name() if path else i[id][INFO_KEY].name()))
            elif isinstance(i[id], FSItemInfo):
                files.append((id, path+'/'+i[id].name() if path else i[id].name()))
            else:
                raise Exception('Error, wrong item type in the index')   
        dirs.sort(key=lambda e: e[1])
        files.sort(key=lambda e: e[1])
        for id, pth in dirs:
            recursive_traverse(i[id], path_id+'/'+str(id) if path_id else str(id), path, cb)
        for id, pth in files:
            cb(path_id+'/'+str(id) if path_id else str(id), pth, i[id])
        del dirs
        del files
    if iterID is None:
        iterID = fsID()
    startpth = '' if dhnio.Windows() else '/'
    recursive_traverse(iterID, '', startpth, callback)
    
def IterateIDs(iterID=None):
    # iterator is (pathID, localPath, item)
    if iterID is None:
        iterID = fsID()
    def recursive_iterate(i, path_id, path):
        name = None
        if path not in ['', '/']:
            path += '/'
        if i.has_key(INFO_KEY):
            name = i[INFO_KEY].name()
            path += name
            yield path_id, path, i[INFO_KEY]
        for id in i.keys():
            if id == INFO_KEY:
                continue
            if isinstance(i[id], dict):
                for t in recursive_iterate(i[id], path_id+'/'+str(id) if path_id else str(id), path): 
                    yield t
            elif isinstance(i[id], FSItemInfo):
                yield path_id+'/'+str(id) if path_id else str(id), path+'/'+i[id].name(), i[id]
            else:
                raise Exception('Error, wrong item type in the index')        
    startpth = '' if dhnio.Windows() else '/'
    return recursive_iterate(iterID, '', startpth)    

#------------------------------------------------------------------------------ 

def ListByPath(path, iter=None):
    path = portablePath(path)
    iter_and_id = WalkByPath(path, iter)
    if iter_and_id is None:
        return None
    result = []
    iter, path_id = iter_and_id
    if isinstance(iter, int):
        return [(path_id, path),]
    if not isinstance(iter, dict):
        raise Exception('Wrong data type in the index')
    if not iter.has_key(0):
        raise Exception('Error, directory ID missed in the index')
    for key in iter.keys():
        if key == 0:
            continue
        if isinstance(iter[key], dict):
            if not iter[key].has_key(0):
                raise Exception('Error, directory ID missed in the index')
            id = iter[key][0]
        elif isinstance(iter[key], int):
            id = iter[key]
        else:
            raise Exception('Wrong data type in the index')
        result.append((path_id+'/'+str(id), path+'/'+key))
    return result    
    
def ListByID(pathID, iterID=None):  
    iter_and_path = WalkByID(pathID, iterID)
    if iter_and_path is None:
        return None
    result = []
    iterID, path = iter_and_path
    if isinstance(iterID, FSItemInfo):
        return [(pathID, path),]
    if not isinstance(iterID, dict):
        raise Exception('Wrong data type in the index')
    if not iterID.has_key(INFO_KEY) and pathID.strip() != '':
        raise Exception('Error, directory info missed in the index')
    for id in iterID.keys():
        if id == INFO_KEY:
            continue
        if isinstance(iterID[id], dict):
            if not iterID[id].has_key(INFO_KEY):
                raise Exception('Error, directory info missed in the index')
            name = iterID[id][INFO_KEY].name()
        elif isinstance(iterID[id], FSItemInfo):
            name = iterID[id].name()
        else:
            raise Exception('Wrong data type in the index')
        result.append((pathID+'/'+str(id), path+'/'+name))
    return result    

def ListAllBackupIDs(sorted=False, reverse=False, iterID=None):
    lst = []
    def visitor(path_id, path, info):
        for version in info.list_versions(sorted, reverse):
            lst.append(str(path_id + '/' + version))
    TraverseByID(visitor)
    return lst

def ListAllBackupIDsFull(sorted=False, reverse=False, iterID=None):
    lst = []
    def visitor(path_id, path, info):
        for version in info.list_versions(sorted, reverse):
            lst.append((str(path_id + '/' + version), info.get_version_info(version), path))
    TraverseByID(visitor)
    return lst

def ListSelectedFolders(selected_dirs_ids, sorted=False, reverse=False):
    lst = []
    def visitor(path_id, path, info):
        basepathid = path_id[:path_id.rfind('/')] if path_id.count('/') else ''
        if basepathid in selected_dirs_ids: 
            lst.append((info.type, path_id, path, info.size, info.list_versions(sorted, reverse)))
        return True
    TraverseByIDSorted(visitor)
    return lst

def ListExpandedFoldersAndBackups(expanded_dirs, selected_items):
    lst = []
    backups = []
    def visitor(path_id, path, info):
        basepathid = path_id[:path_id.rfind('/')] if path_id.count('/') else ''
        if basepathid in expanded_dirs: 
            lst.append((info.type, path_id, path, info.size, info.get_versions()))
        if path_id in selected_items:
            for version in info.list_versions():
                backups.append(path_id+'/'+version)
        return True
    TraverseByIDSorted(visitor)
    return lst, backups

#------------------------------------------------------------------------------ 

def MakeLocalDir(basedir, pathID):
    if not pathIsDir(basedir):
        raise Exception('Directory not exist: %s' % basedir)
    path = os.path.join(basedir, pathID)
    if os.path.exists(path):
        if not pathIsDir(path):
            raise Exception('Can not create directory %s' % path)
    else:
        os.makedirs(path)
    return path

def DeleteLocalDir(basedir, pathID):
    if not pathIsDir(basedir):
        raise Exception('Directory not exist: %s' % basedir)
    path = os.path.join(basedir, pathID)
    if not os.path.exists(path):
        return
    if not pathIsDir(path):
        raise Exception('Error, %s is not a directory' % path)
    dhnio.rmdir_recursive(path)
    
def DeleteLocalBackup(basedir, backupID):
    count_and_size = [0, 0,]
    if not pathIsDir(basedir):
        raise Exception('Directory not exist: %s' % basedir)
    backupDir = os.path.join(basedir, backupID)
    if not pathExist(backupDir):
        return count_and_size[0], count_and_size[1]
    if not pathIsDir(backupDir):
        raise Exception('Error, %s is not a directory' % backupDir)
    def visitor(fullpath):
        if os.path.isfile(fullpath):
            count_and_size[0] += 1
            count_and_size[1] += os.path.getsize(fullpath) 
        return True
    dhnio.rmdir_recursive(backupDir, pre_callback=visitor)
    return count_and_size[0], count_and_size[1]

#------------------------------------------------------------------------------ 

def Scan():
    iterID = fsID()
    sum = [0, 0,]
    def visitor(path_id, path, info):
        info.read_stats(path)
        if info.exist():
            sum[0] += info.size
        versions_path = portablePath(os.path.join(settings.getLocalBackupsDir(), path_id))
        sum[1] += info.read_versions(versions_path)
    TraverseByID(visitor, iterID)
    return sum[0], sum[1]

def ScanID(pathID):
    iter_and_path = WalkByID(pathID)
    if not iter_and_path:
        return
    iter, path = iter_and_path
    if isinstance(iter, dict):
        if not iter.has_key(INFO_KEY):
            return
        iter = iter[INFO_KEY]
    iter.read_stats(path)
    iter.read_versions(portablePath(os.path.join(settings.getLocalBackupsDir(), pathID)))
    
def Calculate():
    global _SizeFiles
    global _SizeBackups
    global _ItemsCount
    global _FilesCount
    _ItemsCount = 0
    _FilesCount = 0
    _SizeFiles = 0
    _SizeBackups = 0
    def recursive_calculate(i):
        global _SizeFiles
        global _SizeBackups
        global _ItemsCount
        global _FilesCount
        folder_size = 0
        for id in i.keys():
            if id == INFO_KEY:
                continue
            if isinstance(i[id], FSItemInfo):
                if i[id].exist():
                    folder_size += i[id].size
                if i[id].type == FILE:
                    _FilesCount += 1
                    if i[id].exist():
                        _SizeFiles += i[id].size
                for version in i[id].list_versions():
                    versionSize = i[id].get_version_info(version)[1]
                    if versionSize > 0:
                        _SizeBackups += versionSize 
                _ItemsCount += 1
            elif isinstance(i[id], dict):
                sub_folder_size = recursive_calculate(i[id])
                if sub_folder_size != -1:
                    folder_size += sub_folder_size
            else:
                raise Exception('Error, wrong item type in the index')
        if i.has_key(INFO_KEY):
            i[INFO_KEY].size = folder_size
            if i[INFO_KEY].type == FILE:
                _FilesCount += 1
                if i[INFO_KEY].exist():
                    _SizeFiles += i[INFO_KEY].size
            for version in i[INFO_KEY].list_versions():
                versionSize = i[INFO_KEY].get_version_info(version)[1]
                if versionSize > 0:
                    _SizeBackups += versionSize 
            _ItemsCount += 1
        return folder_size
    return recursive_calculate(fsID())

def Calculate2(iterID=None):
    if iterID is None:
        iterID = fsID()
    def recursive_calculate(i):
        folder_size = 0
        for id in i.keys():
            if id == INFO_KEY:
                continue
            if isinstance(i[id], FSItemInfo):
                if i[id].exist():
                    folder_size += i[id].size
            elif isinstance(i[id], dict):
                sub_folder_size = recursive_calculate(i[id])
                if sub_folder_size != -1:
                    folder_size += sub_folder_size
            else:
                raise Exception('Error, wrong item type in the index')
        if i.has_key(INFO_KEY):
            i[INFO_KEY].size = folder_size
        return folder_size
    return recursive_calculate(iterID)
    
#------------------------------------------------------------------------------ 

def Clear():
    fs().clear()
    fsID().clear()

def Serialize(iterID=None):
    result = cStringIO.StringIO()
    cnt = [0]
    def cb(path_id, path, info):
        result.write(info.serialize())
        cnt[0] += 1
    TraverseByID(cb, iterID)
    src = result.getvalue()
    result.close()
    dhnio.Dprint(6, 'backup_fs.Serialize done with %d indexed files' % cnt[0])
    return src

def Unserialize(input, iter=None, iterID=None):
    count = 0
    while True:
        src = input.readline() + input.readline() # 2 times because we take 2 lines for every item
        if src.strip() == '':
            break
        item = FSItemInfo()
        item.unserialize(src)
        if item.type == FILE:
            if not SetFile(item, iter, iterID):
                raise Exception('Can not put item into the tree: %s' % str(item))
        elif item.type == DIR or item.type == PARENT:
            if not SetDir(item, iter, iterID):
                raise Exception('Can not put item into the tree: %s' % str(item))
        else:
            raise Exception('Incorrect entry type')
        count += 1
    dhnio.Dprint(6, 'backup_fs.Unserialize done with %d indexed files' % count)
    return count

#------------------------------------------------------------------------------ 

def main():
    import pprint
#    dhnio.init()
#    for path in sys.argv[1:]:
#        print path, AddLocalPath(path, True)
#
#    for pathID, localPath, itemInfo in IterateIDs():
#        print pathID, localPath, itemInfo
#        
#    print IsDirID('0/0/0')

    # pprint.pprint(fs())
    # pprint.pprint(fsID())
    # s = Serialize()
    # print s
#    open('index', 'w').write(s)
#    for id, path in ListByID(''):
#        pprint.pprint(ListByID(id))
#    fs().clear()
#    fsID().clear()
#    inp = cStringIO.StringIO(s)
#    Unserialize(inp)
#    inp.close()
#    pprint.pprint(fs())
#    pprint.pprint(fsID())
    
    # print GetPath('/0/0/0/1/31/12')
    # print GetID('C:/.Veselin/diplom/Social/Editor/type 5.vsd.aut')
    # print WalkByPath('C:/.Veselin/diplom/Social/Editor/type 5.vsd.aut')
    # print WalkByID('/0/0/0/1/31/12')
    # print IsDir('C:')
    # DeleteByID('/0')
    # print ListByID('')
    # print 'NEW C:/.Veselin/diplom/', AddLocalPath('C:/.Veselin/diplom/')
    # print ListByID('')
    # pprint.pprint(ListByPath('c:\.Veselin/diplom/'))
    # print DeleteByID('0/0/0/0')
    # print DeleteByPath('C:/.Veselin/diplom/Social')
    # pprint.pprint(fs())
    # pprint.pprint(ListByPath('C:/.Veselin/diplom/Social/Editor'))
    
    # iter = fs()['c:']['work']['modnamama']['_katalog']
    # print map(lambda k: iter[k][0] if isinstance(iter, dict) else '', iter.keys())
    # pprint.pprint( ListLocalFolder(sys.argv[1]) )
    # print ListLocalFolder(sys.argv[1])

if __name__ == '__main__':
    main()

    
