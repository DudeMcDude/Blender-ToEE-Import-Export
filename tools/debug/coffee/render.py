import bpy, sys, math, mathutils
from mathutils import Vector
a = sys.argv[sys.argv.index('--') + 1:]; out = a[0]; frames = [int(x) for x in a[1].split(',')] if len(a) > 1 else None
sc = bpy.context.scene; rig = bpy.data.objects['ToEE Rig']
rig.animation_data.action = bpy.data.actions['coffee_preview']
for o in bpy.data.objects:
    if o.type == 'EMPTY': o.hide_render = True
bpy.data.objects['ToEE Model'].color = (0.62, 0.8, 0.95, 1)
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 1.33)); bpy.context.object.color = (0.35, 0.33, 0.3, 1)
sc.render.engine = 'BLENDER_WORKBENCH'; sc.render.resolution_x = 560; sc.render.resolution_y = 400
sh = sc.display.shading; sh.light = 'STUDIO'; sh.color_type = 'OBJECT'; sh.show_shadows = True; sh.show_cavity = True
sh.show_object_outline = True
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = float(a[3]) if len(a) > 3 else 35
cam.location = Vector([float(x) for x in a[2].split(',')]) if len(a) > 2 else Vector((5.5, -6.5, 4.5))
look = Vector([float(x) for x in a[4].split(",")]) if len(a) > 4 else Vector((-0.6, 0.6, 2.0))
cam.rotation_euler = (look - cam.location).to_track_quat('-Z', 'Y').to_euler()
for f in frames or range(1, 272, 2):
    sc.frame_set(f); sc.render.filepath = out + '/f%04d.png' % f; bpy.ops.render.render(write_still=True)
