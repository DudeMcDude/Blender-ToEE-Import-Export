"""ToEE MDF material files, following Temple+ Infrastructure/mdfparser.cpp (MdfParser) and
infrastructure/mdfmaterial.h (MdfMaterial). Pure Python (no bpy), so tools can use it too.

Types: "Textured" (one texture, color, flags), "General" (up to 4 texture stages with per-stage
BlendType/UvType/SpeedU/SpeedV, Color, Specular, SpecularPower, MaterialBlendType, GlossMap, flags)
and "Clipper" (depth-only: Wire, ZFill, Outline). Identifiers are case-insensitive. Colors are
written RGBA (0-255). Speeds are UV units per second in the file (the engine stores them * 60 and
applies them per minute). Placeholder slots (HEAD, GLOVES, CHEST, BOOTS) are not MDF files: the
engine resolves them in AasResolveMaterial (Temple/src/meshes.cpp) and swaps in equipment MDFs."""
import re

PLACEHOLDERS = ("HEAD", "GLOVES", "CHEST", "BOOTS")  # gfx::MaterialPlaceholderSlot
BLEND_STAGE = ("modulate", "add", "texturealpha", "currentalpha", "currentalphaadd")
BLEND_MATERIAL = ("none", "alpha", "add", "alphaadd")
UV_TYPES = ("mesh", "environment", "drift", "swirl", "wavey")


class MdfError(Exception):
    pass


def is_placeholder(name):
    return name in PLACEHOLDERS  # the engine compares exactly (upper case)


def _tokens(text):
    # quoted strings (no escapes for textured files), numbers, identifiers; '#'/'//' comments are not
    # part of the format, but stray text is ignored in non-strict mode like the engine
    for m in re.finditer(r'"([^"]*)"|(-?\d+(?:\.\d*)?|-?\.\d+)|([A-Za-z_][A-Za-z_0-9]*)', text):
        if m.group(1) is not None:
            yield ('str', m.group(1))
        elif m.group(2) is not None:
            yield ('num', float(m.group(2)))
        else:
            yield ('id', m.group(3).lower())


class Sampler:
    __slots__ = ("filename", "blend", "uv", "speed_u", "speed_v")

    def __init__(self):
        self.filename = ""; self.blend = "modulate"; self.uv = "mesh"
        self.speed_u = 1.0; self.speed_v = 0.0  # file units (engine default speedU = 60/60)

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


class Mdf:
    def __init__(self, mtype="textured"):
        self.type = mtype
        self.blend = "alpha"          # MaterialBlendType (engine default Alpha)
        self.specular_power = 50.0
        self.specular = (0, 0, 0, 0)  # RGBA 0-255
        self.color = (255, 255, 255, 255)
        self.glossmap = ""
        self.double = False; self.linear_filtering = False; self.recalculate_normals = False
        self.zfill_only = False; self.colorfill_only = False; self.not_lit = False; self.disable_z = False
        self.clamp = False; self.high_quality = False
        self.wire = False; self.zfill = False; self.outline = False
        self.samplers = [Sampler() for _ in range(4)]
        self.unknown = []

    @property
    def textures(self):
        return [(i, s) for i, s in enumerate(self.samplers) if s.filename]

    def as_dict(self):
        d = {k: v for k, v in self.__dict__.items() if k != 'samplers'}
        d['samplers'] = [s.as_dict() if s.filename else None for s in self.samplers]  # unused stages don't matter
        return d


def parse(text, strict=False):
    toks = list(_tokens(text))
    if not toks or toks[0][0] != 'id' or toks[0][1] not in ("textured", "general", "clipper"):
        raise MdfError("unrecognized material type %r" % (toks[0][1] if toks else ""))
    m = Mdf(toks[0][1]); i = 1

    def nxt(kind=None):
        nonlocal i
        if i >= len(toks): raise MdfError("unexpected end of file")
        t = toks[i]; i += 1
        if kind and t[0] != kind: raise MdfError("expected %s, got %r" % (kind, t[1]))
        return t[1]

    def rgba():
        return tuple(int(nxt('num')) & 0xFF for _ in range(4))

    def stage():
        n = int(nxt('num'))
        if not 0 <= n < 4: raise MdfError("texture stage %d out of range" % n)
        return m.samplers[n]

    flags = {"double": "double", "linearfiltering": "linear_filtering", "recalculatenormals": "recalculate_normals",
             "notlit": "not_lit", "notlite": "not_lit", "disablez": "disable_z", "clamp": "clamp",
             "highquality": "high_quality", "zfillonly": "zfill_only", "colorfillonly": "colorfill_only"}
    while i < len(toks):
        kind, tok = toks[i]; i += 1
        try:
            if kind != 'id':
                raise MdfError("unexpected token %r" % (tok,))
            if m.type == "clipper":
                if tok in ("wire", "zfill", "outline"): setattr(m, tok, True)
                else: raise MdfError("unrecognized token %r" % tok)
            elif tok == "texture":
                if m.type == "textured": m.samplers[0].filename = nxt('str')
                else:
                    s = stage(); s.filename = nxt('str')
            elif tok == "color": m.color = rgba()
            elif tok in flags and (m.type == "general" or tok in ("double", "notlit", "notlite", "disablez", "clamp", "colorfillonly")):
                setattr(m, flags[tok], True)
            elif m.type != "general":
                raise MdfError("unrecognized token %r" % tok)
            elif tok == "glossmap": m.glossmap = nxt('str')
            elif tok == "uvtype":
                s = stage(); v = nxt('id')
                if v not in UV_TYPES: raise MdfError("unrecognized UvType %r" % v)
                s.uv = v
            elif tok == "blendtype":
                s = stage(); v = nxt('id')
                if v not in BLEND_STAGE: raise MdfError("unrecognized BlendType %r" % v)
                s.blend = v
            elif tok == "specular": m.specular = rgba()
            elif tok == "specularpower": m.specular_power = nxt('num')
            elif tok == "materialblendtype":
                v = nxt('id')
                if v not in BLEND_MATERIAL: raise MdfError("unrecognized MaterialBlendType %r" % v)
                m.blend = v
            elif tok == "speed":
                v = nxt('num')
                for s in m.samplers: s.speed_u = s.speed_v = v
            elif tok == "speedu": s = stage(); s.speed_u = nxt('num')
            elif tok == "speedv": s = stage(); s.speed_v = nxt('num')
            else:
                raise MdfError("unrecognized token %r" % tok)
        except MdfError:
            if strict: raise
            m.unknown.append(tok)
    return m


def _fmt(x):
    return ("%d" % x) if float(x).is_integer() else repr(float(x))


def write(m):
    """MDF text for an Mdf (as the stock files are laid out)."""
    L = [m.type.capitalize()]
    if m.type == "clipper":
        L += [k.capitalize() for k in ("wire", "zfill", "outline") if getattr(m, k)]
        return "\n".join(L) + "\n"
    if m.type == "textured":
        if m.samplers[0].filename: L.append('Texture "%s"' % m.samplers[0].filename)
        if m.color != (255, 255, 255, 255): L.append("Color %d %d %d %d" % m.color)
        for k, n in (("double", "Double"), ("not_lit", "notlit"), ("disable_z", "DisableZ"), ("clamp", "Clamp"),
                     ("colorfill_only", "ColorFillOnly")):
            if getattr(m, k): L.append(n)
        return "\n".join(L) + "\n"
    if m.high_quality: L.append("HighQuality")
    for i, s in m.textures:
        L.append('Texture %d "%s"' % (i, s.filename))
        if s.blend != "modulate": L.append("BlendType %d %s" % (i, s.blend.capitalize()))
        if s.uv != "mesh": L.append("UVType %d %s" % (i, s.uv.capitalize()))
        if s.uv in ("drift", "swirl", "wavey") or (s.speed_u, s.speed_v) != (1.0, 0.0):
            L.append("SpeedU %d %s" % (i, _fmt(s.speed_u))); L.append("SpeedV %d %s" % (i, _fmt(s.speed_v)))
    if m.glossmap: L.append('GlossMap "%s"' % m.glossmap)
    if m.color != (255, 255, 255, 255): L.append("Color %d %d %d %d" % m.color)
    if m.specular != (0, 0, 0, 0): L.append("Specular %d %d %d %d" % m.specular)
    if m.specular_power != 50.0: L.append("SpecularPower %s" % _fmt(m.specular_power))
    if m.blend != "alpha": L.append("MaterialBlendType %s" % m.blend.capitalize())
    for k, n in (("double", "Double"), ("linear_filtering", "LinearFiltering"), ("recalculate_normals", "RecalculateNormals"),
                 ("zfill_only", "ZFillOnly"), ("colorfill_only", "ColorFillOnly"), ("not_lit", "notlit"),
                 ("disable_z", "DisableZ")):
        if getattr(m, k): L.append(n)
    return "\n".join(L) + "\n"
