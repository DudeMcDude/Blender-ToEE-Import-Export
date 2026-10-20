"""Parse every .mdf under a folder with SKA_Export/mdf.py (strict), count the features used, and
check that write(parse(x)) parses back to the same material. python3 mdf_survey.py <root>"""
import sys, os, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'SKA_Export'))
import mdf
C = collections.Counter(); bad = []; rt_bad = []
for dp, _, fs in os.walk(sys.argv[1]):
    for f in fs:
        if not f.lower().endswith('.mdf'): continue
        p = os.path.join(dp, f); t = open(p, 'rb').read().decode('latin1')
        try:
            m = mdf.parse(t, strict=True)
        except mdf.MdfError as e:
            bad.append((os.path.relpath(p, sys.argv[1]), str(e))); m = mdf.parse(t)
        C['type:' + m.type] += 1; C['textures:%d' % len(m.textures)] += 1; C['blend:' + m.blend] += 1
        for i, s in m.textures:
            C['stage blend:' + s.blend] += 1; C['uv:' + s.uv] += 1
        for k in ('double', 'not_lit', 'disable_z', 'clamp', 'linear_filtering', 'recalculate_normals', 'zfill_only',
                  'colorfill_only', 'high_quality', 'wire', 'zfill', 'outline'):
            if getattr(m, k): C['flag:' + k] += 1
        if m.color != (255, 255, 255, 255): C['color'] += 1
        if m.specular != (0, 0, 0, 0): C['specular'] += 1
        if m.glossmap: C['glossmap'] += 1
        if mdf.parse(mdf.write(m)).as_dict() != {**m.as_dict(), 'unknown': []}: rt_bad.append(p)
print('files', sum(v for k, v in C.items() if k.startswith('type:')), 'strict parse errors', len(bad), 'write/parse mismatches', len(rt_bad))
for k, v in sorted(C.items()): print('  %-28s %d' % (k, v))
for b in bad[:10]: print('  ERR', b)
