"""Compare one round trip with the originals (plain python3 + numpy).
python3 rt_compare.py <orig.ska> <orig.skm> <out dir>  -> <out dir>/result.json"""
import sys, os, io, json, re, struct, contextlib, glob, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'debug')); sys.path.insert(0, os.path.join(HERE, '..', '..', 'SKA_Export'))
with contextlib.redirect_stdout(io.StringIO()):
    import ska, engine_eval as E
SAMPLES = int(os.environ.get('RT_SAMPLES', '8'))  # frames sampled per animation (incl. half frames)

def quiet(f, *a):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a)

def skm_names(raw):
    nb, ob, nm, om = struct.unpack_from('<4i', raw, 0)
    return [raw[om + 128 * i: om + 128 * (i + 1)].split(b'\0')[0].decode('latin1') for i in range(nm)]

def skm_fields(a, b):
    """Per-field differences when the SKM is not byte-identical."""
    def load(p):
        m = ska.SkmFile(); quiet(m.read, open(p, 'rb')); return m
    A, B = load(a), load(b); d = {}
    d['counts'] = [(len(A.bone_data), len(B.bone_data)), (len(A.material_data), len(B.material_data)),
                   (len(A.vertex_data), len(B.vertex_data)), (len(A.face_data), len(B.face_data))]
    d['bone_names_same'] = [str(x.name) for x in A.bone_data] == [str(x.name) for x in B.bone_data]
    d['bone_wi'] = float(max((np.abs(np.array(x.world_inverse) - np.array(y.world_inverse)).max()
                              for x, y in zip(A.bone_data, B.bone_data)), default=0))
    n = min(len(A.vertex_data), len(B.vertex_data))
    for f in ('pos', 'normal', 'uv'):
        x = np.array([list(getattr(v, f)) for v in A.vertex_data[:n]], float)
        y = np.array([list(getattr(v, f)) for v in B.vertex_data[:n]], float)
        d['vert_' + f] = float(np.abs(x - y).max()) if n else 0.0
    d['attach_diff'] = sum(1 for x, y in zip(A.vertex_data, B.vertex_data) if list(x.attachment_bones) != list(y.attachment_bones))
    d['faces_diff'] = sum(1 for x, y in zip(A.face_data, B.face_data)
                          if (x.material_id, tuple(x.vertex_ids)) != (y.material_id, tuple(y.vertex_ids)))
    return d

def event_bytes(raw):
    n, off = struct.unpack('<2i', raw[16:24]); out = {}
    f = ska.SkaFile(); f._fileraw = raw; st = f._legacy_anim_stride(n, off)  # older compact headers
    size = st or 236
    for i in range(n):
        h = off + i * size
        if h + size > len(raw): break
        name = raw[h:h + 64].split(b'\0')[0].decode('latin1')
        cnt, eo = struct.unpack('<2i', raw[h + 72:h + 80]) if st == 84 else (0, 0) if st else struct.unpack('<hi', raw[h + 66:h + 72])
        out[name] = raw[h + eo:h + eo + cnt * 178] if cnt > 0 else b''
    return out

def main(oska, oskm, out):
    R = dict(model=oska, status='pass', problems=[]); t0 = time.time()
    bj = os.path.join(out, 'blender.json')
    B = json.load(open(bj)) if os.path.exists(bj) else {}
    R['blender'] = B; log = open(os.path.join(out, 'blender.log'), errors='replace').read() if os.path.exists(os.path.join(out, 'blender.log')) else ''
    R['validation'] = dict(errors=sorted(set(re.findall(r'^\s+ERROR\s+\[(\w+)\]', log, re.M))),
                           warnings=sorted(set(re.findall(r'^\s+WARNING\s+\[(\w+)\]', log, re.M))))
    nska = os.path.join(out, 'out.ska'); nskm = next(iter(glob.glob(os.path.join(out, 'out.[sS][kK][mM]'))), None)
    if B.get('stage') != 'done' or not os.path.exists(nska) or nskm is None:
        R['status'] = 'crash'
        tb = [l for l in log.splitlines() if re.match(r'\w*(Error|Exception)\b', l.strip())]
        R['problems'].append('blender stage %s: %s' % (B.get('stage', 'start'), (tb[-1] if tb else 'no output (timeout?)')[:200]))
        return R
    if R['validation']['errors']: R['problems'].append('validation errors %s' % R['validation']['errors'])
    if R['validation']['warnings']: R['problems'].append('validation warnings %s' % R['validation']['warnings'])
    ro, rn = open(oskm, 'rb').read(), open(nskm, 'rb').read()
    R['skm_identical'] = ro == rn
    if not R['skm_identical']:
        R['skm'] = skm_fields(oskm, nskm)
    R['materials_same'] = skm_names(ro) == skm_names(rn) == B.get('materials', skm_names(rn))
    if not R['materials_same']: R['problems'].append('material names changed')
    ao, an = open(oska, 'rb').read(), open(nska, 'rb').read()
    R['ska_identical'] = ao == an
    eo, en = event_bytes(ao), event_bytes(an)
    R['events'] = sum(len(v) // 178 for v in eo.values())
    R['events_differ'] = [k for k in eo if eo[k] != en.get(k)][:10]
    # SKA: engine math on the original vs exported file, both skinned with the original SKM
    m1 = quiet(E.Model, oskm, oska); m2 = quiet(E.Model, oskm, nska)
    R['anims'] = len(m1.anims); R['missing_anims'] = [n for n in m1.anims if n not in m2.anims][:10]
    # bones the engine actually uses: SKA bones some SKM bone maps to by name (AnimatedModel binds by name);
    # e.g. polarbear.SKM's root 'polarbear' vs the shared SKA's 'Grizzlybear', which never drives anything
    used = sorted(set(i for i in m1.skm2ska if i >= 0))
    R['ska_bones_unused'] = len(m1.ska.bone_data) - len(used)
    worst = []; ve = be = 0.0
    for n, x in m1.anims.items():
        y = m2.anims.get(n)
        if y is None: continue
        fc = x.header.stream_headers[0].frame_count if x.header.stream_headers else 1
        fr = np.unique(np.round(np.linspace(0, max(fc - 1, 0), SAMPLES) * 2) / 2)
        av = ab = 0.0
        for f in fr:
            W1 = m1.bone_mats(m1.bone_state(x, f)); W2 = m2.bone_mats(m2.bone_state(y, f))
            av = max(av, float(np.abs(m1.skin(W1) - m2.skin(W2)).max()) if len(m1.verts) else 0.0)
            ab = max(ab, max((float(np.abs(W1[i][:3, 3] - W2[i][:3, 3]).max()) for i in used), default=0.0))
        worst.append((av, ab, n)); ve = max(ve, av); be = max(be, ab)
    R['vert_err'] = ve; R['bone_err'] = be
    R['worst_anims'] = [dict(anim=n, vert=v, bone=b) for v, b, n in sorted(worst, reverse=True)[:3]]
    R['t_compare'] = round(time.time() - t0, 1)
    return R

if __name__ == '__main__':
    oska, oskm, out = sys.argv[1:4]
    try:
        R = main(oska, oskm, out)
    except Exception as e:
        import traceback
        R = dict(model=oska, status='crash', problems=['compare: %r' % e], trace=traceback.format_exc()[-1500:])
    json.dump(R, open(os.path.join(out, 'result.json'), 'w'), indent=1, default=str)
    print('RT_COMPARED', R['status'])
