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

## Animation events and scale
SKA events (footsteps, sounds, particles, screen shake, hit frames) import as pose markers on each
action and are written back on export. Edit them in *3D View > Sidebar > ToEE*. Bone scale keys import
as scale F-Curves (bones use `inherit_scale = NONE`, as in the engine). See `docs/scale_events.md`.

## Export validation
Exports are checked first against the engine's limits (6 weights per vertex, triangles, 32767 vertices,
1023 bones, name lengths, ...). Errors block the export. Warnings are listed in the operator report and in the
*ToEE Export Report* text. *Auto-fix* triangulates and limits weights in a temporary copy. See `docs/export_validation.md`.
