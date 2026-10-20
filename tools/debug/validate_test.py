"""Export validation: stock models must pass without errors; broken fixtures must give the expected
errors/warnings, and blocked exports must write nothing; auto-fix must not modify the scene mesh.
blender -b --factory-startup --python validate_test.py -- <addon dir> <out dir> <stock.ska> [<stock.ska> ...]"""
import bpy, sys, os, io, contextlib, addon_utils
a = sys.argv[sys.argv.index('--') + 1:]
addon_dir, out, stock = a[0], a[1], a[2:]; os.makedirs(out, exist_ok=True)
sys.path.insert(0, addon_dir)
from SKA_Export import validate as V, anim_compat as AC, ska_events as EV, ska as S
fails = []

def fresh(path):
    bpy.ops.wm.read_factory_settings(use_empty=True); addon_utils.enable('SKA_Export')
    with contextlib.redirect_stdout(io.StringIO()):
        getattr(bpy.ops, 'import').ska_file(filepath=path)
    rig = bpy.data.objects['ToEE Rig']; mesh = bpy.data.objects['ToEE Model']
    bpy.context.view_layer.objects.active = rig
    return rig, mesh

def checks(rig, mesh, auto_fix=False):
    from SKA_Export.export_ska import _ska_actions
    r1, plan = V.check_skm(mesh, rig, auto_fix=auto_fix)
    r2 = V.check_ska(rig, _ska_actions(rig), AC.action_fcurves, EV.collect_events)
    return r1, r2, plan

for p in stock:
    rig, mesh = fresh(p)
    r1, r2, _ = checks(rig, mesh)
    ok = not r1.errors and not r2.errors
    print('VAL stock %-28s %s  skm warnings %s  ska warnings %s' % (os.path.basename(p), 'PASS' if ok else 'FAIL', r1.codes('WARNING'), r2.codes('WARNING')))
    if not ok: fails.append(p); print(r1.text('SKM')); print(r2.text('SKA'))

LIZ = stock[0]
def act0(rig): return next(x for x in bpy.data.actions if len(x.pose_markers))
def quad(rig, mesh):
    import bmesh
    bm = bmesh.new(); bm.from_mesh(mesh.data); bmesh.ops.join_triangles(bm, faces=bm.faces[:40], angle_face_threshold=3.14, angle_shape_threshold=3.14)
    bm.to_mesh(mesh.data); bm.free()
def many_weights(rig, mesh):
    for n in [b.name for b in rig.data.bones][:7]:
        g = mesh.vertex_groups.get(n) or mesh.vertex_groups.new(name=n); g.add([0], 0.1, 'REPLACE')
def weight_issues(rig, mesh):
    for g in mesh.vertex_groups: g.remove([1])
    mesh.vertex_groups[mesh.data.vertices[2].groups[0].group].add([2], 0.3, 'REPLACE')
    g = mesh.vertex_groups[mesh.data.vertices[3].groups[0].group]; mesh.vertex_groups[[x for x in mesh.vertex_groups if x.index != g.index][0].index].add([3], 0.0, 'REPLACE')
    mesh.vertex_groups.new(name='Bogus').add([4], 0.5, 'ADD')
def long_bone(rig, mesh):
    rig.data.bones[3].name = 'B' * 50
def many_bones(rig, mesh):
    bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode='EDIT')
    for i in range(1030):
        b = rig.data.edit_bones.new('x%d' % i); b.head = (0, 0, 0); b.tail = (0, 0, 1)
    bpy.ops.object.mode_set(mode='OBJECT')
def dup_bone(rig, mesh):
    rig.data.bones[4].name = rig.data.bones[5].name.upper() if rig.data.bones[5].name.upper() != rig.data.bones[5].name else rig.data.bones[5].name + 'x'
    if rig.data.bones[4].name.lower() != rig.data.bones[5].name.lower(): rig.data.bones[4].name = rig.data.bones[5].name.swapcase()
def no_mat(rig, mesh): mesh.data.materials.clear(); mesh.data.pop("toee_materials", None)
def long_mat(rig, mesh): mesh.data.materials[0]["toee_mdf_path"] = 'art/meshes/' + 'x' * 130 + '.mdf'  # the per-material SKM name
def bad_mat_idx(rig, mesh): mesh.data.polygons[0].material_index = 7
def no_uv(rig, mesh): mesh.data.uv_layers.remove(mesh.data.uv_layers[0])
def moved(rig, mesh): mesh.location.x += 0.5
def nonuni(rig, mesh): rig.scale = (rig.scale[0], rig.scale[1] * 2, rig.scale[2])  # mesh is parented: follows the rig
def frames(rig, mesh): act0(rig)["toee_frame_count"] = 40000
def ev_long(rig, mesh):
    act = act0(rig); EV.add_event(act, 3, 'script', 'x' * 140); EV.add_event(act, 4, 't' * 50, 'y'); EV.add_event(act, 5, 'sound', 'z')
    EV.add_event(act, 900, 'script', 'anim_obj.footstep()')
def stray(rig, mesh):
    act = rig.animation_data.action; w = AC.ActionWriter(act, rig); fc = w.fcurve('pose.bones["NoSuchBone"].location', 0, '')
    fc.keyframe_points.insert(1, 0.0)
def long_anim(rig, mesh): act0(rig).name = 'a' * 70

SCEN = [  # name, fn, auto_fix, expected errors, expected warnings (subset)
    ('quads', quad, False, {'NOT_TRIANGLES'}, set()),
    ('quads+fix', quad, True, set(), set()),
    ('7 weights', many_weights, False, {'TOO_MANY_WEIGHTS'}, set()),
    ('7 weights+fix', many_weights, True, set(), set()),
    ('weight issues', weight_issues, False, set(), {'UNWEIGHTED_VERTS', 'WEIGHTS_NOT_NORMALIZED', 'ZERO_WEIGHTS', 'VGROUP_NO_BONE'}),
    ('long bone name', long_bone, False, {'BONE_NAME_LONG'}, set()),
    ('1030 extra bones', many_bones, False, {'TOO_MANY_BONES'}, set()),
    ('case-dup bone', dup_bone, False, {'BONE_NAME_DUP'}, set()),
    ('no material', no_mat, False, {'NO_MATERIAL'}, set()),
    ('long material', long_mat, False, {'MATERIAL_NAME_LONG'}, set()),
    ('bad material idx', bad_mat_idx, False, {'MATERIAL_INDEX'}, set()),
    ('no UV', no_uv, False, {'NO_UV'}, set()),
    ('mesh moved', moved, False, {'MESH_TRANSFORM'}, set()),
    ('non-uniform scale', nonuni, False, set(), {'NONUNIFORM_SCALE'}),
    ('frame count', frames, False, {'FRAME_COUNT'}, set()),
    ('events', ev_long, False, {'EVENT_TEXT_LONG', 'EVENT_TYPE_LONG'}, {'EVENT_TYPE_UNKNOWN', 'EVENT_FRAME_RANGE'}),
    ('stray bone curves', stray, False, set(), {'ACTION_UNKNOWN_BONES'}),
    ('long action name', long_anim, False, {'ANIM_NAME_LONG'}, set()),
]
for name, fn, fix, want_e, want_w in SCEN:
    rig, mesh = fresh(LIZ)
    fn(rig, mesh)
    if name == 'long action name' and len(act0(rig).name) <= 63:
        print('VAL %-20s SKIP (this Blender caps ID names at 63)' % name); continue
    nf0 = len(mesh.data.polygons); w0 = [[(g.group, round(g.weight, 6)) for g in v.groups] for v in mesh.data.vertices[:5]]
    r1, r2, plan = checks(rig, mesh, auto_fix=fix)
    got_e = set(r1.codes('ERROR')) | set(r2.codes('ERROR')); got_w = set(r1.codes('WARNING')) | set(r2.codes('WARNING'))
    ok = got_e == want_e and want_w <= got_w
    # operator: blocked exports write nothing; allowed ones write a valid file
    f = os.path.join(out, name.replace(' ', '_').replace('+', '_') + '.ska')
    for x in (f, f[:-4] + '.skm'):
        if os.path.exists(x): os.remove(x)
    bpy.context.view_layer.objects.active = rig
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            res = bpy.ops.export.ska_file(filepath=f, write_skm=True, auto_fix=fix)
    except RuntimeError:  # an ERROR report raises when called from Python
        res = {'CANCELLED'}
    written = os.path.exists(f) or os.path.exists(f[:-4] + '.skm')
    ok = ok and (('CANCELLED' in res and not written) if want_e else ('FINISHED' in res and written))
    extra = ''
    if fix and not want_e:
        unchanged = len(mesh.data.polygons) == nf0 and w0 == [[(g.group, round(g.weight, 6)) for g in v.groups] for v in mesh.data.vertices[:5]]
        m = S.SkmFile()
        with contextlib.redirect_stdout(io.StringIO()): m.read(open(f[:-4] + '.skm', 'rb'))
        v0 = m.vertex_data[0]
        extra = ' scene mesh unchanged %s, exported faces %d (scene %d), v0 weights %d sum %.4f' % (
            unchanged, len(m.face_data), nf0, len(v0.attachment_weights), sum(v0.attachment_weights))
        ok = ok and unchanged and len(v0.attachment_weights) <= 6 and abs(sum(v0.attachment_weights) - 1) < 1e-3 and \
            ('TRIANGULATED' in r1.codes() or len(m.face_data) == nf0)
    print('VAL %-20s %s  errors %s warnings %s%s' % (name, 'PASS' if ok else 'FAIL', sorted(got_e), sorted(got_w & (want_w | {'NONUNIFORM_SCALE'})), extra))
    if not ok: fails.append(name)
print('VAL RESULT', 'ALL PASS' if not fails else 'FAILED: %s' % fails)
