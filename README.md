# Blender-ToEE-Import-Export

WIP, don't look :)

## Blender versions
- The main line (`blender5-port` onward) supports **Blender 4.2 LTS through 5.x** (tested on 4.2.3 and 5.2.2).
- The last state before the Blender 5 port is kept on branch `legacy/blender-4.2` (tag `blender-4.2-last`).

## Installing
- As an extension (Blender 4.2+): `blender --command extension build --source-dir SKA_Export`, then
  *Edit > Preferences > Get Extensions > Install from Disk* with the zip.
- As a legacy add-on: zip the `SKA_Export` folder (or link it into `scripts/addons`) and enable
  "SKA Importer/Exporter". Both ways work from the same folder.

## Tests
`TOEE_DATA=<folder with art/meshes> test/run_all.sh <blender> <out dir>` runs the headless checks:
SKA import vs the engine math (Ice Lizard, PC_Human_Male), SKM and SKA export round trips,
Prepare rig and, with `FIT_SRC`/`FIT_TGT` set, `tools/fit_free_model.py`.
