"""Survey SKA files: multi-stream animations, non-unity scale keys, events, raw byte round trip.
python3 ska_survey.py <root dir> [out.json]"""
import sys, os, io, json, contextlib, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'SKA_Export'))
with contextlib.redirect_stdout(io.StringIO()):
    import ska
root = sys.argv[1]; rep = dict(files=0, anims=0, multistream=[], scale=[], scale_initial=[], events=collections.Counter(),
                               event_files=0, event_anims=0, events_total=0, raw_rt_diff=[], errors=[], event_samples={})
for dp, _, fs in os.walk(root):
    for f in fs:
        if not f.lower().endswith('.ska'): continue
        p = os.path.join(dp, f); rel = os.path.relpath(p, root); raw = open(p, 'rb').read()
        s = ska.SkaFile()
        try:
            with contextlib.redirect_stdout(io.StringIO()): s.read(io.BytesIO(raw))
            b = io.BytesIO(); s.write(b)
            if b.getvalue() != raw: rep['raw_rt_diff'].append(rel)
        except Exception as e:
            rep['errors'].append((rel, repr(e))); continue
        rep['files'] += 1; has_ev = False
        for a in s.animation_data:
            rep['anims'] += 1; n = str(a.header.name)
            if a.header.stream_count > 1: rep['multistream'].append((rel, n, a.header.stream_count))
            if a.events:
                has_ev = True; rep['event_anims'] += 1
                for e in a.events:
                    rep['events_total'] += 1; k = '%s|%s' % (e.type, e.action); rep['events'][str(e.type)] += 1
                    rep['event_samples'].setdefault(k, '%s:%s@%d' % (rel, n, e.frame_id))
            for st in a.streams[:1]:
                for bi, keys in st.scale_channels.items():
                    dev = max(max(abs(c - 1.0) for c in sc) for _, sc in keys)
                    if dev > 1e-3:
                        moving = max(max(abs(c - d) for c, d in zip(sc, keys[0][1])) for _, sc in keys)
                        (rep['scale'] if moving > 1e-4 else rep['scale_initial']).append((rel, n, str(s.bone_data[bi].name), round(dev, 4), len(keys)))
        rep['event_files'] += has_ev
print('files %d anims %d errors %d raw-rt-diff %d' % (rep['files'], rep['anims'], len(rep['errors']), len(rep['raw_rt_diff'])))
print('multistream anims', len(rep['multistream']), rep['multistream'][:5])
print('animated scale (keys that change):', len(rep['scale']), 'anims', len(set((r[0], r[1]) for r in rep['scale'])), 'files', sorted(set(r[0] for r in rep['scale']))[:20])
print('constant non-unity scale:', len(rep['scale_initial']), 'files', len(set(r[0] for r in rep['scale_initial'])))
print('events: %d in %d anims, %d files; types %s' % (rep['events_total'], rep['event_anims'], rep['event_files'], dict(rep['events'])))
for k, v in list(rep['event_samples'].items())[:40]: print('  ', k, '->', v)
if len(sys.argv) > 2:
    rep['events'] = dict(rep['events']); json.dump(rep, open(sys.argv[2], 'w'), indent=1)
