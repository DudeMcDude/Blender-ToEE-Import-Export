"""blender -b --factory-startup --python materials_test.py -- <addon dir> <out dir> <model.ska> ...
Imports each model (MDF node materials / placeholders), checks the materials, writes the SKM back
and compares it byte-for-byte with the stock SKM. Then: renamed material, missing MDF files and
writing an MDF for a new material."""
import bpy, sys, os, shutil, addon_utils
a = sys.argv[sys.argv.index('--') + 1:]
sys.path.insert(0, a[0]); out = a[1]; os.makedirs(out, exist_ok=True)
fails = []
def check(c, msg):
    print("MAT %s %s" % ("ok  " if c else "FAIL", msg))
    if not c: fails.append(msg)
def skm_of(ska):
    d, b = os.path.split(ska); stem = os.path.splitext(b)[0].lower()
    return next(os.path.join(d, n) for n in os.listdir(d) if n.lower() == stem + '.skm')
def load(ska):
    bpy.ops.wm.read_factory_settings(use_empty=True); addon_utils.enable('SKA_Export')
    getattr(bpy.ops, 'import').ska_file(filepath=ska)
    me = next(o for o in bpy.data.objects if o.type == 'MESH').data
    return me
def export(path):
    bpy.context.view_layer.objects.active = bpy.data.objects['ToEE Rig']
    bpy.ops.export.skm_file(filepath=path)
from SKA_Export import mdf as M
for ska in a[2:]:
    n = os.path.basename(ska).split('.')[0]
    me = load(ska)
    for m in me.materials:
        ph = m.get("toee_placeholder")
        if ph:
            check(M.is_placeholder(ph) and m.name == ph, "%s placeholder %s" % (n, ph)); continue
        nodes = m.node_tree.nodes
        texs = [x for x in nodes if x.type == 'TEX_IMAGE']
        info = "%s %s: type=%s tex=%d loaded=%d" % (n, m.get("toee_mdf_path"), m.get("toee_mdf_type"), len(texs),
                                                   sum(1 for t in texs if t.image and t.image.size[0] > 0))
        if m.get("toee_mdf"):
            x = M.parse(m["toee_mdf"])
            check(len(texs) == len(x.textures) and all(t.image and t.image.size[0] > 0 for t in texs), info)
            drift = [s for _, s in x.textures if s.uv == 'drift' and (s.speed_u or s.speed_v)]
            drv = [d for d in (m.node_tree.animation_data.drivers if m.node_tree.animation_data else [])]
            if drift: check(len(drv) >= 1, "%s drift UV -> %d drivers" % (n, len(drv)))
            env = [s for _, s in x.textures if s.uv == 'environment']
            if env: check(any(l.from_socket.name == 'Reflection' for l in m.node_tree.links), "%s environment stage uses Reflection" % n)
            check(m.use_backface_culling == (not x.double), "%s double-sided=%s" % (n, x.double))
        else:
            check(False, info + " (MDF missing)")
    o = os.path.join(out, n + '_rt.skm'); export(o)
    check(open(o, 'rb').read() == open(skm_of(ska), 'rb').read(), "%s SKM round trip byte-identical" % n)

# renamed Blender material + missing MDFs + new material MDF writing, on the first model
ska = a[2]; n = os.path.basename(ska).split('.')[0]
tmp = os.path.join(out, 'nodata', 'art', 'meshes', 'm'); shutil.rmtree(os.path.join(out, 'nodata'), ignore_errors=True); os.makedirs(tmp)
for f in (ska, skm_of(ska)): shutil.copy(f, tmp)
me = load(os.path.join(tmp, os.path.basename(ska)))
names = [m.get("toee_mdf_path") or m.get("toee_placeholder") for m in me.materials]
check(all(names) and all(m.get("toee_mdf_missing") or m.get("toee_placeholder") for m in me.materials), "missing MDFs: import ok, paths kept %s" % names[:2])
for m in me.materials: m.name = "renamed_" + m.name[:20]
o = os.path.join(out, n + '_renamed.skm'); export(o)
check(open(o, 'rb').read() == open(skm_of(ska), 'rb').read(), "renamed materials / missing MDFs: SKM still byte-identical")
img = bpy.data.images.new("newtex", 8, 8); img.filepath_raw = os.path.join(out, 'nodata', 'art', 'meshes', 'm', 'newtex.tga')
img.file_format = 'TARGA'; img.save()
nm = bpy.data.materials.new("art/meshes/m/new_material.mdf")
if bpy.app.version < (5, 0, 0): nm.use_nodes = True
t = nm.node_tree.nodes.new('ShaderNodeTexImage'); t.image = img
me.materials[0] = nm
bpy.context.view_layer.objects.active = bpy.data.objects['ToEE Rig']
bpy.ops.export.skm_file(filepath=os.path.join(tmp, 'out.skm'), write_mdf=True)
w = os.path.join(out, 'nodata', 'art', 'meshes', 'm', 'new_material.mdf')
txt = open(w).read() if os.path.exists(w) else ""
check('Textured' in txt and 'art/meshes/m/newtex.tga' in txt, "write_mdf: new material -> %s" % txt.replace("\n", " | "))
print("MAT RESULT", "PASS" if not fails else "FAIL %d" % len(fails))
