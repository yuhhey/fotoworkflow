import sys
import HDRList
import os.path


if 3 > len(sys.argv):
    print "Usage: " + sys.argv[0] + " indir outdir [prefix]"
    quit()
    
indir = os.path.abspath(sys.argv[1])
outdir = os.path.abspath(sys.argv[2])

if 3 == len(sys.argv):
    prefix = os.path.basename(indir)
else:
    prefix = 'Set' + sys.argv(3)
    
HDRList.generateMoveScript(indir,
                           outdir,
                           prefix)
HDRList.generateHDRScript(indir,
                          outdir,
                          prefix)