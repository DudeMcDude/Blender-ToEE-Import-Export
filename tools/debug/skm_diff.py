"""Field-by-field SKM comparison. python3 skm_diff.py a.skm b.skm  (also: byte identity)"""
import sys, os, io, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'SKA_Export'))
import contextlib
with contextlib.redirect_stdout(io.StringIO()):
    import ska
def load(p):
    m = ska.SkmFile()
    with contextlib.redirect_stdout(io.StringIO()): m.read(open(p, 'rb'))
    return m
def main(a, b):
    ra, rb = open(a, 'rb').read(), open(b, 'rb').read()
    print('bytes:', 'IDENTICAL' if ra == rb else 'differ (%d vs %d bytes)' % (len(ra), len(rb)))
    A, B = load(a), load(b)
    print('header ints a', np.frombuffer(ra[:40], '<i4').tolist(), '\n             b', np.frombuffer(rb[:40], '<i4').tolist())
    print('counts bones %d/%d mats %d/%d verts %d/%d faces %d/%d' % (len(A.bone_data), len(B.bone_data), len(A.material_data),
          len(B.material_data), len(A.vertex_data), len(B.vertex_data), len(A.face_data), len(B.face_data)))
    bd = []
    for i, (x, y) in enumerate(zip(A.bone_data, B.bone_data)):
        e = np.abs(np.array(x.world_inverse) - np.array(y.world_inverse)).max()
        if str(x.name) != str(y.name) or x.parent_id != y.parent_id or x.flags != y.flags or e > 0:
            bd.append((i, str(x.name), x.parent_id, y.parent_id, x.flags, y.flags, float(e)))
    print('bones differing: %d' % len(bd)); [print('   ', r) for r in bd[:12]]
    print('materials a', [str(m.id) for m in A.material_data], '\n          b', [str(m.id) for m in B.material_data])
    def arr(M, f): return np.array([list(getattr(v, f)) for v in M.vertex_data], float)
    n = min(len(A.vertex_data), len(B.vertex_data))
    for f in ('pos', 'normal', 'uv'):
        x, y = arr(A, f)[:n], arr(B, f)[:n]; d = np.abs(x - y)
        print('vertex %-6s max diff %.3g, exact-equal %d/%d' % (f, d.max(), int((d.max(1) == 0).sum()), n))
    att = sum(1 for x, y in zip(A.vertex_data, B.vertex_data) if list(x.attachment_bones) != list(y.attachment_bones))
    w = max(np.abs(np.array(x.attachment_weights) - np.array(y.attachment_weights)).max() if len(x.attachment_weights) == len(y.attachment_weights) and x.attachment_weights else 0
            for x, y in zip(A.vertex_data, B.vertex_data))
    print('vertex attachments differing %d, weight max diff %.3g' % (att, w))
    fd = sum(1 for x, y in zip(A.face_data, B.face_data) if (x.material_id, tuple(x.vertex_ids)) != (y.material_id, tuple(y.vertex_ids)))
    print('faces differing %d' % fd)
    if ra != rb and len(ra) == len(rb):
        diff = np.nonzero(np.frombuffer(ra, np.uint8) != np.frombuffer(rb, np.uint8))[0]
        print('differing bytes %d, first at %s' % (len(diff), diff[:8].tolist()))
if __name__ == '__main__':
    main(*sys.argv[1:3])
