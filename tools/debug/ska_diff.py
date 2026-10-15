"""Compare two SKA files: structure (header fields, bones, animation headers, events, stream
sharing, keyframe counts) and engine-evaluated vertex/bone error at half-frame steps.
python3 ska_diff.py <file.skm> <orig.ska> <new.ska> [anim,...]   -> also writes <new>.diff.json"""
import sys, os, json, struct, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_eval as E

def summary(path):
    raw = open(path, 'rb').read()
    return dict(size=len(raw), header=struct.unpack('<6i', raw[:24]))

def main(skm, a, b, only=None):
    m1, m2 = E.Model(skm, a), E.Model(skm, b)
    s1, s2 = m1.ska, m2.ska
    rep = dict(orig=summary(a), new=summary(b))
    print('file header (bones,off,var,off,anims,off): orig', rep['orig'], ' new', rep['new'])
    bd = [i for i, (x, y) in enumerate(zip(s1.bone_data, s2.bone_data))
          if (str(x.name), x.parent_id, x.flags) != (str(y.name), y.parent_id, y.flags)
          or np.abs(np.r_[x.scale, x.rotation, x.translation] - np.r_[y.scale, y.rotation, y.translation]).max() > 1e-6]
    print('bones: %d vs %d, differing records: %s' % (len(s1.bone_data), len(s2.bone_data), bd))
    print('streams: %d vs %d' % (len(set(map(id, s1.streams))), len(set(map(id, s2.streams)))))
    rows = []
    for x in s1.animation_data:
        n = str(x.header.name)
        if only and n not in only: continue
        y = m2.anims.get(n)
        if y is None: print('MISSING', n); continue
        hx, hy = x.header, y.header; sx, sy = hx.stream_headers[0], hy.stream_headers[0]
        hdr_same = (hx.drive_type, hx.loopable, hx.event_count, hx.stream_count, sx.frame_count, sx.variation_id, sx.frame_rate, sx.dps) == \
                   (hy.drive_type, hy.loopable, hy.event_count, hy.stream_count, sy.frame_count, sy.variation_id, sy.frame_rate, sy.dps)
        ev_same = [(e.frame_id, str(e.type), str(e.action)) for e in x.events] == [(e.frame_id, str(e.type), str(e.action)) for e in y.events]
        stx, sty = x.streams[0], y.streams[0]
        def cnt(st):
            return sum(len(r.bone_data) for r in st.raw_frames), len(st.initial_state.bone_data)
        frames = np.arange(0, sx.frame_count - 1 + 1e-9, 0.5)
        ve = be = 0.0
        for f in frames:
            W1 = m1.bone_mats(m1.bone_state(x, f)); W2 = m2.bone_mats(m2.bone_state(y, f))
            ve = max(ve, np.abs(m1.skin(W1) - m2.skin(W2)).max())
            be = max(be, max(np.abs(p[:3, 3] - q[:3, 3]).max() for p, q in zip(W1, W2)))
        r = dict(anim=n, header_same=hdr_same, events_same=ev_same, records=cnt(stx), records_new=cnt(sty),
                 lf=(stx.location_factor, sty.location_factor), sf=(stx.scale_factor, sty.scale_factor),
                 vert_err=float(ve), bone_err=float(be))
        rows.append(r)
        print('%-30s hdr %s ev %s recs(keys,init) %s -> %s  lf %.6f->%.6f  vert %.4f bone %.4f' % (
            n, hdr_same, ev_same, r['records'], r['records_new'], *r['lf'], ve, be))
    rep['anims'] = rows
    rep['max_vert_err'] = max(r['vert_err'] for r in rows); rep['max_bone_err'] = max(r['bone_err'] for r in rows)
    print('MAX vertex err %.4f, bone origin err %.4f' % (rep['max_vert_err'], rep['max_bone_err']))
    json.dump(rep, open(b + '.diff.json', 'w'), indent=1)

if __name__ == '__main__':
    main(*sys.argv[1:4], sys.argv[4].split(',') if len(sys.argv) > 4 else None)
