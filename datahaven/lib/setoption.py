
import sys
if len(sys.argv) < 4:
    print 'setoption.py <base dir path> <full option name> <value>'
    sys.exit(1)

baseDir = sys.argv[1]
key = sys.argv[2]
value = ' '.join(sys.argv[3:])

import settings
settings.init(baseDir)
settings.uconfig().set(key, value)
settings.uconfig().update()
