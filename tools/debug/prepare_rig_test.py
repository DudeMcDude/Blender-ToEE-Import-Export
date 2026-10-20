"""Fresh Blender-convention rig -> Prepare rig for ToEE -> export SKA+SKM -> re-import (conversion on),
compare world-space bone heads/tails and skinned vertices per frame against the original.
blender -b --factory-startup --python prepare_rig_test.py -- <addon dir> <work dir> [render.png]"""
import bpy, sys, os, math, addon_utils, mathutils, numpy as np
from mathutils import Vector, Matrix
a = sys.argv[sys.argv.index('--') + 1:]
addon_dir, work = a[0], a[1]
sys.path.insert(0, addon_dir)
bpy.ops.wm.read_factory_settings(use_empty=True); addon_utils.enable('SKA_Export')
sc = bpy.context.scene; sc.render.fps = 30
out_dir = os.path.join(work, 'art', 'meshes', 'test'); os.makedirs(out_dir, exist_ok=True)

# --- build a small biped-ish rig in Blender convention: Z up, front -Y, metres ---
arm = bpy.data.armatures.new('MyArm'); rig = bpy.data.objects.new('MyRig', arm); sc.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode='EDIT')
def bone(n, h, t, p=None, roll=0.0):
    b = arm.edit_bones.new(n); b.head = h; b.tail = t; b.roll = roll
    if p: b.parent = arm.edit_bones[p]
    return b
bone('Bip01', (0, 0, 1.0), (0, 0, 1.1))
bone('Bip01 Spine', (0, 0, 1.1), (0, 0, 1.5), 'Bip01', 0.3)
bone('Bip01 Head', (0, 0, 1.5), (0, 0, 1.8), 'Bip01 Spine')
bone('Bip01 Nose', (0, 0, 1.65), (0, -0.25, 1.65), 'Bip01 Head')       # points to the front (-Y)
bone('Bip01 L UpperArm', (0.2, 0, 1.45), (0.55, 0, 1.45), 'Bip01 Spine')  # character's left = +X
bone('HandL_ref', (0.55, 0, 1.45), (0.6, 0, 1.45), 'Bip01 L UpperArm')
bone('Bip01 R Thigh', (-0.1, 0, 1.0), (-0.1, 0, 0.0), 'Bip01')
bpy.ops.object.mode_set(mode='OBJECT')
rig.matrix_world = Matrix.Translation((2, 1, 0)) @ Matrix.Rotation(math.radians(30), 4, 'Z') @ Matrix.Scale(1.5, 4)

# mesh: one box per bone, rigidly weighted (plus a blended vertex set on the spine/head)
import bmesh
bm = bmesh.new()
groups = []
for b in arm.bones:
    h, t = b.head_local, b.tail_local; c = (h + t) / 2; d = (t - h)
    r = bmesh.ops.create_cube(bm, size=1.0)['verts']
    for v in r:
        v.co = c + Vector((v.co.x * max(abs(d.x), 0.08), v.co.y * max(abs(d.y), 0.08), v.co.z * max(abs(d.z), 0.08)))
    groups.append((b.name, [v.index for v in r]))
bm.verts.index_update(); bmesh.ops.triangulate(bm, faces=bm.faces)
me = bpy.data.meshes.new('MyMesh'); bm.to_mesh(me); me.uv_layers.new()
mesh = bpy.data.objects.new('MyMesh', me); sc.collection.objects.link(mesh)
mat = bpy.data.materials.new('test.mdf'); me.materials.append(mat)
idx = 0
for name, _ in groups:  # vertex groups deliberately NOT in bone order
    pass
for name, vids in reversed(groups):
    vg = mesh.vertex_groups.new(name=name)
for name, vids in groups:
    vg = mesh.vertex_groups[name]
    for vi in vids:
        vg.add([vi], 1.0, 'REPLACE')
mesh.parent = rig; mesh.matrix_parent_inverse = rig.matrix_world.inverted()
mesh.modifiers.new('Armature', 'ARMATURE').object = rig

# animation: root walks forward (-Y) and bobs, spine twists, arm raises, head nods; frames 1..21
act = bpy.data.actions.new('unarmed_unarmed_walk'); rig.animation_data_create(); rig.animation_data.action = act
for pb in rig.pose.bones: pb.rotation_mode = 'QUATERNION'
for f in range(1, 22, 4):
    t = (f - 1) / 20
    rig.pose.bones['Bip01'].location = (0, 0.3 * t, 0.05 * math.sin(6.28 * t))   # bone-local: Bip01 points +Z, so bone-y = world +Z.. any
    rig.pose.bones['Bip01'].keyframe_insert('location', frame=f)
    for n, ax, ang in (('Bip01 Spine', 'Y', 0.6 * math.sin(6.28 * t)), ('Bip01 L UpperArm', 'Z', 1.2 * t),
                       ('Bip01 Head', 'X', 0.4 * math.sin(12.56 * t)), ('Bip01', 'Z', 0.5 * t)):
        rig.pose.bones[n].rotation_quaternion = Matrix.Rotation(ang, 4, ax).to_quaternion()
        rig.pose.bones[n].keyframe_insert('rotation_quaternion', frame=f)
from SKA_Export import anim_compat
for fc in anim_compat.action_fcurves(act):
    for k in fc.keyframe_points: k.interpolation = 'LINEAR'


def render(path, mesh_ob, rig_ob, frame=11):
    sc = bpy.context.scene; sc.frame_set(frame)
    dg = bpy.context.evaluated_depsgraph_get(); ev = mesh_ob.evaluated_get(dg); m = ev.to_mesh()
    pts = [ev.matrix_world @ v.co for v in m.vertices]; ev.to_mesh_clear()
    lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
    c = (lo + hi) / 2; size = max(hi - lo)
    cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam')); sc.collection.objects.link(cam)
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = size * 1.6
    cam.location = c + Vector((-size * 0.8, -size * 3, size * 0.5))   # front-left of a -Y-facing model
    cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler(); sc.camera = cam
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 480, 480
    bpy.ops.mesh.primitive_plane_add(size=size * 3, location=(c.x, c.y, 0))
    sc.render.filepath = path; bpy.ops.render.render(write_still=True); print('RENDERED', path)
    bpy.data.objects.remove(bpy.context.object); bpy.data.objects.remove(cam)

FR = list(range(1, 22))
def sample(rig_ob, mesh_ob, bones):
    B, V = [], []
    for f in FR:
        sc.frame_set(f); dg = bpy.context.evaluated_depsgraph_get()
        mw = rig_ob.matrix_world
        B.append([list(mw @ rig_ob.pose.bones[n].head) + list(mw @ rig_ob.pose.bones[n].tail) for n in bones])
        ev = mesh_ob.evaluated_get(dg); m = ev.to_mesh()
        V.append([list(ev.matrix_world @ v.co) for v in m.vertices]); ev.to_mesh_clear()
    return np.array(B), np.array(V)
names = [b.name for b in arm.bones]
B0, V0 = sample(rig, mesh, names)
if len(a) > 2: render(a[2].replace('.png', '_original.png'), mesh, rig)

from SKA_Export import prepare_rig as P
assert P.prepare_rig(rig) is True
B1, V1 = sample(rig, mesh, names)
print('PREPARE viewport change: bones %.2e m, verts %.2e m' % (np.abs(B1 - B0).max(), np.abs(V1 - V0).max()))
assert P.prepare_rig(rig) is False  # idempotent
B1b, _ = sample(rig, mesh, names); print('PREPARE twice: change %.2e m' % np.abs(B1b - B1).max())

bpy.context.view_layer.objects.active = rig
ska = os.path.join(out_dir, 'testrig.ska')
bpy.ops.export.ska_file(filepath=ska, write_skm=True)

# --- re-import in a fresh scene ---
bpy.ops.wm.read_factory_settings(use_empty=True); addon_utils.enable('SKA_Export'); sc = bpy.context.scene
getattr(bpy.ops, 'import').ska_file(filepath=ska)
rig2 = bpy.data.objects['ToEE Rig']; mesh2 = bpy.data.objects['ToEE Model']
rig2.animation_data.action = bpy.data.actions['unarmed_unarmed_walk']
B2, V2 = sample(rig2, mesh2, names)
print('ROUNDTRIP(info) world error incl. display tails: bone head/tail max %.5f m, vertex max %.5f m (%.4f / %.4f ToEE units)' % (
    np.abs(B2 - B0).max(), np.abs(V2 - V0).max(), np.abs(B2 - B0).max() / 0.0254, np.abs(V2 - V0).max() / 0.0254))
_h = np.abs(B2[..., :3] - B0[..., :3]).max(axis=(0, 2)); _t = np.abs(B2[..., 3:] - B0[..., 3:]).max(axis=(0, 2))
print('ROUNDTRIP bone heads (joints) max %.5f m [%s]; tails max %.5f m (not stored in SKM/SKA, rebuilt on import); worst tail: %s' % (_h.max(), 'PASS' if _h.max() < 1e-3 else 'FAIL', _t.max(),
      sorted(zip(_t, names), reverse=True)[:3]))
# orientation in ToEE data and in Blender
import SKA_Export.ska as S
skm = S.SkmFile(); skm.read(open(os.path.join(out_dir, 'testrig.skm'), 'rb'))
def toee_head(n):
    b = next(b for b in skm.bone_data if str(b.name) == n)
    W = np.linalg.inv(np.vstack([np.array(b.world_inverse_matrix)[:3], [0, 0, 0, 1]])); return W[:3, 3]
print('TOEE SPACE (rest, no object transform): Head', toee_head('Bip01 Head').round(2), 'Nose tip dir via Nose head',
      toee_head('Bip01 Nose').round(2), 'L arm', toee_head('Bip01 L UpperArm').round(2))
r = bpy.data.objects['ToEE Rig']; sc.frame_set(1)
nose = r.matrix_world @ r.pose.bones['Bip01 Nose'].tail - r.matrix_world @ r.pose.bones['Bip01 Nose'].head
up = r.matrix_world @ r.pose.bones['Bip01 Spine'].tail - r.matrix_world @ r.pose.bones['Bip01 Spine'].head
print('BLENDER after re-import: nose dir', np.round(list(nose.normalized()), 3), 'spine dir', np.round(list(up.normalized()), 3))
np.save(os.path.join(work, 'samples.npy'), dict(B0=B0, B2=B2, V0=V0, V2=V2), allow_pickle=True)
if len(a) > 2:
    render(a[2], mesh2, rig2)
