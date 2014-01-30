#!/usr/bin/python
#dhn.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

import os
import sys
import platform


def windows_and_frozen():
    if platform.uname()[0] != 'Windows':
        # return False
        # under Linux we have same problem too ...
        # I have no idea!
        return True

    #http://www.py2exe.org/index.cgi/HowToDetermineIfRunningFromExe
    import imp
    return  (hasattr(sys, "frozen") or # new py2exe
            hasattr(sys, "importers") or# old py2exe
            imp.is_frozen("__main__")) # tools/freeze



if __name__ == "__main__":
    # to be able to use "tail -f <log file>" command

#    OriginalSTDOUT = None
#    if platform.uname()[0] == 'Linux':
#        OriginalSTDOUT = sys.stdout
#        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    # DHN use py2exe to build binaries under Windows, but it wont finish correctly!
    # After finishing all processes dhnmain.exe still working and eat 50% CPU! - it wont stop.
    # But if running from command line - it gives no problems.
    # It seems CSpace reactor makes some conflicts with twisted reactor.
    # However all threads are finished correctly - really strange thing.
    # TODO: I definately should find where is the problem here.
    # But let's take this for now - it is working.
    
    how_to_stop = windows_and_frozen()
    
    #---START THE MAIN CODE---
    import p2p.dhnmain
    ret = p2p.dhnmain.main()
    
#    if OriginalSTDOUT is not None:
#        sys.stdout = OriginalSTDOUT
    
    if how_to_stop:
        os._exit(ret)
    else:
        sys.exit(ret)

