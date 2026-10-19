"""Fit a third-party rigged model onto a vanilla ToEE skeleton so it plays the vanilla SKA animations.

blender -b --factory-startup --python tools/fit_free_model.py -- \
    --addon <repo dir> --target <vanilla .SKA (its .SKM next to it)> --source <model .glb/.gltf/.fbx/.blend> \
    --map tools/fit_maps/<map>.json --out <dir> --mdf art/meshes/.../name.mdf [--mesh-object Name] [--keep-thickness]

What it does (both rigs must be in roughly the same rest pose, e.g. both T-pose, both facing -Y in Blender):
 1. imports the ToEE model with the plugin (axis conversion on: ToEE Y-up/+Z-forward -> Blender Z-up/-Y-forward,
    1 unit = 1 inch -> metres) and the source model with Blender's importer;
 2. scales the source so its bounding-box height matches the ToEE mesh (feet stay on the floor);
 3. re-shapes the source mesh onto the ToEE joints: every source bone listed under "segments" maps its joint
    pair (head -> next joint) onto the ToEE joint pair (minimal rotation, stretch along the segment, thickness
    kept); bones under "translate" just move with a joint; each vertex blends these by its source skin weights;
 4. renames/merges the source vertex groups to ToEE bone names ("weights"; '*.L' wildcards; null drops; a list
    splits one source bone over several ToEE bones by distance to their segments, e.g. a 1-bone arm),
    keeps at most 6 influences, renormalises;
 5. converts the source texture (single textured material) or bakes flat material colours into a palette TGA,
    optionally tinted (--tint, e.g. icy blue), one material,
    writes the MDF and exports <out>/<target name>.SKM against the ToEE rig (the vanilla SKA is reused as is).
"""
import bpy, sys, os, json, math, argparse, fnmatch, struct, addon_utils
from mathutils import Vector, Matrix

a = argparse.ArgumentParser()
for k in ('addon', 'target', 'source', 'map', 'out', 'mdf'): a.add_argument('--' + k, required=True)
a.add_argument('--mesh-object', default=None)
a.add_argument('--tint', default=None, help='r,g,b colour blend for the texture/palette, e.g. 0.55,0.75,1.0 (icy blue)')
a.add_argument('--tint-amount', type=float, default=0.6)
a.add_argument('--decimate', type=int, default=0, help='decimate the source mesh to about this many triangles first')
a.add_argument('--tex-size', type=int, default=256, help='max texture size (power of two) for the TGA')
args = a.parse_args(sys.argv[sys.argv.index('--') + 1:])
sys.path.insert(0, args.addon); addon_utils.enable('SKA_Export')
M = json.load(open(args.map)); os.makedirs(args.out, exist_ok=True)

for o in list(bpy.data.objects): bpy.data.objects.remove(o)
getattr(bpy.ops, 'import').ska_file(filepath=args.target, toee_axis_conversion=True)
rig = bpy.data.objects['ToEE Rig']; tmesh = bpy.data.objects['ToEE Model']
tz = [(tmesh.matrix_world @ v.co).z for v in tmesh.data.vertices]; t_height = max(tz) - min(tz)
before = set(bpy.data.objects)
ext = os.path.splitext(args.source)[1].lower()
if ext in ('.glb', '.gltf'): bpy.ops.import_scene.gltf(filepath=args.source)
elif ext == '.blend':  # append every object (armature + meshes) from the source .blend
    with bpy.data.libraries.load(args.source, link=False) as (src_lib, dst_lib): dst_lib.objects = src_lib.objects
    for o in dst_lib.objects:
        if o is not None and o.type in ('ARMATURE', 'MESH'): bpy.context.scene.collection.objects.link(o)
else: bpy.ops.import_scene.fbx(filepath=args.source)
new = [o for o in bpy.data.objects if o not in before]
sarm = next(o for o in new if o.type == 'ARMATURE')
smesh = bpy.data.objects[args.mesh_object] if args.mesh_object else max(
    (o for o in new if o.type == 'MESH' and o.vertex_groups), key=lambda o: len(o.data.vertices))
if sarm.animation_data: sarm.animation_data.action = None
if args.decimate:
    for mod in list(smesh.modifiers): smesh.modifiers.remove(mod)  # rest pose; armature etc. not needed
    if smesh.data.shape_keys: smesh.shape_key_clear()  # basis shape only
    tris = sum(len(p.vertices) - 2 for p in smesh.data.polygons)
    if tris > args.decimate:
        d = smesh.modifiers.new('fit_decimate', 'DECIMATE'); d.ratio = args.decimate / tris
        bpy.context.view_layer.objects.active = smesh; bpy.ops.object.modifier_apply(modifier=d.name)
        print('FIT decimated %d -> %d tris' % (tris, sum(len(p.vertices) - 2 for p in smesh.data.polygons)))
for pb in sarm.pose.bones: pb.matrix_basis = Matrix.Identity(4)
bpy.context.view_layer.update()

# --- 2. scale source to the target height (uniform, about the floor point under its origin)
sw = smesh.matrix_world
sv = [sw @ v.co for v in smesh.data.vertices]
s_minz = min(v.z for v in sv); s_height = max(v.z for v in sv) - s_minz
k = t_height / s_height
S = Matrix.Translation((0, 0, 0)) @ Matrix.Scale(k, 4) @ Matrix.Translation((0, 0, -s_minz))
print('FIT scale %.4f (source %.3f m -> target %.3f m)' % (k, s_height, t_height))

def sjoint(name):  # source bone head, Blender world, after scaling
    return S @ (sarm.matrix_world @ sarm.data.bones[name].head_local)
def tjoint(spec):  # target joint
    if isinstance(spec, list): return Vector(spec)
    floor = spec.endswith('@floor'); name = spec[:-6] if floor else spec
    p = rig.matrix_world @ rig.data.bones[name].head_local
    return Vector((p.x, p.y, 0.0)) if floor else p
def lookup(table, name):
    if name in table: return table[name], True
    for pat, v in table.items():
        if '*' in pat and fnmatch.fnmatch(name, pat): return v, True
    return None, False

# --- 3. per source-bone transforms
T = {}
for b in sarm.data.bones:
    n = b.name
    if n in M['segments']:
        (sa, sb), (ta, tb) = M['segments'][n]
        A, B, C, D = sjoint(sa), sjoint(sb), tjoint(ta), tjoint(tb)
        d1, d2 = (B - A), (D - C)
        R = d1.normalized().rotation_difference(d2.normalized()).to_matrix()
        st = d2.length / max(d1.length, 1e-6); u = d1.normalized()
        def f(p, A=A, C=C, R=R, st=st, u=u):
            r = p - A; par = r.dot(u)
            return C + R @ (u * par * st + (r - u * par))
        T[n] = f
    else:
        v, ok = lookup(M['translate'], n)
        if ok and isinstance(v, dict):  # {"follow": seg}: rigid continuation of another segment
            pass
        elif ok:
            off = tjoint(v[1]) - sjoint(v[0]); T[n] = (lambda p, off=off: p + off)
        else:
            T[n] = (lambda p: p)
            print('FIT warning: source bone %s has no segment/translate rule (left in place)' % n)

def tseg(name):  # ToEE bone segment: head -> head of its first child (or a short stub)
    b = rig.data.bones[name]; h = rig.matrix_world @ b.head_local
    kids = [c for c in b.children if not c.name.endswith('_ref')] or list(b.children)
    t = rig.matrix_world @ kids[0].head_local if kids else rig.matrix_world @ b.tail_local
    return h, t
def split_by_segments(p, names, power=6.0):
    ds = []
    for nm in names:
        h, t = tseg(nm); d = t - h; L2 = max(d.length_squared, 1e-9)
        x = max(0.0, min(1.0, (p - h).dot(d) / L2)); ds.append((nm, max((h + d * x - p).length, 1e-4)))
    ds.sort(key=lambda x: x[1]); ds = ds[:2]
    inv = [(nm, 1.0 / d ** power) for nm, d in ds]; tot = sum(w for _, w in inv)
    return [(nm, w / tot) for nm, w in inv if w / tot > 0.02]

for b in sarm.data.bones:  # resolve "follow" rules once all segments exist
    v, ok = lookup(M['translate'], b.name)
    if b.name not in M['segments'] and ok and isinstance(v, dict): T[b.name] = T[v['follow']]

gname = {g.index: g.name for g in smesh.vertex_groups}
out_co, out_w = [], []
for v, p0 in zip(smesh.data.vertices, sv):
    p = S @ p0
    ws = [(gname[g.group], g.weight) for g in v.groups if g.weight > 1e-4 and g.group in gname]
    tot = sum(w for _, w in ws)
    q = sum((T[n](p) * w for n, w in ws), Vector()) / tot if tot > 0 else p
    out_co.append(q)
    acc = {}
    for n, w in ws:
        tb, ok = lookup(M['weights'], n)
        if not ok: print('FIT warning: no weight rule for', n); continue
        if isinstance(tb, list):  # one source bone covers several ToEE bones: split by distance to their segments
            for bn, ww in split_by_segments(q, tb): acc[bn] = acc.get(bn, 0) + w * ww
        elif tb: acc[tb] = acc.get(tb, 0) + w
    top = sorted(acc.items(), key=lambda x: -x[1])[:6]; s = sum(w for _, w in top) or 1
    out_w.append([(n, w / s) for n, w in top] or [('Bip01 Pelvis', 1.0)])

# --- 4. new mesh in rig-local (= ToEE model) space
inv = rig.matrix_world.inverted()
src = smesh.data
me = bpy.data.meshes.new('fit_tmp')
me.from_pydata([inv @ c for c in out_co], [], [list(p.vertices) for p in src.polygons])
me.update()
# UVs: palette cell per source material
mats = list(src.materials); n = max(1, len(mats)); cell = 8
def tex_of(m):
    if m and m.node_tree:
        for nd in m.node_tree.nodes:
            if nd.type == 'TEX_IMAGE' and nd.image and nd.image.size[0] > 0: return nd.image
image = next((tex_of(m) for m in mats if tex_of(m)), None)
uv = me.uv_layers.new(name='UVMap')
if image is not None:  # textured source: keep its UVs (all materials assumed to share that texture)
    suv = src.uv_layers.active.data
    for p_src, p in zip(src.polygons, me.polygons):
        for ls, ld in zip(p_src.loop_indices, p.loop_indices): uv.data[ld].uv = suv[ls].uv
else:
    image = None
    for p_src, p in zip(src.polygons, me.polygons):
        cx = (p_src.material_index + 0.5) / n
        for li in p.loop_indices: uv.data[li].uv = (cx, 0.5)
tint = [float(x) for x in args.tint.split(',')] if args.tint else None
def tinted(rgb):  # 0..255 sRGB -> blended toward tint * luminance
    if not tint: return rgb
    l = (0.3 * rgb[0] + 0.59 * rgb[1] + 0.11 * rgb[2]) / 255.0
    return tuple(int(max(0, min(255, (1 - args.tint_amount) * c + args.tint_amount * 255 * min(1.0, 1.25 * l + 0.15) * t)))
                 for c, t in zip(rgb, tint))
def lin2srgb(c): return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
cols = []
for m in mats:
    c = (0.7, 0.7, 0.7)
    if m and m.node_tree:
        bsdf = next((nd for nd in m.node_tree.nodes if nd.type == 'BSDF_PRINCIPLED'), None)
        if bsdf: c = tuple(bsdf.inputs['Base Color'].default_value[:3])
    cols.append(tuple(int(round(255 * max(0, min(1, lin2srgb(x))))) for x in c))
cols = cols or [(180, 180, 180)]
if image is not None:
    if max(image.size) > args.tex_size:
        image.scale(min(args.tex_size, image.size[0]), min(args.tex_size, image.size[1]))
    W, H = image.size; f = list(image.pixels)  # float RGBA, bottom row first (= TGA default origin)
    px = bytearray()
    for i in range(W * H):
        r, g, b = tinted(tuple(int(round(255 * max(0, min(1, f[4 * i + c])))) for c in range(3)))
        px += bytes((b, g, r, 255))
    px = bytes(px); cols = 'texture %s %dx%d' % (image.name, W, H)
else:
    cols = [tinted(c) for c in cols]
    W, H = n * cell, cell
    px = b''.join(bytes((cols[x // cell][2], cols[x // cell][1], cols[x // cell][0], 255)) for y in range(H) for x in range(W))
base = os.path.splitext(os.path.basename(args.mdf))[0]
tga_rel = os.path.dirname(args.mdf) + '/' + base + '.tga'
open(os.path.join(args.out, base + '.tga'), 'wb').write(struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, W, H, 32, 8) + px)
open(os.path.join(args.out, base + '.mdf'), 'w').write('Textured\nTexture "%s"\n' % tga_rel)
print('FIT palette', cols)

# triangulate
import bmesh
bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.triangulate(bm, faces=bm.faces[:]); bm.to_mesh(me); bm.free()

# replace the ToEE model mesh
old = tmesh.data; tmesh.data = me
for g in list(tmesh.vertex_groups): tmesh.vertex_groups.remove(g)
for mod in tmesh.modifiers:
    if mod.type == 'ARMATURE': mod.object = rig
bpy.data.meshes.remove(old); me.name = 'ToEE Model'
groups = {}
for vi, ws in enumerate(out_w):
    for bn, w in ws:
        g = groups.get(bn) or tmesh.vertex_groups.new(name=bn); groups[bn] = g
        g.add([vi], w, 'REPLACE')
mat = bpy.data.materials.new(args.mdf); me.materials.append(mat)
me['toee_materials'] = [args.mdf]
for o in new: bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(args.out, 'fit.blend'))
bpy.context.view_layer.objects.active = rig
name = os.path.splitext(os.path.basename(args.target))[0]
tmp = os.path.join(args.out, '_export'); os.makedirs(tmp, exist_ok=True)
bpy.ops.export.ska_file(filepath=os.path.join(tmp, name + '.ska'), write_skm=True)
os.replace(os.path.join(tmp, name + '.skm'), os.path.join(args.out, name + '.SKM'))
print('FIT done: %d verts, %d tris, groups %s' % (len(me.vertices), len(me.polygons), sorted(groups)))
