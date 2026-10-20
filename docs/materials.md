# Materials: MDF files and body placeholders

## What the importer builds
Each SKM material slot names either an MDF file (path relative to the data dir) or one of the
engine's **body placeholders**.

| Placeholder | Engine id (`AasResolveMaterial`) | Replaced at runtime by |
|---|---|---|
| `HEAD`   | 0x84000000 | helmet / naked head MDF |
| `GLOVES` | 0x88000000 | gloves / naked hands |
| `CHEST`  | 0x90000000 | armor / naked torso |
| `BOOTS`  | 0xA0000000 | boots / naked feet |

The engine compares names exactly (upper case). Placeholders are imported as materials with those names,
a flat colour per slot and the custom property `toee_placeholder`. Stock users: the six PC bodies
(human/dwarf/half-orc, male+female; elves, gnomes, half-elves and halflings reuse them), NPC_Brother_Smith,
NPC_Elmo and Spiritual_Weapon_Man (`CHEST` only). No stock monster uses one.

MDF slots become node materials (`SKA_Export/mdf.py` parses them following Temple+'s `MdfParser`; `materials.py`
builds the nodes):

| MDF | Blender |
|---|---|
| `Textured` / `General` / `Clipper` | image-texture graph / same / transparent (z-only clipper) |
| `Texture N` (up to 4 stages) | one Image Texture node per stage |
| `BlendType` modulate / add / texturealpha / currentalpha / currentalphaadd | Mix node multiply / add / mix by the stage alpha / mix by the running alpha / add by the running alpha |
| `Color` | RGB node multiplied in (alpha multiplied into the alpha) |
| `UVType` mesh / environment | UV / Reflection coordinates through a Mapping node |
| `UVType drift` + `SpeedU`/`SpeedV`/`Speed` | Mapping location driven by `frame/fps*speed` (the engine moves UVs by speed per second) |
| `UVType swirl` / `wavey` | kept in the MDF; shown static (Mapping node carries `toee_uv`) |
| `MaterialBlendType` none / alpha / add / alphaadd | opaque / alpha-blended / emission added over transparent / same, weighted by alpha |
| `notlit` | Emission shader |
| `Double` | backface culling off |
| `Clamp` | Extend instead of Repeat |
| `Specular`, `SpecularPower` | roughness approximation |
| `LinearFiltering`, `HighQuality`, `RecalculateNormals`, `ZFillOnly`, `ColorFillOnly`, `DisableZ`, `GlossMap`, clipper flags | parsed and kept, not shown |

The material keeps `toee_mdf_path` (the exact SKM name) and `toee_mdf` (the original MDF text). Paths are looked
up case-insensitively. A missing MDF or texture prints a warning and gives a magenta/placeholder material
(`toee_mdf_missing`) that still exports the original path.

## Export
The SKM material name for each slot is the material's `toee_mdf_path` / `toee_placeholder`, so renaming the
Blender material, reordering slots or names longer than Blender's 63 characters don't change it. Materials made
in Blender use their own name (`HEAD`/`CHEST`/... or `art/meshes/.../x.mdf`). The original name bytes are kept
while the name is unchanged, so the SKM round trip is byte-identical (tested on PC_Human_Male/Female,
PC_Dwarf_Male, PC_halforc_female, Demon, Vrock and fire_Snake).

**Write MDFs for new materials** (export option, off by default): for slots whose material was not imported
from an MDF and whose `.mdf` does not exist yet under the data dir, a `Textured` MDF is written from the first
image texture (path relative to the data dir). Existing MDFs are never overwritten.

## Stock MDF survey (`tools/debug/mdf_survey.py`, 1585 files)
1362 textured, 218 general, 5 clipper. Textures per file: 0: 51, 1: 1458, 2: 64, 3: 12. UV types: drift 41,
environment 28, swirl 18, wavey 10. Stage blends: add 21, currentalpha 28, currentalphaadd 9, texturealpha 5.
Material blend: alphaadd 16, add 1. 15 files contain tokens the engine ignores (e.g. `uv`, `BlendType alpha`);
the parser ignores them too. Writer: all 1585 files parse back to the same material.
`tools/debug/skm_material_survey.py` lists the slots of every stock SKM.

## Equipment on PCs vs monsters (Temple+ findings, not implemented)
- `GetModelRaceOffset` (critter.cpp) returns -1 for any critter whose `obj_f_base_mesh` >= 1000 (monsters).
  With -1, both `UpdateModelEquipment` (placeholder material swaps) and `UpdateAddMeshes` (armor/cloak/helmet
  addmeshes) return early. So monsters never get equipment visuals, whatever their mesh contains.
- PCs: race offset = `GetRaceMaterialOffset(race)` + female. `rules/materials.mes` holds replacement sets
  (`{id}{SLOT:mdf ...}`) in banks of 100 (offset = race/sex; 0/100/200/500/800 = naked helmet/cloak/gloves/armor/boots).
  An item uses `obj_f_item_material_slot + offset` (fallback to the base race). `rules/addmesh.mes` (+ `rules/addmeshes/*.mes`)
  maps the same ids to addmesh SKMs (e.g. 2700+ fullplate). Robes hide armor, polymorph disables addmeshes, helmets
  change hair.
- Any NPC, monsters included, gets the static `obj_f_npc_add_mesh` addmesh (`AddNpcAddMeshes`), which doesn't depend on equipment.
- Stock bugbears show armor through **separate baked meshes** (`Monsters/Bugbears/<temple>/<temple>-Chain`, `-Hvy_leather`,
  `-Scale`...), each a full model with its own MDF, picked by the proto's mesh id.
- Addmeshes are skinned to the base skeleton by bone name. The bugbear (76 bones) and troll (67) use the same `Bip01 ...`
  names as the PC rig, missing only the PC ponytail/dummy/`human_male_base`/`casting_ref` helper bones, but their proportions differ.

What a bugbear/troll would need to show equipped armor:
1. Its mesh with `HEAD`/`GLOVES`/`CHEST`/`BOOTS` material slots on the matching body parts (the add-on now round-trips these).
2. Replacement sets for it in `materials_ext.mes`: a new bank offset (like a new race) with naked sets plus per-armor MDFs
   UV-mapped for its body.
3. Optional armor addmeshes skinned to its skeleton, listed in an addmesh `.mes` at the same offsets.
4. An engine change (Temple+): `GetModelRaceOffset` must return that offset for the monster instead of -1, e.g. a
   per-mesh-id or per-proto table, so `UpdateModelEquipment`/`UpdateAddMeshes` run. Without it, 1-3 do nothing.
   Alternative with no engine change: keep baked variants per armor type, as stock does.
