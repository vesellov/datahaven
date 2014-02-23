#!/usr/bin/python
#diskusage.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#

import os
import time
import glob

import dhnio
import settings
import diskspace

if dhnio.Windows():
    import win32api
    import win32file

#------------------------------------------------------------------------------ 

# return free space in bytes, total space in bytes
def GetWinDriveSpace(drive): 
    try:
        sectorsPerCluster, bytesPerSector, numFreeClusters, totalNumClusters = win32file.GetDiskFreeSpace(drive + ":\\")
        sectorsPerCluster = long(sectorsPerCluster)
        bytesPerSector = long(bytesPerSector)
        numFreeClusters = long(numFreeClusters)
        totalNumClusters = long(totalNumClusters)
    except:
        return None, None
    return float(numFreeClusters * sectorsPerCluster * bytesPerSector), float(totalNumClusters * sectorsPerCluster * bytesPerSector)

# return free space in bytes, total space in bytes
def GetLinuxDriveSpace(path): 
    try:
        s = os.statvfs(str(path))
        # free, total = s.f_bsize*(s.f_blocks-s.f_bavail), s.f_bsize * s.f_bavail 
        # free, total = float(s.f_bsize * s.f_bavail), float(s.f_bsize * s.f_blocks)
        free, total = float(s.f_frsize * s.f_bavail), float(s.f_bsize * s.f_blocks) 
        return free, total
    except:
        return None, None
#    if free > total:
#        return total, free
#    else:
#        return free, total

def GetDriveSpace(path):
    if dhnio.Windows():
        drive = os.path.abspath(path)[0]
        if os.path.isdir(drive+':'):
            # the drive the data directory is on, ie C
            return GetWinDriveSpace(drive)
        else:
            return None, None
    else:
        # on linux the mount points can make a directory be off a different disk than root
        return GetLinuxDriveSpace(path)

def SumFileSizes(fileList):
    fileSizeTotal = 0
    for filename in fileList:
        try:
            fileSizeTotal += os.path.getsize(filename)
        except:
            pass
    return fileSizeTotal

def GetOurTempFileSizeTotal(tempDirectory):
    ourFileMasks = ['*-Data', '*-Parity', '*dhn*', '*.controloutbox', 'newblock-*', '*.backup']
    ourFileSizes = 0
    for mask in ourFileMasks:
        ourFileSizes += SumFileSizes(glob.glob(os.path.join(tempDirectory, mask)))
    return ourFileSizes

def OkToShareSpace(desiredSharedSpaceMB):
    # make sure a user really has the space they claim they want to share
    dataDir = settings.getCustomersFilesDir()
    dataDriveFreeSpace, dataDriveTotalSpace = GetDriveSpace(dataDir)
    if dataDriveFreeSpace is None:
        return False
    currentlySharedSpace = GetDirectorySize(dataDir)
    if (currentlySharedSpace + dataDriveFreeSpace/(1024*1024)) < desiredSharedSpaceMB:
        return False
    else:
        return True
    
def GetDirectorySize(directoryPath):
    return dhnio.getDirectorySize(directoryPath)/(1024*1024)

#------------------------------------------------------------------------------ 

def main():
    dataDir = settings.getCustomersFilesDir()
    tempDir = settings.TempDir()
    dataDriveFreeSpace = 0
    dataDriveTotalSpace = 0
    tempDriveFreeSpace = 0
    tempDriveTotalSpace = 0

    dataDriveFreeSpace, dataDriveTotalSpace = GetDriveSpace(dataDir)
    tempDriveFreeSpace, tempDriveTotalSpace = GetDriveSpace(tempDir)

    print "data dir =", dataDir
    print "tep dir =", tempDir
    print "data dir: " + str(dataDriveFreeSpace/(1024*1024)) +"MB free/" + str(dataDriveTotalSpace/(1024*1024)) +"MB total"
    print "temp dir: " + str(tempDriveFreeSpace/(1024*1024)) +"MB free/" + str(tempDriveTotalSpace/(1024*1024)) +"MB total"

    print time.time()
    print "our temp files: " + str(GetOurTempFileSizeTotal(tempDir)/(1024*1024)) + "MB"
    ourFileMasks = ['*-Data', '*-Parity', '*dhn*', '*.controloutbox', 'newblock-*', '*.backup']
    for mask in ourFileMasks:
        print time.time()
        print mask + "=" + str(SumFileSizes(glob.glob(os.path.join(tempDir, mask))))

    print time.time()

    GetDirectorySize(dataDir)

    ds = diskspace.DiskSpace()
    print ds.getValueBest(dataDriveFreeSpace)

    print "at OkToShareSpace ..."
    print "ok to share 100MB - should be true"
    print OkToShareSpace(100)
    print "ok to share 12345678MB - should be false"
    print OkToShareSpace(12345678)


if __name__ == '__main__':
    main()