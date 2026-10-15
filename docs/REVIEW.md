# Blender-ToEE-Import-Export: review (2026-10-11)

Repo: https://github.com/GrognardsFromHell/Blender-ToEE-Import-Export, cloned here. Local branch `local-blender4` has the minimal fixes. Nothing was pushed.
Tested with Blender 4.2.3 LTS (portable tarball at ~/opt/blender-4.2.3-linux-x64), headless.

## What it is
One addon, `SKA_Export/` (~2.7k lines of Python). README: "WIP, don't look :)". bl_info: "Cattletech & Pugmeister", blender (2,90,0).
- `ska.py`: pure-Python binary model for SKM, SKA, and MDF writing. It reads and writes the SKA keyframe stream at the *raw quantized* level.
- `import_ska.py`: SKM -> mesh, UVs, materials (MDF -> image), armature, and vertex groups. SKA -> one Action per animation (quaternion/location fcurves relative to rest).
- `export_ska.py`: Blender -> SKM (mesh, UVs, bones, weights, MDF texture path). **SKA export is a stub**: `_write_ska` only writes the SKM, and the rest is commented out. The operator calls `export_ska.save`, which doesn't exist.
- `ska_import_export_test.py`: a script that loads an SKA, modifies values (an Ice Lizard Z tweak), and writes it back with ska.py. This "load, modify, write" route is the only working SKA write path.

Feature status:
| Feature | Status |
|---|---|
| SKM import (mesh, UV, bones, weights) | works |
| Materials | partial: only the MDF base texture. Placeholder materials (CHEST/BOOTS/HEAD/GLOVES on PC bodies) aren't resolved and are **dropped on export**. Single texture only (TODO for phase spiders). No texture scale/offset. |
| SKA import to Actions | works after fixes. Rotation and location only; scale channels are just printed. One stream per animation assumed (assert). Events aren't imported. |
| SKM export | works, with caveats (below) |
| SKA export from Blender | **missing**: no fcurve -> quantized keyframe encoder |
| SKA binary read/write (no Blender) | works, byte-identical |

## History
17 commits. Initial upload Jul 2018 (Dude McDude). Sebastian Hartte "Updated and fixed SKA import" (Nov 2018). Then a 2.8/2.9 port by "fd gfd" (Oct 2020 to Jan 2021: working SKM import/export, `@` matmul, SKM-only option, rest_pose index bugfix, "ska load modify write"). Merged to master 2021-01-07, which is the last master commit.
Branches: `Update_Blender_v2p9` (merged), and `dirty` (1 commit "WIP", 2025-03-14, +183 lines in import_ska.py, an Ice Lizard reference asset set, and a duplicate `SKA_Import/` folder; not reviewed in depth).
Issues: none. PRs: #1 to #4, all merged (2020/21 port). Forks: dolio/Blender-ToEE-Import-Export, with no commits beyond master.
TODOs in code: texture scaling/translation, multi-texture, multi-stream, an `event_offset # TODO`, `anim_count = 10 # DEBUG` (imports only 10 animations), and debug dumps to `D:/bones.txt` and `<data>/bone_dump.txt`.
API: **2.8+** (2.9-era): annotations for props, `@`, `view_layer`, `node_shader_utils`, `evaluated_depsgraph_get`.

## Blender 4.2 test
Assets were extracted from ToEE*.dat with `tools/datx.py` (a small DAT1 extractor I wrote) into `assets/`: PC_Human_Male.SKM/.ska (91 bones, 684 anims) and icelizard.skm/.ska (122 bones, 24 anims). Harness: `test/rt.py` (Blender), `test/cmp.py`, and `test/ska_rt.py`.

The addon **enables cleanly**. Errors hit, in order (all fixed locally except the last):
1. `time.clock()` removed in Python 3.8, so every import and export crashed. Fixed by switching to `perf_counter`.
2. Companion SKM was looked up as `<name>.SKM` only, which fails on case-sensitive filesystems. Fixed.
3. Hard-coded `open("D:/bones.txt")` debug dump. Pointed it at the data dir.
4. `bpy.ops.poselib.pose_add` (T Pose / Rest Pose markers) was removed in Blender 3.0. Calls removed.
5. `progress.step(i)` passes an int as msg, so a format error. Fixed (upstream bug).
6. `anim_count = 10 # DEBUG` removed, so all animations import.
7. SKM export: `matrix4_to_3x4_array` flattened 12 floats while `SkmBone.write` expects 3 rows (`TypeError: float has no len()`) whenever a rig exists. Fixed.
8. SKA export: `AttributeError: export_ska has no attribute 'save'`. Not fixed, because it's a missing feature, not a port bug.

Results after the fixes (import 8 s for both models, all 684 human actions):
- Import: human 620 verts / 562 faces / 4 mats / 91 bones / 91 vgroups / 684 actions; lizard 1405 / 1448 / 2 / 122 / 24 actions. Counts match the files.
- SKM round trip (import, then export): bone count/names, vertex/face count, positions, UVs, faces, bone attachments and weights are all **identical**. Differences: normals are recomputed (max diff ~1.0 to 1.7, so some normals flip or are re-smoothed); **4/122 (lizard) and 24/91 (human) bone world-inverse matrices change** (all `*Nub` / `*_ref` helper bones, up to ~187 units off). Edit bones can't hold their exact matrix (zero-length or roll issues). This would break attachment points (Head_ref, HandL_ref…) in game. Human: **all 4 materials dropped**.
- SKA: no Blender export exists. The pure ska.py read and write of both SKAs is **byte-identical**, with 0 keyframe mismatches on re-read. But that only re-serializes the stored quantized frames; edits made in Blender can't be written.
- Things that will break next on newer Blender (not hit on 4.2): `action.fcurves` and `keyframe_points.insert` go through the legacy path of slotted Actions in 4.4+ and are removed in 5.0. The addon should also become a 4.2+ "extension" (blender_manifest.toml) for distribution.

## Engine check
The Temple+ SKA layout is in `Infrastructure/src/aas/aas_skeleton.h` (SkelAnimHeader: name, flags, frameRate, dps, eventCount, eventOffset, streamCount, streams[10] with dataOffset). ska.py mirrors it, and its output was byte-identical, so it's structurally valid. No in-game test was run: there's no Blender-authored SKA to test, and a byte-identical file proves nothing new.

## Porting effort and plan
1. Fixes 1 to 7: done locally, about 1 hour. Needs a clean CRLF-preserving diff (my rewrites normalized line endings in two files).
2. Exact bone matrices: store the original world-inverse as a custom property per bone and use it on export unless the bone was edited. About 0.5 day.
3. Materials: keep placeholder names and non-.mdf materials; split normals on export (or keep the originals). About 0.5 to 1 day.
4. **SKA export (the real work)**: sample or read fcurves per action, convert them back to bone-local SRT against rest, quantize to the stream format (scale/location factors, per-bone channel headers, frame deltas), and write events. Unit-test against the import of vanilla SKAs (import, export, re-import, max error). About 3 to 5 days.
5. Slotted-actions (4.4/5.0) API and an extension manifest: about 1 day.
6. Look at the `dirty` branch's import work before starting.
Total to a usable animation round-trip tool is about 1 to 1.5 weeks. Then an in-game test via a Temple+ data override of one animation (e.g. human unarmed_rturn).

## Animation import accuracy: engine vs Blender (2026-10-11, Ice Lizard)

### Method
- **Engine side**: I didn't build a native tool. The only AAS viewer in Temple+ is `Tools/ParticleEditorNative/animatedmodel.cpp`, a native DLL for the .NET ParticleEditor, which is impractical headless under Wine. Instead I wrote a standalone reference evaluator, `debug/engine_eval.py`, that mirrors the engine math line by line:
  - `aas_anim_player_stream.cpp` `Initialize` L165-228, `SetFrame` L41-163, `GetBoneState` L230-303 (per-channel prev/next keys, hold/lerp/slerp rules)
  - `aas_math.h` `slerpQuaternion` L146 (XMQuaternionSlerp, shortest arc) and `rotationMatrix` L271 (values under 1e-4 zeroed)
  - `aas_animated_model.cpp` L966-987 (W_i = W_parent · T · S_parent⁻¹ · R · S, SKA hierarchy) and skinning L597-692 / L1170-1185 (SKM full_world_inverse, then the SKA bone matrix, weighted)
  - Validation: after the fixes, Blender agrees with it to within 0.07 units on every animation, so the two independent implementations confirm each other.
- **Blender side**: `debug/blender_dump.py` imports icelizard.ska with the plugin. For each of the 24 actions it steps every half frame (Blender frame = 1 + SKA frame, with subframes) and dumps the depsgraph-evaluated world-space vertices plus each pose bone's deform matrix (`pb.matrix @ bone.matrix_local⁻¹`).
- **Comparison**: `debug/compare.py` reports max/mean vertex error per sample, plus which bones diverge first and which are worst. Results are in `debug/cmp_<stage>.json`. Plots: `debug/error_before_after.png` and `debug/rturn_stages.png`.

### Root causes (in order of impact) and fixes (branch `local-blender4`, commit edb5c20)
1. **Translations applied in the wrong frame** (constant ~300-unit offset): pose `location` was `loc - rest_loc`, but Blender applies it in the bone's rest frame, so it must be `rest_rot⁻¹ @ (loc - rest_loc)`. Shai's `dirty` branch already had this fix. Evidence: rotations matched exactly while translations didn't.
2. **Quaternion hemisphere flips (this is the "tilt toward the end")**: the importer negated each key when w < 0. When neighbouring keys straddle w = 0, Blender's component-wise lerp swings the long way round. In `unarmed_unarmed_rturn` the root goes from (0.707,-0.707,0,0) to (-0.037,0.037,-0.706,-0.706) at frame 29 of 30, so error spiked to **428 units at frames 27-29** and grew toward the end (unarmed_unarmed_fidget 428 at frame 86, likewise). The engine's slerp always takes the short arc. Fix: keep each key on the same hemisphere as the previous one (dot < 0 means negate). The `dirty` branch had just removed the flip, which also breaks on negative-dot pairs (up to 58 per animation).
3. **Unkeyed bones kept a stale pose**: the engine resets every bone to the skeleton's initial state, but Blender keeps whatever the previous action left. The roots aren't keyed in rattack/panic/rhit/walk/run, so there was a ~96-unit constant offset (root rotated 180°). Fix: a constant key from the SKA defaults.
4. **SKM and SKA hierarchies differ**: on the Ice Lizard, `Bip01 L/R Thigh` and `Bip01 Tail` have SKM parent Pelvis but SKA parent Spine. The engine animates the SKA skeleton, so the thighs were off by ~13°, a constant ~2.8 mean / up to 130 max error from frame 0 on. Fix: build the rig with SKA parents (the original is saved as `skm_parent_id`), set parents after all bones exist, and look pose bones up by name rather than index, since reparenting reorders `pose.bones`.
5. **Slerp vs Blender's component lerp** over large spans (the root's ~173° turn in one 29-frame span): up to 58 units mid-span, zero at the keys. Fix: when a span exceeds 20°, bake slerp-sampled keys at each integer frame (`SLERP_BAKE_ANGLE`).
6. **Time mapping**: the scene was 24 fps but SKA is 30 (turns are rotation-driven at 9.55, walk/run distance-driven at 0.0916 frames/unit), so I set the scene to 30 fps. Keys are on integer SKA frames and the engine samples fractional frames; comparing on half frames shows no extra error. Loop wrap (`SetFrame` rewinds when time goes backwards) isn't modelled in Blender.

Other checks: no non-unity scale in any Ice Lizard animation, so dropping scale isn't a factor here. It would be for other models; the parent-scale compensation in L982 isn't reproduced by Blender's default inherit_scale. There are no "hold gaps" between keys (each record's frame equals the previous key's next-frame).

### Numbers (max / mean vertex error, model is ~300 units tall)
| animation | before (upstream + API fixes) | after |
|---|---|---|
| unarmed_unarmed_rturn | 489 / 300 | 0.07 / 0.01 |
| unarmed_unarmed_fidget | 556 / 316 | 0.05 / 0.00 |
| unarmed_unarmed_rattack | 699 / 398 | 0.05 / 0.00 |
| unarmed_unarmed_idle | 374 / 302 | 0.05 / 0.00 |
| all 24 animations | ≤ 699 | ≤ 0.07 |
Stages for rturn: 489, then 428 (loc fix), 58 (hemisphere), 58 (stale), 31 (hierarchy), 0.07 (slerp bake).

### Caveats
- With the SKA-parent rig, SKM *export* now writes SKA parents. Export should restore `skm_parent_id`, which isn't done yet.
- The human male needed no reparenting and still imports fine. Only the Ice Lizard was compared numerically.
- No in-engine dump was taken; the engine side is the reference re-implementation cited above.
