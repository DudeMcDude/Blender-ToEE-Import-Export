"""All SKA events in a data tree: by type and by normalized text (numbers -> N, quoted names -> 'S').
python3 event_survey.py <root> [out.json]"""
import sys, os, io, re, json, contextlib, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'SKA_Export'))
with contextlib.redirect_stdout(io.StringIO()):
    import ska
exact = collections.Counter(); norm = collections.Counter(); files = collections.defaultdict(set); frames0 = collections.Counter()
for dp, _, fs in os.walk(sys.argv[1]):
    for f in fs:
        if not f.lower().endswith('.ska'): continue
        p = os.path.join(dp, f); s = ska.SkaFile()
        try:
            with contextlib.redirect_stdout(io.StringIO()): s.read(open(p, 'rb'))
        except Exception: continue
        for a in s.animation_data:
            for e in a.events:
                t, x = str(e.type), str(e.action).strip()
                exact[(t, x)] += 1
                k = (t, re.sub(r"'[^']*'", "'S'", re.sub(r"\b\d+\b", "N", x)))
                norm[k] += 1; files[k].add(os.path.relpath(p, sys.argv[1]))
print('distinct exact (type, text): %d' % len(exact))
print('normalized kinds:')
for (t, x), c in norm.most_common():
    print('  %6d  %-7s %-60s files %d' % (c, t, x, len(files[(t, x)])))
if len(sys.argv) > 2:
    json.dump(dict(exact=[[t, x, c] for (t, x), c in exact.most_common()],
                   kinds=[[t, x, c, sorted(files[(t, x)])[:10]] for (t, x), c in norm.most_common()]), open(sys.argv[2], 'w'), indent=1)
