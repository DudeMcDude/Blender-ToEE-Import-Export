# Stock round-trip suite

`tools/roundtrip/run_suite.py` takes every stock SKA (and the SKM with the same name next to it) through the
add-on headless: import -> export SKA+SKM (export validation runs as part of export), then compares with the originals.

```
python3 tools/roundtrip/run_suite.py --blender <blender> --data <ToEE data dir with art/meshes> --out /tmp/rt5 -j 7 \
    --baseline tools/roundtrip/baseline_5.2.json          # exit 1 on regressions (CI)
# resume after an interruption: run the same command again (finished models are skipped)
# after changing the add-on: add --rerun-stale (reruns results made by another commit), or --rerun for everything
# subsets: --filter REGEX, --limit N; new baseline: --write-baseline (merged when --filter is used)
```
Game data is read from `--data` only; the repo holds tooling and the baseline numbers. Per-model logs/results go to
`<out>/models/<path>/` (exported files are deleted unless `--keep`), the report to `<out>/results.csv` and `<out>/summary.md`.

## Checks per model
| check | pass when |
|---|---|
| SKM | byte-identical; otherwise per-field diff: counts, bone names/world-inverse (<=1e-5), vertex pos/normal/uv (<=1e-5), weights, faces |
| SKA | engine math (`tools/debug/engine_eval.py`, AnimPlayerStream mirror) on original vs exported file, both skinned with the original SKM, 8 sampled frames per animation incl. half frames: max vertex error and bone-origin error <= 0.25 ToEE units; only bones an SKM bone binds to by name (what the engine animates) |
| events | event records byte-identical per animation |
| materials | SKM material names unchanged (MDF paths, HEAD/CHEST/... placeholders) |
| validation | no export-validation errors (warnings are listed, don't fail) |
| crash | Blender error, timeout (`--timeout`, default 900 s) or compare error |

The SKA is not byte-identical by design: the exporter re-samples and re-reduces keys; the error metric is what the game shows.

Regressions vs baseline: a model's status got worse, its vertex/bone error grew by >25 % (+0.001), or its SKM stopped
being byte-identical. `known` in the baseline lists accepted failures with a reason.

## Known issues
- Fixed (fix/roundtrip-known-issues): the older compact animation headers (`player/walker.ska`: 76 bytes, no events;
  `Particle/test.ska`, `Scenery/Foliage/tree1.ska`: 84 bytes with event count/offset) are now detected and read, and
  export writes the current layout. `PC_shield_buckler.SKA` is truncated and has no SKM (skipped).
- Fixed: non-unit stock quaternions (`Particle/shard-breaking.SKA`, `Scenery/Portals/14_343_curtain01.SKA` helper bones).
  The engine uses them unnormalized; its slerp even inflates them between equal keys. Import stores the key norms in
  the action (`toee_qnorm`), export reapplies them and keeps such keys/bones instead of reducing them away.
- prepare-rig test "1.373 m": bone display tails (`Bip01 R Thigh`) - tails aren't stored in SKM/SKA and are rebuilt on import;
  joint heads round-trip within 0.08 mm. The test now checks heads.

## Results (stock data, 877 SKAs)
Blender 5.2.2: 870 pass, 5 known issues, 1 fail (medusa, normals; fixed by a later commit, rerun pending), 0 crash, 1 skipped
(PC_shield_buckler has no SKM). SKM byte-identical 875/876, materials preserved 876/876, events byte-identical 873 (the
other 3 are the legacy-header files), no validation errors. Worst SKA error in a passing model: 0.16 units (the snakes' long spine chain).
After the fix the 5 former known issues pass (rerun of those 5 only; full rerun pending).
Blender 4.2.3: pending.

Bugs found by the suite and fixed: SKA-only bones keyed the last SKM bone (fire_Snake), rotation segments near 180 deg in
export and import baking direction (giantrat/fireToad/firebat/kritch turns, up to 260 units), duplicate faces dropped,
zero/odd normals, loose-vertex UVs written short (corrupt SKM), import KeyError (EarthElemental), case-sensitive SKM lookup.

Big humanoid rigs (goblins, ogres, ~470 animations) take 20-50 min each under load; default timeout 2700 s.
