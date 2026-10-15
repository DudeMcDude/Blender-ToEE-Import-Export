"""Blender-free check of the SKA keyframe encoder: decode every animation of an SKA with the
engine reference evaluator, re-encode it from dense per-frame samples with ska.encode_stream,
write a new SKA and compare engine-evaluated bone matrices of both files at half-frame steps.
Usage: python3 ska_reencode.py <file.skm> <file.ska> [out.ska]"""
import sys, os, io, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_eval as E
ska = E.ska

def main(skm, skap, out=None):
    m = E.Model(skm, skap)
    src = m.ska
    new = ska.SkaFile(); new.bone_data = src.bone_data
    cache = {}
    for a in src.animation_data:
        st = a.streams[0]; n = a.header.stream_headers[0].frame_count
        if id(st) not in cache:
            bones = sorted(st.initial_state.bone_data)
            samples = {b: ([], [], []) for b in bones}
            for f in range(n):
                state = m.bone_state(a, f)
                for b in bones:
                    s, r, t = state[b]
                    samples[b][0].append(tuple(s)); samples[b][1].append(tuple(r)); samples[b][2].append(tuple(t))
            cache[id(st)] = ska.encode_stream(str(a.header.name), samples)
        na = ska.SkaAnim(); na.header = ska.SkaAnimHeader(str(a.header.name))
        h = a.header
        na.header.drive_type, na.header.loopable = h.drive_type, h.loopable
        sh = ska.SkaAnimStreamHeader(); o = h.stream_headers[0]
        sh.frame_count, sh.variation_id, sh.frame_rate, sh.dps = o.frame_count, o.variation_id, o.frame_rate, o.dps
        na.header.stream_headers = [sh]; na.streams = [cache[id(st)]]; na.events = a.events
        new.animation_data.append(na)
    bio = io.BytesIO(); new.write(bio)
    out = out or '/tmp/reencoded.ska'
    open(out, 'wb').write(bio.getvalue())
    m2 = E.Model(skm, out)
    worst = 0
    for a in src.animation_data:
        a2 = m2.anims[str(a.header.name)]; n = a.header.stream_headers[0].frame_count
        e = 0
        for f in np.arange(0, n - 1 + 1e-9, 0.5):
            W1 = m.bone_mats(m.bone_state(a, f)); W2 = m2.bone_mats(m2.bone_state(a2, f))
            V1 = m.skin(W1); V2 = m2.skin(W2)
            e = max(e, np.abs(V1 - V2).max())
        worst = max(worst, e)
        print('%-32s vertex max err %.4f' % (a.header.name, e))
    print('size orig %d new %d; worst %.4f' % (os.path.getsize(skap), len(bio.getvalue()), worst))

if __name__ == '__main__':
    main(*sys.argv[1:])
