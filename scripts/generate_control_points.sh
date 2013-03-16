#!/bin/bash
# Kezdeti verzió. Az aktuális könyvtárban lévő össze IMG_*.tif
# fájlra lefuttatja a matchpointot.

. /home/smb/SajatFejlesztes/common/scripts/multithread.sh

for i in IMG*.tif
do
# matchpoint bő egy percig mollyol
  wait_forlock 0.5
  l=$?
  case $l in
# 4 cpu core bedrótozva
  0 | 1 | 2 | 3)
    ( matchpoint $i $i.key ; rm mt_lock$l ) &
     ;;
  *) echo wait_for_lock error: $l
     exit ;;
  esac
done