#!/bin/bash
# Headless regression run: test/run_all.sh <blender binary> <out dir>
# Needs TOEE_DATA (folder containing art/meshes) and, for the fit test, FIT_SRC (Yawa .blend) + FIT_TGT (Lizardman_Large.SKA).
set -u
B=$1; O=$2; R=$(cd "$(dirname "$0")/.." && pwd); D=$R/tools/debug; mkdir -p "$O"; cd "$O"
M=$TOEE_DATA/art/meshes
"$B" --version | head -1
for case in "lizard Monsters/Icelizard/icelizard.ska Monsters/Icelizard/icelizard.skm" "human PCs/PC_Human_Male/PC_Human_Male.ska PCs/PC_Human_Male/PC_Human_Male.SKM"; do
  set -- $case; n=$1; ska=$2; skm=$3
  echo "=== $n: import vs engine"
  TOEE_MODEL=$ska:$skm "$B" -b --factory-startup --python $D/blender_dump.py -- "$R" $O/$n.npy > $O/$n.dump.log 2>&1; grep -c '^DUMP ' $O/$n.dump.log; grep -iE "Traceback|Error" $O/$n.dump.log | head -5
  TOEE_MODEL=$ska:$skm python3 $D/compare.py $O/$n.npy $n | tail -1
  echo "=== $n: SKM export round trip"
  "$B" -b --factory-startup --python $D/skm_roundtrip.py -- "$R" $M/$ska $O/${n}_rt.skm 0 > $O/$n.skm.log 2>&1; grep -iE "Traceback|Error" $O/$n.skm.log | head -5
  python3 $D/skm_diff.py $M/$skm $O/${n}_rt.skm | grep -E "bytes|differing|max diff"
  echo "=== $n: SKA export round trip"
  "$B" -b --factory-startup --python $D/blender_export.py -- "$R" $M/$ska $O/${n}_rt.ska > $O/$n.ska.log 2>&1; grep -iE "Traceback|Error" $O/$n.ska.log | head -5
  python3 $D/ska_diff.py $M/$skm $M/$ska $O/${n}_rt.ska | grep -E "MAX|MISSING|False" | head -8
done
echo "=== prepare rig"
"$B" -b --factory-startup --python $D/prepare_rig_test.py -- "$R" $O/prep > $O/prep.log 2>&1; grep -E "PREPARE|ROUNDTRIP|Traceback|Error" $O/prep.log | head -8
if [ -n "${FIT_SRC:-}" ]; then
  echo "=== fit_free_model"
  "$B" -b --factory-startup --python $R/tools/fit_free_model.py -- --addon "$R" --target "$FIT_TGT" --source "$FIT_SRC" --mesh-object YawaFull \
    --map $R/tools/fit_maps/aedan_snakeman_to_lizardman.json --decimate 6000 --tex-size 512 --out $O/fit \
    --mdf art/meshes/Monsters/Lizardman/Lizardman_Large/yuanti.mdf --tint 0.45,0.85,0.35 --tint-amount 0.75 > $O/fit.log 2>&1
  grep -iE "Traceback|Error" $O/fit.log | head -5; tail -3 $O/fit.log; ls -la $O/fit
fi
