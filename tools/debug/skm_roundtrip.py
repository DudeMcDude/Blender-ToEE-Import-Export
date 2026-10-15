"""blender -b --factory-startup --python skm_roundtrip.py -- <addon dir> <in.ska> <out.skm> [conv 0|1]
Import SKA+SKM with the plugin and write the SKM back with the plugin's SKM exporter."""
import bpy, sys, addon_utils
a = sys.argv[sys.argv.index('--') + 1:]
sys.path.insert(0, a[0])
bpy.ops.wm.read_factory_settings(use_empty=True); addon_utils.enable('SKA_Export')
conv = (a[3] == '1') if len(a) > 3 else True
getattr(bpy.ops, 'import').ska_file(filepath=a[1], toee_axis_conversion=conv)
bpy.context.view_layer.objects.active = bpy.data.objects['ToEE Rig']
bpy.ops.export.skm_file(filepath=a[2])
print('EXPORTED', a[2])
