#!/usr/bin/env bash
# SKA-EXPORT check: run dist-cloth with SlotAuto, spawn an Ice Lizard, record its attacks with ffmpeg.
# Usage: run-skaview.sh <tag> [ska file to install as art/meshes/Monsters/Icelizard/icelizard.ska,
#        or a directory whose files (ska/skm/mdf/tga) all go into art/meshes/Monsters/Icelizard/]
# SKAVIEW_MODE=attack (default) | falldown | idle (plain standing NPC -> idle/fidget slots)
export DISPLAY=${DISPLAY_SKA:-:47} PATH=/usr/local/bin:/usr/bin:/bin:$PATH
TAG=${1:-run}; SKA=$2
O=/workspace/tp-build/dist-cloth/tpdata/overrides/skatest; D=$O/art/meshes/Monsters/Icelizard
L="/home/box/.wine-toee-ska/drive_c/users/box/Saved Games/TemplePlus/TemplePlus.log"
OUT=/workspace/tp-runs/skaview-$TAG; mkdir -p $OUT
WINEPREFIX=/home/box/.wine-toee-ska wineserver -k 2>/dev/null; sleep 1; rm -f "$L"
Z=/home/box/games/ToEE-ska/zzskatest.dat; rm -rf $O $Z; if [ -n "$SKA" ]; then T=$(mktemp -d); mkdir -p $T/art/meshes/Monsters/Icelizard; if [ -d "$SKA" ]; then cp "$SKA"/* $T/art/meshes/Monsters/Icelizard/; else cp "$SKA" $T/art/meshes/Monsters/Icelizard/icelizard.ska; fi; (cd $T && mkdir pk && mv art pk/ && WINEPREFIX=/home/box/.wine-toee-ska WINEDEBUG=-all wine /workspace/TemplePlus/dependencies/bin/datpack.exe zz.dat pk > /dev/null && mv zz.dat $Z); rm -rf $T; fi
export TP_TICK="skaview.tick()" TP_TICK_MS=250 TP_AUTOLOAD=SlotAuto TP_AUTOEXEC="import skaview; skaview.start()" WINEDEBUG=-all WINEDLLOVERRIDES=winedbg.exe=d
export WINEPREFIX=/home/box/.wine-toee-ska
cd /workspace/tp-build/dist-cloth
wine explorer /desktop=ToEEska,1280x800 TemplePlus.exe > $OUT/wine.out 2>&1 &
T0=$(date +%s)
until grep -q "SKAVIEW spawned" "$L" 2>/dev/null || [ $(( $(date +%s) - T0 )) -gt 200 ]; do sleep 0.2; done; xdotool mousemove 616 515 click 1; sleep 0.3; xdotool mousemove 1200 700
until grep -q "SKAVIEW ATTACK 2" "$L" 2>/dev/null || [ $(( $(date +%s) - T0 )) -gt 240 ]; do sleep 0.2; done
ffmpeg -loglevel error -y -f x11grab -framerate 15 -video_size 1280x800 -i $DISPLAY -t ${REC_S:-8} $OUT/rec.mp4
grep -q "SKAVIEW DONE" "$L" 2>/dev/null; import -window root $OUT/final.png
WINEPREFIX=/home/box/.wine-toee-ska wineserver -k 2>/dev/null; sleep 1
cp "$L" $OUT/TemplePlus.log
rm -f $Z
grep SKAVIEW $OUT/TemplePlus.log; echo "elapsed $(( $(date +%s) - T0 ))s"
