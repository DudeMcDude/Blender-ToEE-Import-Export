"""Blender side of the round-trip suite (one model per process):
blender -b --factory-startup --python rt_blender.py -- <addon dir> <in.ska> <out dir>
Imports the SKA+SKM, exports SKA and SKM (export validation runs and prints its report), and
writes <out dir>/blender.json with the material slots and timings."""
import bpy, sys, os, json, time, addon_utils
a = sys.argv[sys.argv.index('--') + 1:]
addon, src, out = a[:3]
sys.path.insert(0, addon); os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True); addon_utils.enable('SKA_Export')
info = dict(blender=bpy.app.version_string, src=src, stage='import')
def dump():
    json.dump(info, open(os.path.join(out, 'blender.json'), 'w'), indent=1)
t = time.time(); dump()
getattr(bpy.ops, 'import').ska_file(filepath=src)
info['t_import'] = round(time.time() - t, 2)
rig = bpy.data.objects.get('ToEE Rig')
mesh = next((o for o in bpy.data.objects if o.type == 'MESH'), None)
if mesh is not None:
    from SKA_Export import materials as MAT
    info['materials'] = MAT.skm_material_names(mesh.data)
    info['mat_kinds'] = ['placeholder' if m.get('toee_placeholder') else 'missing' if m.get('toee_mdf_missing')
                         else 'mdf' if m.get('toee_mdf') else 'other' for m in mesh.data.materials if m]
info['actions'] = len(bpy.data.actions); info['stage'] = 'export'; dump()
bpy.context.view_layer.objects.active = rig
t = time.time()
r = bpy.ops.export.ska_file(filepath=os.path.join(out, 'out.ska'), write_skm=True)
info['export_result'] = sorted(r); info['t_export'] = round(time.time() - t, 2); info['stage'] = 'done'; dump()
print('RT_DONE')
