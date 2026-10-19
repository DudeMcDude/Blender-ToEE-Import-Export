"""Events as pose markers: import, check markers, export unchanged (event bytes must match),
then edit markers (add / move / delete) and check the exported events.
blender -b --factory-startup --python events_test.py -- <addon dir> <in.ska> <out dir>"""
import bpy, sys, os, io, contextlib, addon_utils
a = sys.argv[sys.argv.index('--') + 1:]
addon_dir, src, out = a[0], a[1], a[2]; os.makedirs(out, exist_ok=True)
sys.path.insert(0, addon_dir)
bpy.ops.wm.read_factory_settings(use_empty=True); addon_utils.enable('SKA_Export')
from SKA_Export import ska
def read(p):
    s = ska.SkaFile()
    with contextlib.redirect_stdout(io.StringIO()): s.read(open(p, 'rb'))
    return {str(x.header.name): [(e.frame_id, str(e.type), str(e.action)) for e in x.events] for x in s.animation_data}
orig = read(src)
getattr(bpy.ops, 'import').ska_file(filepath=src)
rig = bpy.data.objects['ToEE Rig']; bpy.context.view_layer.objects.active = rig
n_mk = sum(len(act.pose_markers) for act in bpy.data.actions); n_ev = sum(len(v) for v in orig.values())
print('EVT markers %d, events in file %d' % (n_mk, n_ev))
ex = next(act for act in bpy.data.actions if len(act.pose_markers))
print('EVT example', ex.name, [(m.frame, m.name) for m in ex.pose_markers][:4])
p1 = os.path.join(out, 'unchanged.ska'); bpy.ops.export.ska_file(filepath=p1)
r1 = read(p1); print('EVT unchanged export: events equal', r1 == orig)
# edits on an animation with events: move the first marker 2 frames, delete the last, add a new one
act = ex; ms = list(act.pose_markers); want = list(orig[act.name])
ms[0].frame += 2; want[0] = (want[0][0] + 2,) + want[0][1:]
if len(ms) > 1:
    act.pose_markers.remove(ms[-1]); want.pop()
m = act.pose_markers.new('script: game.sound_local_obj ( 4242, anim_obj )'); m.frame = 6
want.append((5, 'script', 'game.sound_local_obj ( 4242, anim_obj )'))
p2 = os.path.join(out, 'edited.ska'); bpy.ops.export.ska_file(filepath=p2)
r2 = read(p2)
print('EVT edited export: %s matches %s' % (r2[act.name], r2[act.name] == want))
print('EVT other anims unchanged', all(r2[k] == orig[k] for k in orig if k != act.name))
# marker data survives action switching
rig.animation_data.action = bpy.data.actions[0]; rig.animation_data.action = act
print('EVT after action switch markers', len(act.pose_markers))
