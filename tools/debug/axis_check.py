"""blender -b --factory-startup --python axis_check.py -- <addon dir> <in.ska> <out.ska> <conv 0|1> [render.png]
Import with/without ToEE->Blender axis conversion, export again, optionally Workbench-render a front view."""
import bpy, sys, addon_utils, math, mathutils
a = sys.argv[sys.argv.index('--') + 1:]
addon_dir, src, out, conv = a[0], a[1], a[2], a[3] == '1'
sys.path.insert(0, addon_dir)
bpy.ops.wm.read_factory_settings(use_empty=True); addon_utils.enable('SKA_Export')
getattr(bpy.ops, 'import').ska_file(filepath=src, toee_axis_conversion=conv)
rig = bpy.data.objects['ToEE Rig']; mesh = bpy.data.objects['ToEE Model']
print('RIG MW', [list(map(lambda v: round(v, 4), r)) for r in rig.matrix_world])
bpy.context.view_layer.objects.active = rig
bpy.ops.export.ska_file(filepath=out, toee_axis_conversion=conv)
if len(a) > 4:
    sc = bpy.context.scene
    rig.animation_data.action = bpy.data.actions['unarmed_unarmed_idle']; sc.frame_set(1)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg); me = ev.to_mesh()
    pts = [ev.matrix_world @ v.co for v in me.vertices]
    lo = mathutils.Vector([min(p[i] for p in pts) for i in range(3)]); hi = mathutils.Vector([max(p[i] for p in pts) for i in range(3)])
    print('BBOX', [round(x, 3) for x in lo], [round(x, 3) for x in hi])
    c = (lo + hi) / 2; size = max(hi - lo)
    cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam')); sc.collection.objects.link(cam)
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = size * 1.3
    # Blender "Front" view: camera at -Y looking +Y, Z up
    cam.location = c + mathutils.Vector((size * 0.35, -size * 3, size * 0.15))
    cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.clip_end = size * 10; sc.camera = cam
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.light = 'STUDIO'; sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 640, 480
    sc.render.film_transparent = False
    # axis gizmo: small empties for X (red) / Y (green) / Z (blue) at the origin
    for i, col in enumerate(((1, 0, 0, 1), (0, 1, 0, 1), (0, 0, 1, 1))):
        bpy.ops.mesh.primitive_cylinder_add(radius=size * 0.01, depth=size * 0.4)
        o = bpy.context.object; d = mathutils.Vector([0, 0, 0]); d[i] = 1
        o.rotation_euler = d.to_track_quat('Z', 'Y').to_euler(); o.location = d * size * 0.2
        m = bpy.data.materials.new('ax%d' % i); m.diffuse_color = col; o.data.materials.append(m)
    sc.display.shading.color_type = 'MATERIAL'
    sc.render.filepath = a[4]; bpy.ops.render.render(write_still=True)
    print('RENDERED', a[4])
