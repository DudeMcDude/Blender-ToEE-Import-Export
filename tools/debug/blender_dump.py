import bpy, sys, os, numpy as np, addon_utils
args = sys.argv[sys.argv.index('--')+1:]
addon_dir, out = args[0], args[1]
sys.path.insert(0, addon_dir)
addon_utils.enable('SKA_Export')
A = os.path.join(os.environ.get('TOEE_DATA', 'data'), 'art/meshes/Monsters/Icelizard/icelizard.ska')
bpy.ops.wm.read_factory_settings(use_empty=True); addon_utils.enable('SKA_Export')
getattr(bpy.ops, 'import').ska_file(filepath=A)
mesh = bpy.data.objects['ToEE Model']; rig = bpy.data.objects['ToEE Rig']
print('DUMP mesh mw', [list(r) for r in mesh.matrix_world], 'rig mw', [list(r) for r in rig.matrix_world], 'parent', mesh.parent, [m.type for m in mesh.modifiers], 'fps', bpy.context.scene.render.fps)
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(addon_dir, 'SKA_Export'))
import engine_eval as E
m = E.Model(A[:-3]+'skm', A)
bone_names = [str(b.name) for b in m.skm.bone_data]
res = {}
scene = bpy.context.scene
only = args[2].split(',') if len(args) > 2 and args[2] else None
for act in bpy.data.actions:
    if only and act.name not in only: continue
    a = m.anims.get(act.name)
    if a is None: continue
    rig.animation_data.action = act
    n = a.header.stream_headers[0].frame_count
    frames = np.arange(0, n - 1 + 1e-9, 0.5)
    V = []; D = []
    for f in frames:
        bf = 1 + f
        scene.frame_set(int(np.floor(bf)), subframe=float(bf - np.floor(bf)))
        dg = bpy.context.evaluated_depsgraph_get()
        ev = mesh.evaluated_get(dg); me = ev.to_mesh()
        mw = np.array(ev.matrix_world)
        co = np.array([v.co for v in me.vertices]); co = co @ mw[:3, :3].T + mw[:3, 3]
        V.append(co); ev.to_mesh_clear()
        rw = np.array(rig.matrix_world)
        D.append([rw @ np.array(rig.pose.bones[nm].matrix) @ np.linalg.inv(np.array(rig.data.bones[nm].matrix_local)) for nm in bone_names])
    res[act.name] = dict(frames=frames, V=np.array(V), D=np.array(D))
    print('DUMP', act.name, len(frames))
np.save(out, res, allow_pickle=True)
