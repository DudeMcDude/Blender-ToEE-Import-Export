# Export validation

Before anything is written, `SKA_Export/validate.py` checks the mesh and rig against the limits the
engine enforces (Temple+ `Infrastructure/src/aas`). **Errors** block the export: nothing is written and
the operator is cancelled. **Warnings** allow it. Every item goes to the operator report (status bar /
Info editor), the console, and a text block called **ToEE Export Report** (Text editor). Both export
operators have **Auto-fix (temporary copy)** (on by default). It triangulates non-triangle faces in a
temporary mesh copy, drops zero weights, and keeps the 6 largest weights (renormalized) per vertex while
writing. The scene's mesh is never modified.

## Limits (source)
| Limit | Value | Source |
|---|---|---|
| bone weights per vertex | 6 | `aas_mesh.h` `MeshVertex::sMaxBoneAttachments = 6` |
| vertices | 32767 | `aas_mesh.h` `MeshFace::vertices` is `int16_t[3]`; `aas_renderer.cpp` `RecalcNormals` buffer `[0x8000]` |
| faces | triangles only | `MeshFace::sVertexCount = 3` |
| SKM bone name | 47 bytes | `aas_mesh.h` `MeshBone::name[48]` |
| SKA bone name | 39 bytes | `aas_skeleton.h` `SkelBone::name[40]` |
| bones | 1023 | `aas_animated_model.cpp` `boneState[1024]`, `bone_mapping[1024]` indexed by bone + 1 |
| material (MDF path) | 127 bytes | `aas_mesh.cpp` `MeshMaterial::id[128]` |
| animation name | 63 bytes | `aas_skeleton.h` `SkelAnim::name[64]` |
| event type / text | 47 / 127 bytes | `SkelAnimEvent` `type[48]`, `action[128]` |
| events per animation | 65535 (warn > 255) | `SkelAnim::eventCount` uint16, "seems to be uint8_t in reality" |
| frames | 32766 | keyframe frame stored as uint16 `frame << 1`; `aas_anim_player_stream.cpp` clamps at 32766 |
| name matching | case-insensitive | `Skeleton::FindBoneByName` `_stricmp` |
| weights | used as stored | normalized only on cloth skeletons (`aas_animated_model.cpp` ~372) |
| unweighted vertex | drawn unskinned | "simply use the vertex position" (`aas_animated_model.cpp` ~658) |

## Checks
SKM errors: no mesh/rig, empty mesh, non-triangle faces (unless auto-fix), more than 32767 vertices, more than 6 weights
(unless auto-fix), more than 1023 bones, bone names over 47 bytes, bone names that differ only in case, no material slots,
empty slot, material name over 127 bytes, face material index out of range, no UV map, and the mesh moved, rotated or scaled
relative to the rig (the export ignores object transforms).
SKM warnings: zero weights, weights not summing to 1, vertices with no weights, vertex groups matching no bone (with a
case-mismatch hint), non-uniform object scale, non-ASCII bone names, materials that are neither `.mdf` nor a body placeholder
(CHEST/BOOTS/GLOVES/HEAD), bone names over 39 bytes (SKA limit), no Armature modifier or armature parent, and other
modifiers (not applied).
SKA errors: bones over 1023, bone names over 39 bytes, bone names that differ only in case, action name over 63 bytes,
frame count outside 1..32766, event type over 47 or text over 127 bytes, more than 65535 events.
SKA warnings: no actions, actions keying bones not in the skeleton (ignored), unknown event type, event frame outside the
animation, more than 255 events, action names that differ only in case.

Tests: `tools/debug/validate_test.py`. Stock models (Ice Lizard, PC_Human_Male, Phycomid, PC_Dwarf_Male) pass with no
errors or warnings. 18 broken fixtures give exactly the expected errors and warnings. Blocked exports write no file.
Auto-fixed exports leave the scene mesh unchanged.
