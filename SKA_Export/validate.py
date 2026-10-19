"""Pre-export checks against the limits the engine really has (Temple+ Infrastructure/src/aas):

SKM (aas_mesh.h / aas_mesh.cpp)
  MeshVertex.attachmentBone/Weight[sMaxBoneAttachments = 6]      -> max 6 bone weights per vertex
  MeshFace.vertices: int16_t[3], material_idx: int16_t             -> triangles only, max 32767 vertices
  Renderer::RecalcNormals buffer[0x8000] (aas_renderer.cpp)       -> same 32768 bound
  MeshBone.name: char[48]                                         -> bone names max 47 bytes
  MeshMaterial.id: char[128]                                      -> material (MDF path) max 127 bytes
  weights are used as stored, normalized only on cloth skeletons (aas_animated_model.cpp ~372);
  a vertex with no attachments is drawn unskinned ("simply use the vertex position", ~658)
SKA (aas_skeleton.h, aas_animated_model.cpp, aas_anim_player*.cpp)
  SkelBone.name: char[40]                                         -> bone names max 39 bytes
  boneState/bone_mapping[1024], indexed by bone idx + 1           -> max 1023 bones
  SkelAnim.name: char[64]                                         -> action names max 63 bytes
  SkelAnimEvent: int16 frame, char type[48], char action[128]     -> type 47, text 127 bytes
  SkelAnim.eventCount uint16 ("seems to be uint8_t in reality")  -> > 255 events warned
  keyframe frame stored as uint16 (frame << 1), frame clamp 32766 -> max 32766 frames
  bone and animation names are matched case-insensitively (_stricmp)
"""
import bpy

MAX_WEIGHTS = 6
MAX_VERTS = 32767
MAX_BONES = 1023
SKM_BONE_NAME = 47
SKA_BONE_NAME = 39
MATERIAL_NAME = 127
ANIM_NAME = 63
EVENT_TYPE = 47
EVENT_TEXT = 127
MAX_FRAMES = 32766
PLACEHOLDER_MATERIALS = {"CHEST", "BOOTS", "GLOVES", "HEAD"}  # PC body slots replaced by armor at runtime


class Report:
    def __init__(self):
        self.items = []  # (level, code, message)

    def error(self, code, msg): self.items.append(('ERROR', code, msg))
    def warn(self, code, msg): self.items.append(('WARNING', code, msg))
    def info(self, code, msg): self.items.append(('INFO', code, msg))

    @property
    def errors(self): return [i for i in self.items if i[0] == 'ERROR']
    @property
    def warnings(self): return [i for i in self.items if i[0] == 'WARNING']
    def codes(self, level=None): return sorted(set(c for l, c, _ in self.items if level is None or l == level))

    def text(self, title):
        lines = ["%s: %d error(s), %d warning(s)" % (title, len(self.errors), len(self.warnings))]
        for level in ('ERROR', 'WARNING', 'INFO'):
            for l, c, m in self.items:
                if l == level:
                    lines.append("  %-7s [%s] %s" % (l, c, m))
        return "\n".join(lines)

    def publish(self, operator, title):
        """Operator report (shown in the status bar / Info editor), console, and a text block."""
        txt = self.text(title)
        print(txt)
        try:
            tb = bpy.data.texts.get("ToEE Export Report") or bpy.data.texts.new("ToEE Export Report")
            tb.clear(); tb.write(txt + "\n")
        except Exception:
            pass
        if operator is not None:
            for l, c, m in self.items[:40]:
                operator.report({l}, "[%s] %s" % (c, m))
            if self.errors:
                operator.report({'ERROR'}, "%s blocked: %d error(s); see the 'ToEE Export Report' text" % (title, len(self.errors)))


def _nbytes(s):
    return len(s.encode('utf-8'))


def _few(idx, n=8):
    idx = list(idx)
    return ", ".join(str(i) for i in idx[:n]) + (" ..." if len(idx) > n else "")


def _bone_checks(r, rig, name_limit, label):
    bones = rig.data.bones
    if len(bones) == 0:
        r.error('NO_BONES', "armature '%s' has no bones" % rig.name)
    if len(bones) > MAX_BONES:
        r.error('TOO_MANY_BONES', "%d bones; the engine handles at most %d" % (len(bones), MAX_BONES))
    long = [b.name for b in bones if _nbytes(b.name) > name_limit]
    if long:
        r.error('BONE_NAME_LONG', "%d bone name(s) longer than %d bytes (%s %s): %s" % (len(long), name_limit, label,
                'char[%d]' % (name_limit + 1), ", ".join(long[:5])))
    seen = {}
    for b in bones:
        seen.setdefault(b.name.lower(), []).append(b.name)
    dup = [v for v in seen.values() if len(v) > 1]
    if dup:
        r.error('BONE_NAME_DUP', "bone names that differ only in case (the engine matches case-insensitively): %s" % dup[:5])
    nonascii = [b.name for b in bones if not b.name.isascii()]
    if nonascii:
        r.warn('BONE_NAME_ASCII', "non-ASCII bone names: %s" % nonascii[:5])


def check_skm(mesh_obj, rig, auto_fix=False):
    """Returns (report, plan). plan: dict(triangulate=bool, fix_weights=bool) for the export."""
    r = Report(); plan = dict(triangulate=False, fix_weights=False)
    if mesh_obj is None or mesh_obj.type != 'MESH':
        r.error('NO_MESH', "no mesh object to export ('ToEE Model')"); return r, plan
    if rig is None or rig.type != 'ARMATURE':
        r.error('NO_RIG', "no armature to export ('ToEE Rig')"); return r, plan
    me = mesh_obj.data
    _bone_checks(r, rig, SKM_BONE_NAME, 'MeshBone.name')
    if any(_nbytes(b.name) > SKA_BONE_NAME for b in rig.data.bones) and not r.codes('ERROR'):
        r.warn('BONE_NAME_SKA', "bone names over %d bytes don't fit the SKA skeleton (SkelBone.name char[40])" % SKA_BONE_NAME)

    # geometry
    nv, nf = len(me.vertices), len(me.polygons)
    if nv == 0 or nf == 0:
        r.error('EMPTY_MESH', "mesh '%s' has %d vertices, %d faces" % (me.name, nv, nf))
    if nv > MAX_VERTS:
        r.error('TOO_MANY_VERTS', "%d vertices; faces index them with int16, max %d" % (nv, MAX_VERTS))
    ngon = [p.index for p in me.polygons if p.loop_total != 3]
    if ngon:
        if auto_fix:
            plan['triangulate'] = True
            r.info('TRIANGULATED', "%d non-triangle face(s) triangulated in a temporary copy" % len(ngon))
        else:
            r.error('NOT_TRIANGLES', "%d face(s) are not triangles (e.g. %s); enable auto-fix or triangulate" % (len(ngon), _few(ngon)))
    if not me.uv_layers:
        r.error('NO_UV', "mesh '%s' has no UV map" % me.name)

    # materials
    stored = list(me.get("toee_materials", []))
    names = []
    for i, m in enumerate(me.materials):
        names.append(stored[i] if i < len(stored) else (m.name if m else ""))
    if not names:
        r.error('NO_MATERIAL', "mesh has no material slots (SKM needs at least one MDF material)")
    for i, n in enumerate(names):
        if not n:
            r.error('EMPTY_MATERIAL_SLOT', "material slot %d is empty" % i)
        elif _nbytes(n) > MATERIAL_NAME:
            r.error('MATERIAL_NAME_LONG', "material %d name is %d bytes, max %d (MeshMaterial.id char[128])" % (i, _nbytes(n), MATERIAL_NAME))
        elif not n.lower().endswith('.mdf') and n.upper() not in PLACEHOLDER_MATERIALS:
            r.warn('MATERIAL_NOT_MDF', "material %d '%s' is neither an .mdf path nor a body placeholder (%s)" % (
                i, n, "/".join(sorted(PLACEHOLDER_MATERIALS))))
    if names:
        bad = sorted(set(p.material_index for p in me.polygons if p.material_index >= len(names)))
        if bad:
            r.error('MATERIAL_INDEX', "faces use material index %s but there are %d slots" % (bad[:5], len(names)))

    # weights
    bone_names = set(b.name for b in rig.data.bones)
    lower = {b.lower(): b for b in bone_names}
    vg_ok = {vg.index for vg in mesh_obj.vertex_groups if vg.name in bone_names}
    unmatched = [vg.name for vg in mesh_obj.vertex_groups if vg.name not in bone_names]
    if unmatched:
        case = [n for n in unmatched if n.lower() in lower]
        r.warn('VGROUP_NO_BONE', "%d vertex group(s) match no bone and are ignored: %s%s" % (
            len(unmatched), ", ".join(unmatched[:6]), (" (case differs: %s)" % case[:4]) if case else ""))
    over, zero, unnorm, none = [], [], [], []
    for v in me.vertices:
        ws = [g.weight for g in v.groups if g.group in vg_ok]
        if not ws or sum(ws) <= 0:
            none.append(v.index); continue
        if any(w <= 0 for w in ws): zero.append(v.index)
        if sum(1 for w in ws if w > 0) > MAX_WEIGHTS or len(ws) > MAX_WEIGHTS: over.append(v.index)
        if abs(sum(ws) - 1.0) > 1e-3: unnorm.append(v.index)
    if over:
        if auto_fix:
            plan['fix_weights'] = True
            r.info('WEIGHTS_LIMITED', "%d vertices had more than %d weights: kept the %d largest and renormalized (export only)" % (
                len(over), MAX_WEIGHTS, MAX_WEIGHTS))
        else:
            r.error('TOO_MANY_WEIGHTS', "%d vertices have more than %d bone weights (MeshVertex holds %d), e.g. %s" % (
                len(over), MAX_WEIGHTS, MAX_WEIGHTS, _few(over)))
    if zero:
        if auto_fix:
            plan['fix_weights'] = True
            r.info('ZERO_WEIGHTS_DROPPED', "%d vertices had zero weights: dropped them (export only)" % len(zero))
        else:
            r.warn('ZERO_WEIGHTS', "%d vertices have zero-weight entries (they use up attachment slots), e.g. %s" % (len(zero), _few(zero)))
    if unnorm:
        r.warn('WEIGHTS_NOT_NORMALIZED', "%d vertices' weights don't sum to 1 (the engine uses them as stored), e.g. %s" % (
            len(unnorm), _few(unnorm)))
    if none:
        r.warn('UNWEIGHTED_VERTS', "%d vertices have no bone weights and will not move with the skeleton, e.g. %s" % (
            len(none), _few(none)))

    # transforms: the exporter writes mesh-local coordinates in rig space
    try:
        bpy.context.view_layer.update()  # matrix_world is stale right after an edit
    except Exception:
        pass
    rel = rig.matrix_world.inverted_safe() @ mesh_obj.matrix_world
    if any(abs(rel[i][j] - (1.0 if i == j else 0.0)) > 1e-4 for i in range(4) for j in range(4)):
        r.error('MESH_TRANSFORM', "mesh '%s' is moved/rotated/scaled relative to the rig; apply its transform "
                "(Ctrl+A) or reset it, the export ignores object transforms" % mesh_obj.name)
    for ob in (rig, mesh_obj):
        s = ob.matrix_world.to_scale()
        if max(s) - min(s) > 1e-4 * max(abs(max(s)), 1e-9):
            r.warn('NONUNIFORM_SCALE', "object '%s' has non-uniform scale %s" % (ob.name, tuple(round(x, 4) for x in s)))
    mods = [m for m in mesh_obj.modifiers if m.type == 'ARMATURE']
    parented = mesh_obj.parent == rig and mesh_obj.parent_type == 'ARMATURE'
    if not parented and (not mods or all(m.object != rig for m in mods)):
        r.warn('NO_ARMATURE_MODIFIER', "mesh '%s' is neither armature-parented to nor has an Armature modifier for '%s' (the export uses vertex groups anyway)" % (
            mesh_obj.name, rig.name))
    other = [m.name for m in mesh_obj.modifiers if m.type != 'ARMATURE' and m.show_viewport]
    if other:
        r.warn('MODIFIERS_IGNORED', "modifiers are not applied on export: %s" % other[:5])
    return r, plan


def fix_weights(bones, weights):
    """Drop zero weights, keep the 6 largest, renormalize if anything was dropped."""
    pairs = [(b, w) for b, w in zip(bones, weights) if w > 0]
    changed = len(pairs) != len(bones)
    if len(pairs) > MAX_WEIGHTS:
        pairs = sorted(pairs, key=lambda p: -p[1])[:MAX_WEIGHTS]; changed = True
    if changed and pairs:
        s = sum(w for _, w in pairs)
        pairs = [(b, w / s) for b, w in pairs]
    return [b for b, _ in pairs], [w for _, w in pairs]


def triangulated_copy(me):
    """Temporary triangulated copy of mesh data (the caller removes it)."""
    import bmesh
    tmp = me.copy(); tmp.name = me.name + ".toee_export_tmp"
    bm = bmesh.new(); bm.from_mesh(tmp)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(tmp); bm.free()
    return tmp


def check_ska(rig, actions, fcurves_of, events_of):
    r = Report()
    if rig is None or rig.type != 'ARMATURE':
        r.error('NO_RIG', "no armature to export"); return r
    _bone_checks(r, rig, SKA_BONE_NAME, 'SkelBone.name')
    if not actions:
        r.warn('NO_ACTIONS', "no actions animate '%s'; the SKA will have no animations" % rig.name)
    bone_names = set(b.name for b in rig.data.bones)
    seen = {}
    for a in actions:
        seen.setdefault(a.name.lower(), []).append(a.name)
        if _nbytes(a.name) > ANIM_NAME:
            r.error('ANIM_NAME_LONG', "action '%s' name is %d bytes, max %d (SkelAnim.name char[64])" % (a.name, _nbytes(a.name), ANIM_NAME))
        start, end = a.frame_range
        n = int(a.get("toee_frame_count", int(round(end)) - int(round(start)) + 1))
        if n < 1 or n > MAX_FRAMES:
            r.error('FRAME_COUNT', "action '%s' has %d frames (1..%d)" % (a.name, n, MAX_FRAMES))
        stray = sorted(set(fc.data_path.split('"')[1] for fc in fcurves_of(a)
                           if fc.data_path.startswith('pose.bones["') and fc.data_path.split('"')[1] not in bone_names))
        if stray:
            r.warn('ACTION_UNKNOWN_BONES', "action '%s' animates bones not in the skeleton (ignored): %s" % (a.name, stray[:6]))
        try:
            evs = events_of(a)
        except Exception as e:
            r.error('EVENT_INVALID', "action '%s': %s" % (a.name, e)); continue
        if len(evs) > 65535:
            r.error('TOO_MANY_EVENTS', "action '%s' has %d events (uint16)" % (a.name, len(evs)))
        elif len(evs) > 255:
            r.warn('MANY_EVENTS', "action '%s' has %d events; the engine may only read 255 (eventCount 'seems to be uint8')" % (a.name, len(evs)))
        for frame, t, txt, *_ in evs:
            if _nbytes(t) > EVENT_TYPE:
                r.error('EVENT_TYPE_LONG', "action '%s' event at %d: type is %d bytes, max %d (char[48])" % (a.name, frame, _nbytes(t), EVENT_TYPE))
            if _nbytes(txt) > EVENT_TEXT:
                r.error('EVENT_TEXT_LONG', "action '%s' event at %d: text is %d bytes, max %d (char[128])" % (a.name, frame, _nbytes(txt), EVENT_TEXT))
            if t.lower() not in ('script', 'action', 'end'):
                r.warn('EVENT_TYPE_UNKNOWN', "action '%s' event at %d: type '%s' is ignored by the engine (script/action/end)" % (a.name, frame, t))
            if frame < 0 or frame > n - 1:
                r.warn('EVENT_FRAME_RANGE', "action '%s' event at SKA frame %d is outside 0..%d (fires at the end)" % (a.name, frame, n - 1))
    dup = [v for v in seen.values() if len(v) > 1]
    if dup:
        r.warn('ANIM_NAME_DUP', "action names that differ only in case (looked up case-insensitively): %s" % dup[:5])
    return r
