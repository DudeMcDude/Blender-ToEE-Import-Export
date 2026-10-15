"""Import an SKA with the plugin and export it again with the plugin's SKA exporter.
blender -b --factory-startup --python blender_export.py -- <addon dir> <in.ska> <out.ska>"""
import bpy, sys, addon_utils
args = sys.argv[sys.argv.index('--') + 1:]
addon_dir, src, out = args[:3]
sys.path.insert(0, addon_dir)
bpy.ops.wm.read_factory_settings(use_empty=True); addon_utils.enable('SKA_Export')
getattr(bpy.ops, 'import').ska_file(filepath=src)
rig = bpy.data.objects['ToEE Rig']
bpy.context.view_layer.objects.active = rig
bpy.ops.export.ska_file(filepath=out)
print('EXPORTED', out)
