import bpy, sys, os, numpy as np, addon_utils, math
a = sys.argv[sys.argv.index('--')+1:]
mode, addon_dir, anim, outdir, label = a[0], a[1], a[2], a[3], a[4]
CAM = [float(x) for x in a[5].split(',')]  # cx,cy,cz, dist
os.makedirs(outdir, exist_ok=True)
A = '/workspace/blender-toee/assets/art/meshes/Monsters/Icelizard/icelizard.'
sys.path.insert(0, '/workspace/blender-toee/debug'); sys.path.insert(0, addon_dir)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
import engine_eval as E
m = E.Model(A+'skm', A+'ska'); an = m.anims[anim]; n = an.header.stream_headers[0].frame_count
if mode == 'engine':
    faces = [tuple(f.vertex_ids) for f in m.skm.face_data]
    me = bpy.data.meshes.new('eng'); me.from_pydata(m.verts.tolist(), [], faces); me.update()
    ob = bpy.data.objects.new('eng', me); sc.collection.objects.link(ob)
else:
    addon_utils.enable('SKA_Export')
    getattr(bpy.ops, 'import').ska_file(filepath=A+'ska')
    rig = bpy.data.objects['ToEE Rig']; rig.animation_data.action = bpy.data.actions[anim]
    ob = bpy.data.objects['ToEE Model']
root = bpy.data.objects.new('yup', None); sc.collection.objects.link(root); root.rotation_euler = (math.pi/2, 0, 0)
for o in list(sc.objects):
    if o.parent is None and o is not root: o.parent = root
sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading; sh.light = 'STUDIO'; sh.color_type = 'SINGLE'
sh.single_color = (0.55, 0.75, 0.95); sh.show_cavity = False
sc.render.resolution_x = 480; sc.render.resolution_y = 480; sc.render.film_transparent = False
w = bpy.data.worlds.new('w'); sc.world = w
cx, cy, cz, d = CAM[:4]; FRONT = len(CAM) > 4 and CAM[4] == 1
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (cx, -cz - d, cy + d*0.08) if FRONT else (cx + d*0.8, cz - d*0.55, cy + d*0.25)  # FRONT: along model +Z (lizard forward)  # look from a fixed 3/4 view
direc = np.array([cx, cy, cz]) - np.array(cam.location)
from mathutils import Vector
tgt = bpy.data.objects.new('tgt', None); sc.collection.objects.link(tgt); tgt.location = (cx, -cz, cy)
con = cam.constraints.new('TRACK_TO'); con.target = tgt; con.track_axis = 'TRACK_NEGATIVE_Z'; con.up_axis = 'UP_Y'
cam.data.lens = 50; cam.data.clip_end = 20000; cam.data.clip_start = 1
print('DIMS', ob.dimensions, [list(ob.matrix_world @ Vector(c)) for c in ob.bound_box][:2])
for f in range(n):
    if mode == 'engine':
        v = m.skin(m.bone_mats(m.bone_state(an, f)))
        for i, vv in enumerate(me.vertices): vv.co = v[i]
        me.update()
    else:
        sc.frame_set(1 + f)
    sc.render.filepath = os.path.join(outdir, '%03d.png' % f)
    bpy.ops.render.render(write_still=True)
print('RENDERED', n)
