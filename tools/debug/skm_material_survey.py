"""python3 skm_material_survey.py <data dir>: material slots of every stock SKM (placeholders per
category, MDF types used), plus which meshes use multi-stage / animated MDFs."""
import os, struct, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'SKA_Export'))
import mdf as M
D = sys.argv[1]; root = os.path.join(D, 'art', 'meshes')
def mats(p):
    b = open(p, 'rb').read()
    nb, ob, nm, om = struct.unpack_from('<4i', b, 0)
    return [b[om + 128 * i: om + 128 * (i + 1)].split(b'\0')[0].decode('latin1') for i in range(nm)]
def find(rel):
    cur = D
    for part in rel.replace('\\', '/').split('/'):
        try: hit = next((n for n in os.listdir(cur) if n.lower() == part.lower()), None)
        except OSError: return None
        if hit is None: return None
        cur = os.path.join(cur, hit)
    return cur
cat = collections.defaultdict(lambda: collections.Counter()); ncat = collections.Counter()
fancy = []; missing = collections.Counter(); per = {}
for dp, _, fs in os.walk(root):
    for f in fs:
        if not f.lower().endswith('.skm'): continue
        p = os.path.join(dp, f); rel = os.path.relpath(p, root); c = rel.split(os.sep)[0]
        ms = mats(p); ncat[c] += 1; per[rel] = ms
        for m in ms:
            if M.is_placeholder(m): cat[c][m] += 1; continue
            q = find(m)
            if q is None: missing[m] += 1; continue
            try: x = M.parse(open(q, 'rb').read().decode('latin1'))
            except M.MdfError: continue
            if len(x.textures) > 1 or any(s.uv != 'mesh' for _, s in x.textures) or x.type != 'textured':
                fancy.append((rel, m, x.type, len(x.textures), [s.uv for _, s in x.textures], [s.blend for _, s in x.textures]))
print('SKMs per category:', dict(ncat))
for c in sorted(cat): print('placeholders in', c, dict(cat[c]))
print('meshes with placeholders:')
for r, ms in sorted(per.items()):
    ph = [m for m in ms if M.is_placeholder(m)]
    if ph: print('  ', r, ph)
print('missing MDFs referenced:', len(missing), list(missing)[:10])
print('non-trivial MDFs on meshes:', len(fancy))
for x in fancy: print('  ', x)
