# SKA scale channels, animation events, streams

## Scale channels
Format (Temple+ `aas_anim_player_stream.cpp`, `ska.py`): every stream has a float `scaleFactor`
next to `translationFactor`. The initial frame stores int16 x,y,z scale for every animated bone. A
keyframe record whose header has bit 3 set (`flags & 8`) carries `int16 nextFrame` and int16 x,y,z.
The value is `int16 * scaleFactor`, linearly interpolated between keys like the translation.
- The scale is the bone's absolute local scale (the SKA bone record's rest scale is usually 1). It is
  not relative to the rest pose, and there is no separate scale-orientation quaternion: it is a plain
  diagonal scale applied before the bone's rotation.
- Parent scale (`aas_animated_model.cpp`): the bone matrix is `S * R * S_parent^-1 * T * parent`, so a
  child's own scale and rotation ignore the parent's scale, while its position (the translation) still
  follows the scaled parent. In Blender that is `Bone.inherit_scale = 'NONE'`. The importer and Prepare
  rig now set it on all bones. With Blender's default (FULL) the Phycomid attacks were off by 12 units.
- Import: pose-bone scale F-Curves (engine value, linear keys), only for bones whose scale leaves 1.
  Export: sampled per frame, `scaleFactor = max|s| / 32767`, keys reduced like the other channels.
- Stock use (`tools/debug/ska_survey.py` over ToEE1-4.dat, 873 SKAs, 45415 animations): animated
  scale in 73 animations of 14 SKAs. Phycomid (attacks/casting, Bone20-24 up to 2.74x), the shard-breaking
  particle mesh, Ascomid, Skeleton, Spiritual_Weapon_Man, TempMan, Brother_Smith, Elmo, and the PC
  `#ClothBone` in the combatidle animations (its scale moves by 1.0; dwarves: 12 animations). Constant non-unity
  scale keys occur in 121 files.

## Events
Struct (`aas_skeleton.h` `SkelAnimEvent`, 178 bytes): `int16 frame; char type[48]; char action[128]`.
`SkelAnim.eventCount`/`eventOffset` point to them. `eventOffset` is relative to the animation's own
header. The writer puts all events after the 236-byte headers, as in the vanilla files.
Dispatch (`aas_anim_player.cpp`, `aas.cpp`): the type is matched case-insensitively.
- `script`: the text is run as Python with `anim_obj` bound.
- `action`: sets the "action" flag: the hit, or release of a spell/missile. The text is a bone name,
  `origin`, `Bip01` or `slimeRoot`.
- `end`: sets the end flag.
- Any other type is dropped with a warning.

An event fires when the playback time passes `frame / frameRate`, including on loops.

Stock events (`tools/debug/event_survey.py`): 41737 events in 17481 animations of 329 SKAs, 384 distinct texts:

| count | type | text |
|---:|---|---|
| 25166 | script | `anim_obj.footstep()` |
| 5364 | script | `game.sound_local_obj ( N, anim_obj )` |
| 4855 | action | `origin` |
| 3242 | action | `Bip01` |
| 2202 | script | `game.particles( 'name', anim_obj )` |
| 874 | script | `game.shake (amplitude, duration ms)`, e.g. (20, 800), (10, 200), (15, 400), (30, 1000) (12 SKAs: giants, ettin, elementals, vrock...) |
| 23 | script | `anim_obj.fade_to( 0, rate, n, OBJFADE_C_POOP_OFF )` (deaths) |
| 10 | action | `slimeRoot` |
| 1 | script | `anim_obj.balor_death()` |

No stock file uses the `end` type.

In Blender: each event is a pose marker on its action, named `type: text`, at Blender frame =
SKA frame + 1. Pose markers belong to the action, so they survive action switching. Show them in the
Action editor with *View > Show Pose Markers*. Marker names are capped at 63 bytes, so the full text and
the original 48/128-byte fields (vanilla files keep junk after the NUL) are stored in the action's
`toee_events` JSON. Unchanged or only moved markers write those bytes back. Unchanged events are
byte-identical after export (Ice Lizard 9, PC_Human_Male 337 events).

Editor: *3D View > Sidebar (N) > ToEE > ToEE Animation Events* (active object's action). It lists
the events with their SKA frame, and has buttons to add (presets: footstep, screen shake, sound, particles,
action/hit, fade out, custom), edit, remove, and jump to an event. New events go at the current frame. You
can also add a pose marker by hand named e.g. `script: anim_obj.footstep()`.

## Streams per animation
`SkelAnim` has room for 10 streams (`streamCount`; the engine picks one per model variation via
`variationId`). No stock SKA has more than one stream per animation (survey: 0 of 45415), so the
importer still asserts on more than one stream, and the exporter writes one stream per action.
Streams shared by several animations are written once.

## Files the reader can't parse
`Particle/test.ska`, `player/walker.ska`, `Scenery/Foliage/tree1.ska` and `Shields/PC_shield_buckler.SKA`
fail to parse in `ska.py` (short reads). Not investigated; probably test or leftover files.
