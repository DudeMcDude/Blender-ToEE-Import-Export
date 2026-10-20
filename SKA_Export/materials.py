"""Blender materials for ToEE SKM material slots: MDF files -> node materials, body placeholders
(HEAD/GLOVES/CHEST/BOOTS, swapped for equipment MDFs by the engine) -> named placeholder
materials, and back (SKM material names, optional MDF files for new materials)."""
import os
import bpy
from . import mdf as M

PLACEHOLDER_COLORS = {"HEAD": (0.9, 0.75, 0.2, 1), "GLOVES": (0.2, 0.7, 0.9, 1),
                      "CHEST": (0.85, 0.3, 0.3, 1), "BOOTS": (0.4, 0.8, 0.35, 1)}


def resolve_path(data_dir, rel):
    """Case-insensitive lookup of a ToEE data path (backslashes allowed) under data_dir."""
    if not rel:
        return None
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    cur = data_dir or "."
    direct = os.path.join(cur, *parts)
    if os.path.exists(direct):
        return direct
    for p in parts:
        try:
            names = os.listdir(cur)
        except OSError:
            return None
        hit = next((n for n in names if n.lower() == p.lower()), None)
        if hit is None:
            return None
        cur = os.path.join(cur, hit)
    return cur


def _load_image(data_dir, rel, report):
    p = resolve_path(data_dir, rel)
    if p is None:
        report("WARNING: texture '%s' not found under '%s'" % (rel, data_dir)); return None
    try:
        return bpy.data.images.load(p, check_existing=True)
    except RuntimeError as e:
        report("WARNING: could not load texture '%s': %s" % (p, e)); return None


def _sock(node, name, kind='inputs'):
    """Socket by identifier or name (the Mix node has several sockets with the same name)."""
    socks = getattr(node, kind)
    return next((s for s in socks if s.identifier == name), None) or socks[name]


def _mix(nt, blend, a, b, fac=None, x=0, y=0):
    n = nt.nodes.new('ShaderNodeMix'); n.data_type = 'RGBA'; n.blend_type = blend; n.location = (x, y)
    n.clamp_result = True
    if fac is None:
        _sock(n, 'Factor_Float').default_value = 1.0
    else:
        nt.links.new(fac, _sock(n, 'Factor_Float'))
    nt.links.new(a, _sock(n, 'A_Color')); nt.links.new(b, _sock(n, 'B_Color'))
    return _sock(n, 'Result_Color', 'outputs')


def _set_blend(mat, mode):
    """mode: OPAQUE or BLENDED (EEVEE Next 4.2+: surface_render_method; older: blend_method)."""
    if hasattr(mat, 'surface_render_method'):
        mat.surface_render_method = 'DITHERED' if mode == 'OPAQUE' else 'BLENDED'
    if hasattr(mat, 'blend_method') and bpy.app.version < (4, 2, 0):
        mat.blend_method = 'OPAQUE' if mode == 'OPAQUE' else 'BLEND'


def make_placeholder(name):
    mat = bpy.data.materials.new(name)
    mat["toee_placeholder"] = name
    col = PLACEHOLDER_COLORS.get(name, (0.8, 0.8, 0.8, 1))
    mat.diffuse_color = col
    _ensure_nodes(mat)
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = col
    return mat


def _ensure_nodes(mat):
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    if mat.node_tree is None or not any(n.type == 'BSDF_PRINCIPLED' for n in mat.node_tree.nodes):
        nt = mat.node_tree; nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (600, 0)
        b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (200, 0)
        nt.links.new(b.outputs[0], out.inputs['Surface'])


def make_mdf_material(mdf_path, data_dir, report=print):
    """Material for an SKM slot that names an MDF. Missing/unparsable MDFs give a plain material
    that still exports the same path."""
    mat = bpy.data.materials.new(mdf_path)
    mat["toee_mdf_path"] = mdf_path
    _ensure_nodes(mat)
    p = resolve_path(data_dir, mdf_path)
    if p is None:
        report("WARNING: MDF '%s' not found under '%s'" % (mdf_path, data_dir))
        mat.diffuse_color = (1, 0, 1, 1); mat["toee_mdf_missing"] = 1
        return mat
    text = open(p, 'rb').read().decode('latin1')
    mat["toee_mdf"] = text
    try:
        m = M.parse(text)
    except M.MdfError as e:
        report("WARNING: MDF '%s': %s" % (mdf_path, e)); return mat
    if m.unknown:
        report("note: MDF '%s': ignored tokens %s (the engine ignores them too)" % (mdf_path, m.unknown[:5]))
    build_nodes(mat, m, data_dir, report)
    return mat


def build_nodes(mat, m, data_dir, report=print):
    nt = mat.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (1400, 0)
    mat["toee_mdf_type"] = m.type
    mat.use_backface_culling = not m.double
    col = tuple(c / 255.0 for c in m.color)
    if m.type == "clipper":
        tr = nt.nodes.new('ShaderNodeBsdfTransparent'); nt.links.new(tr.outputs[0], out.inputs['Surface'])
        _set_blend(mat, 'BLENDED'); return
    texco = nt.nodes.new('ShaderNodeTexCoord'); texco.location = (-1000, 0)
    fps = bpy.context.scene.render.fps / max(bpy.context.scene.render.fps_base, 1e-6)
    cur_c = cur_a = None; x = -300
    for i, s in m.textures:
        img = _load_image(data_dir, s.filename, report)
        tex = nt.nodes.new('ShaderNodeTexImage'); tex.location = (-500, -300 * i); tex.label = "stage %d" % i
        tex.image = img
        tex.interpolation = 'Linear' if (m.linear_filtering or m.high_quality) else 'Closest' if False else 'Linear'
        tex.extension = 'EXTEND' if m.clamp else 'REPEAT'
        mp = nt.nodes.new('ShaderNodeMapping'); mp.location = (-750, -300 * i)
        nt.links.new(texco.outputs['Reflection' if s.uv == 'environment' else 'UV'], mp.inputs['Vector'])
        nt.links.new(mp.outputs['Vector'], tex.inputs['Vector'])
        mp["toee_uv"] = s.uv
        if s.uv == 'drift':  # engine: uv += speed * seconds (file units)
            for k, sp in ((0, s.speed_u), (1, s.speed_v)):
                if sp:
                    d = mp.inputs['Location'].driver_add('default_value', k).driver
                    d.type = 'SCRIPTED'; d.expression = "frame/%g*%r" % (fps, float(sp))
        elif s.uv in ('swirl', 'wavey'):
            report("note: MDF stage %d uses UvType %s (shown static in Blender)" % (i, s.uv))
        c, a = tex.outputs['Color'], tex.outputs['Alpha']
        if cur_c is None:
            cur_c, cur_a = c, a
        elif s.blend == 'modulate':
            cur_c = _mix(nt, 'MULTIPLY', cur_c, c, x=x, y=-300 * i)
        elif s.blend == 'add':
            cur_c = _mix(nt, 'ADD', cur_c, c, x=x, y=-300 * i)
        elif s.blend == 'texturealpha':
            cur_c = _mix(nt, 'MIX', cur_c, c, fac=a, x=x, y=-300 * i)
        elif s.blend == 'currentalpha':
            cur_c = _mix(nt, 'MIX', cur_c, c, fac=cur_a, x=x, y=-300 * i)
        elif s.blend == 'currentalphaadd':
            cur_c = _mix(nt, 'ADD', cur_c, c, fac=cur_a, x=x, y=-300 * i)
        x += 150
    rgb = nt.nodes.new('ShaderNodeRGB'); rgb.location = (x, 300); rgb.outputs[0].default_value = col; rgb.label = "MDF Color"
    base = _mix(nt, 'MULTIPLY', cur_c, rgb.outputs[0], x=x + 150, y=0) if cur_c is not None else rgb.outputs[0]
    alpha = cur_a
    if col[3] < 1.0:
        mm = nt.nodes.new('ShaderNodeMath'); mm.operation = 'MULTIPLY'; mm.location = (x + 150, -250)
        mm.inputs[1].default_value = col[3]
        if alpha is not None: nt.links.new(alpha, mm.inputs[0])
        else: mm.inputs[0].default_value = 1.0
        alpha = mm.outputs[0]
    if m.not_lit or m.blend in ('add', 'alphaadd'):
        em = nt.nodes.new('ShaderNodeEmission'); em.location = (x + 400, 0); nt.links.new(base, em.inputs['Color'])
        shader = em.outputs[0]
        if m.blend in ('add', 'alphaadd'):  # additive: emission on top of transparent
            tr = nt.nodes.new('ShaderNodeBsdfTransparent'); tr.location = (x + 400, -200)
            ad = nt.nodes.new('ShaderNodeAddShader'); ad.location = (x + 650, 0)
            if m.blend == 'alphaadd' and alpha is not None:
                sc = nt.nodes.new('ShaderNodeMixShader'); sc.location = (x + 550, 100)
                nt.links.new(alpha, sc.inputs['Fac']); nt.links.new(tr.outputs[0], sc.inputs[1]); nt.links.new(em.outputs[0], sc.inputs[2])
                shader = sc.outputs[0]
            nt.links.new(shader, ad.inputs[0]); nt.links.new(tr.outputs[0], ad.inputs[1]); shader = ad.outputs[0]
        elif m.blend == 'alpha' and alpha is not None:
            tr = nt.nodes.new('ShaderNodeBsdfTransparent'); tr.location = (x + 400, -200)
            sc = nt.nodes.new('ShaderNodeMixShader'); sc.location = (x + 650, 0)
            nt.links.new(alpha, sc.inputs['Fac']); nt.links.new(tr.outputs[0], sc.inputs[1]); nt.links.new(em.outputs[0], sc.inputs[2])
            shader = sc.outputs[0]
    else:
        b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (x + 400, 0)
        nt.links.new(base, b.inputs['Base Color'])
        if m.blend == 'alpha' and alpha is not None:
            nt.links.new(alpha, b.inputs['Alpha'])
        if m.specular != (0, 0, 0, 0):
            b.inputs['Roughness'].default_value = max(0.05, min(1.0, 1.0 - m.specular_power / 128.0))
        else:
            b.inputs['Roughness'].default_value = 1.0
        shader = b.outputs[0]
    nt.links.new(shader, out.inputs['Surface'])
    _set_blend(mat, 'OPAQUE' if (m.blend == 'none' or (m.blend == 'alpha' and alpha is None)) else 'BLENDED')


def material_for_slot(name, data_dir, report=print):
    if M.is_placeholder(name):
        return make_placeholder(name)
    if name.lower().endswith('.mdf'):
        return make_mdf_material(name, data_dir, report)
    report("WARNING: material '%s' is neither an MDF nor a placeholder" % name)
    mat = bpy.data.materials.new(name); mat["toee_mdf_path"] = name
    return mat


def skm_material_names(me):
    """SKM material names for the mesh's slots: the material's ToEE path/placeholder (survives slot
    reordering and Blender's 63-char name limit), else the list stored at import, else the name."""
    stored = list(me.get("toee_materials", []))
    out = []
    for i, m in enumerate(me.materials):
        n = ""
        if m is not None:
            n = m.get("toee_mdf_path") or m.get("toee_placeholder") or ""
        if not n:
            n = stored[i] if i < len(stored) else (m.name if m else "")
        out.append(n)
    return out


def mdf_from_material(mat, data_dir):
    """Textured MDF text for a material made in Blender (first image texture, relative to data_dir)."""
    m = M.Mdf("textured")
    img = None
    if mat.node_tree:
        tex = next((n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image), None)
        img = tex.image if tex else None
    if img is not None:
        p = bpy.path.abspath(img.filepath)
        try:
            rel = os.path.relpath(p, data_dir) if data_dir else os.path.basename(p)
        except ValueError:
            rel = os.path.basename(p)
        m.samplers[0].filename = rel.replace(os.sep, "/")
    m.double = not mat.use_backface_culling
    return M.write(m)
