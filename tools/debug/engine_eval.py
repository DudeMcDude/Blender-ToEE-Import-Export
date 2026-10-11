"""Reference evaluator mirroring Temple+ AAS math (numpy, column-vector convention).
Mirrors:
 - Infrastructure/src/aas/aas_anim_player_stream.cpp  Initialize() L165-228, SetFrame() L41-163, GetBoneState() L230-303
 - Infrastructure/include/aas/aas_math.h  slerpQuaternion L146 (XMQuaternionSlerp), rotationMatrix L271 (|v|<1e-4 -> 0)
 - Infrastructure/src/aas/aas_animated_model.cpp  bone matrices L966-987 (W_i = W_parent * T * S_parent^-1 * R * S),
   skinning L597-692 (pos' = full_world_inverse_skm * pos, weighted) and L1170-1185 (boneMatrix * pos')
 - aas_anim_player.cpp L251: frameIndex = frameRate * time
"""
import sys, os, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'SKA_Export'))
import ska

ROT_TRANSPOSE = False  # validated below (see validate())

def qslerp(a, b, t):
    # DirectXMath XMQuaternionSlerp: hemisphere correction, lerp when nearly parallel
    a = np.asarray(a, float); b = np.asarray(b, float)
    c = float(np.dot(a, b))
    if c < 0: b = -b; c = -c
    if c < 1 - 1e-5:
        om = np.arccos(c); s = np.sin(om)
        return (np.sin((1 - t) * om) / s) * a + (np.sin(t * om) / s) * b
    return (1 - t) * a + t * b

def qmat(q):  # q = (x,y,z,w); standard column-convention rotation matrix
    x, y, z, w = q
    m = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                  [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                  [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    if ROT_TRANSPOSE: m = m.T
    m[np.abs(m) < 1e-4] = 0.0
    return m

class Model:
    def __init__(self, skm_path, ska_path):
        self.skm = ska.SkmFile(); self.skm.read(open(skm_path, 'rb'))
        self.ska = ska.SkaFile(); self.ska.read(open(ska_path, 'rb'))
        names = [str(b.name).lower() for b in self.ska.bone_data]
        self.skm2ska = [names.index(str(b.name).lower()) if str(b.name).lower() in names else -1 for b in self.skm.bone_data]
        self.fwi = [np.array(b.world_inverse_matrix, float)[:4] for b in self.skm.bone_data]
        for m in self.fwi: m[3] = [0, 0, 0, 1]
        self.verts = np.array([v.pos[:3] for v in self.skm.vertex_data], float)
        self.anims = {str(a.header.name): a for a in self.ska.animation_data}

    # --- AnimPlayerStream mirror -------------------------------------------------
    def bone_state(self, anim, frame):
        st = anim.streams[0]
        sF, tF, rF = st.scale_factor, st.location_factor, 1/32767.0
        B = []
        for b in self.ska.bone_data:  # Initialize(): skeleton initial state
            d = dict(s=np.array(b.scale, float), r=np.array(b.rotation, float), t=np.array(b.translation, float))
            d.update(ps=d['s'].copy(), pr=d['r'].copy(), pt=d['t'].copy(), sf=0, sn=0, rf=0, rn=0, tf=0, tn=0, sw=0., rw=0., tw=0.)
            B.append(d)
        for bi, kf in st.initial_state.bone_data.items():
            d = B[bi]
            d['s'] = d['ps'] = np.array(kf.scale, float) * sF
            d['t'] = d['pt'] = np.array(kf.translation, float) * tF
            d['r'] = d['pr'] = np.array(kf.rotation, float) * rF
        fr = min(np.floor(frame), 32766)
        for raw in st.raw_frames:  # SetFrame(): advance while keyframeFrame <= floor(frame)
            F = raw.frame
            if F > fr: break
            for bi, kf in raw.bone_data.items():
                d = B[bi]
                if kf.scale is not None:
                    d['sf'], d['sn'], d['ps'] = F, kf.scale_frame, d['s']
                    d['s'] = np.array(kf.scale, float) * sF; d['sw'] = 1/(d['sn']-F) if F < d['sn'] else 0.
                if kf.rotation is not None:
                    d['rf'], d['rn'], d['pr'] = F, kf.rotation_frame, d['r']
                    d['r'] = np.array(kf.rotation, float) * rF; d['rw'] = 1/(d['rn']-F) if F < d['rn'] else 0.
                if kf.translation is not None:
                    d['tf'], d['tn'], d['pt'] = F, kf.translation_frame, d['t']
                    d['t'] = np.array(kf.translation, float) * tF; d['tw'] = 1/(d['tn']-F) if F < d['tn'] else 0.
        out = []
        c, f0 = np.ceil(frame), np.floor(frame)
        for d in B:  # GetBoneState()
            def ch(p, n, fk, nk, w, lerp):
                if c <= d[fk]: return d[p]
                if f0 >= d[nk]: return d[n]
                f = (frame - d[fk]) * d[w]
                return lerp(d[p], d[n], f)
            lin = lambda a, b, f: (1-f)*a + f*b
            out.append((ch('ps', 's', 'sf', 'sn', 'sw', lin), ch('pr', 'r', 'rf', 'rn', 'rw', qslerp), ch('pt', 't', 'tf', 'tn', 'tw', lin)))
        return out

    def bone_mats(self, state):
        W = []
        for i, b in enumerate(self.ska.bone_data):
            s, r, t = state[i]
            M = np.eye(4); M[:3, :3] = qmat(r) @ np.diag(s)
            p = b.parent_id
            if p >= 0:
                M[:3, :3] = np.diag(1/state[p][0]) @ M[:3, :3]
            T = np.eye(4); T[:3, 3] = t
            W.append((W[p] if p >= 0 else np.eye(4)) @ T @ M)
        return W

    def skin(self, W):
        out = np.zeros_like(self.verts)
        for vi, v in enumerate(self.skm.vertex_data):
            p = np.append(self.verts[vi], 1)
            if not v.attachment_bones: out[vi] = p[:3]; continue
            acc = np.zeros(4)
            for b, w in zip(v.attachment_bones, v.attachment_weights):
                acc += w * (W[self.skm2ska[b]] @ (self.fwi[b] @ p))
            out[vi] = acc[:3]
        return out

    def deform_mats(self, W):  # bind-space -> posed, per SKM bone (comparable to Blender pb.matrix @ bone.matrix_local^-1)
        return [W[j] @ self.fwi[i] if j >= 0 else None for i, j in enumerate(self.skm2ska)]

def validate(m):
    st = [(np.array(b.scale), np.array(b.rotation), np.array(b.translation)) for b in m.ska.bone_data]
    W = m.bone_mats(st)
    errs = [np.abs(W[j] @ m.fwi[i] - np.eye(4)).max() for i, j in enumerate(m.skm2ska) if j >= 0]
    return np.median(errs), max(errs)

if __name__ == '__main__':
    A = os.path.join(os.environ.get('TOEE_DATA', 'data'), 'art/meshes/Monsters/Icelizard/icelizard.')
    m = Model(A + 'skm', A + 'ska')
    for tr in (False, True):
        ROT_TRANSPOSE = tr; print('ROT_TRANSPOSE', tr, 'bind-pose deform err median/max', validate(m))
