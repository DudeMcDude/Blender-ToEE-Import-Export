"""Ice Lizard lies down on its side and sips coffee.
blender -b --factory-startup --python coffee.py -- <addon dir> <icelizard.ska> <out dir> [render]"""
import bpy, sys, addon_utils, math, mathutils, os
from mathutils import Vector, Quaternion, Matrix
a = sys.argv[sys.argv.index('--') + 1:]; sys.path.insert(0, a[0]); addon_utils.enable('SKA_Export')
OUT = a[2]; RENDER = len(a) > 3 and a[3] == 'render'
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
getattr(bpy.ops, 'import').ska_file(filepath=a[1], toee_axis_conversion=True)
sc = bpy.context.scene; rig = bpy.data.objects['ToEE Rig']; mesh = bpy.data.objects['ToEE Model']
rig.animation_data.action = None
for pb in rig.pose.bones:
    pb.rotation_mode = 'QUATERNION'; pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
W3 = rig.matrix_world.to_3x3()

def to_local(bn):
    b = rig.data.bones[bn]
    return (W3 @ b.matrix_local.to_3x3()).inverted()

def qrot(bn, axis, deg):  # rotation about a rest-pose world axis, as bone-local quaternion
    return Quaternion((to_local(bn) @ Vector(axis)).normalized(), math.radians(deg))

def smooth(t): t = max(0.0, min(1.0, t)); return t * t * (3 - 2 * t)

def mesh_min_z():
    dg = bpy.context.evaluated_depsgraph_get(); ev = mesh.evaluated_get(dg)
    return min((ev.matrix_world @ v.co).z for v in ev.data.vertices)

ROLL_F = 31          # falldown frames
LOOP_F = 120         # prone_idle loop frames
NLOOP = 2
TOTAL = ROLL_F + LOOP_F * NLOOP
ground = mesh_min_z()
pivot = rig.matrix_world @ rig.data.bones['Bip01'].head_local

def body_pose(r):
    """roll fraction r in [0,1] -> (quat, loc) of Bip01 (rest-world rotation about the pivot)."""
    q_w = Quaternion((0, 1, 0), math.radians(-90 * r))
    return q_w

# find drop height for the fully rolled pose
pb_root = rig.pose.bones['Bip01']
pb_root.rotation_quaternion = qrot('Bip01', (0, 1, 0), -90)
bpy.context.view_layer.update()
drop = mesh_min_z() - ground
pb_root.rotation_quaternion = (1, 0, 0, 0)
print('drop', drop)

def loc_local(bn, dw):
    return to_local(bn) @ Vector(dw)

# --- IK setup for the left arm: target and pole empties riding on Bip01 Spine2 (rest-world coords)
def bone_empty(name, p, bone='Bip01 Head'):
    e = bpy.data.objects.new(name, None); sc.collection.objects.link(e)
    e.parent = rig; e.parent_type = 'BONE'; e.parent_bone = bone
    bpy.context.view_layer.update(); e.matrix_world = Matrix.Translation(p); bpy.context.view_layer.update()
    return e
hand0 = rig.matrix_world @ rig.data.bones['Bip01 L Finger1'].head_local
tgt = bone_empty('ik_target', hand0); pole = bone_empty('ik_pole', hand0 + Vector((1.2, 1.0, 0.3)), 'Bip01 Spine2')
def key_target(p, f):  # set target at rest-world point p (pose must be at rest)
    tgt.matrix_world = Matrix.Translation(p); bpy.context.view_layer.update()
    tgt.keyframe_insert('location', frame=f)
mouth = Vector([float(x) for x in os.environ.get('MOUTH', '0.2,-0.38,4.15').split(',')])   # in front of the lower jaw, after the head nods down
rest_hand = hand0 + Vector((-0.3, -0.5, 0.15))   # claw resting on the chest
# loop timing (frames within loop)
LIFT0, LIFT1, SIP0, SIP1, LOW0, LOW1 = 18, 46, 52, 76, 84, 112
key_target(hand0, 1); key_target(rest_hand, ROLL_F)
for k in range(NLOOP):
    o = ROLL_F + k * LOOP_F
    key_target(rest_hand, o + LIFT0); key_target(mouth, o + LIFT1); key_target(mouth + Vector((0, -0.04, 0.06)), o + SIP1)
    key_target(mouth, o + LOW0); key_target(rest_hand, o + LOW1)
for fc in tgt.animation_data.action.fcurves:
    for kp in fc.keyframe_points: kp.interpolation = 'BEZIER'; kp.easing = 'AUTO'
ik = rig.pose.bones['Bip01 L Finger1'].constraints.new('IK'); ik.use_tail = False
ik.target = tgt; ik.pole_target = pole; ik.chain_count = 3; ik.pole_angle = 0
ik_w = lambda f: smooth((f - 4) / (ROLL_F - 8))   # blend IK in during the roll
# --- mug, parented to the left hand bone
bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.11, depth=0.26)
mug = bpy.context.object; mug.name = 'mug'
bpy.ops.mesh.primitive_torus_add(major_radius=0.07, minor_radius=0.02)
handle = bpy.context.object; handle.rotation_euler = (math.radians(90), 0, 0); handle.location = (0.12, 0, 0)
bpy.ops.object.select_all(action='DESELECT'); handle.select_set(True); mug.select_set(True)
bpy.context.view_layer.objects.active = mug; bpy.ops.object.join()
mug.color = (0.55, 0.3, 0.15, 1)
bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.095, depth=0.01, location=(0, 0, 0.11))
coffee = bpy.context.object; coffee.color = (0.18, 0.08, 0.03, 1)
coffee.parent = mug
# the mug sits in the claw: handle facing the claw, a bit in front of the hand head
mug.parent = rig; mug.parent_type = 'BONE'; mug.parent_bone = 'Bip01 L Hand'
bpy.context.view_layer.update()
hand_b = rig.data.bones['Bip01 L Hand']
mug_pos = hand0 + Vector((0.0, -0.13, 0.0))   # between thumb and claw
# mug upright in the world once the lizard lies on its right side: axis = rest +X, handle towards the claw (+Y)
R = Matrix(((0, 0, 1), (1, 0, 0), (0, 1, 0))).to_4x4()
mug.matrix_world = Matrix.Translation(mug_pos) @ R
bpy.context.view_layer.update()

# --- FK keyframes per frame (procedural)
def setpose(f):
    if f <= ROLL_F:
        r = smooth((f - 1) / (ROLL_F - 1)); t = None
    else:
        r = 1.0; t = (f - ROLL_F) % LOOP_F
    P = rig.pose.bones
    # roll + drop, with a little settle bounce at the end of the roll
    settle = 0.0 if f <= ROLL_F else 0.04 * math.exp(-(f - ROLL_F) / 6.0) * math.sin((f - ROLL_F) / 2.0)
    P['Bip01'].rotation_quaternion = qrot('Bip01', (0, 1, 0), -90 * r)
    P['Bip01'].location = loc_local('Bip01', (0, 0, -(drop - settle) * r))
    # breathing
    ph = 2 * math.pi * ((f - ROLL_F) / LOOP_F if t is not None else 0)
    breathe = math.sin(2 * ph) * 1.5
    P['Bip01 Spine1'].rotation_quaternion = qrot('Bip01 Spine1', (1, 0, 0), breathe * r)
    # legs relax and tuck a bit
    for s, sg in (('L', 1), ('R', -1)):
        P['Bip01 %s Thigh' % s].rotation_quaternion = qrot('Bip01 %s Thigh' % s, (1, 0, 0), -25 * r) @ qrot('Bip01 %s Thigh' % s, (0, 1, 0), sg * 10 * r)
        P['Bip01 %s Calf' % s].rotation_quaternion = qrot('Bip01 %s Calf' % s, (1, 0, 0), 20 * r)
    # right (lower) arm lies relaxed
    P['Bip01 R UpperArm'].rotation_quaternion = qrot('Bip01 R UpperArm', (1, 0, 0), -20 * r)
    # wings fold back and close to the body
    for wn, sg in (('wing_arm_L', 1), ('wing_arm_R', -1)):
        P[wn].rotation_quaternion = qrot(wn, (1, 0, 0), -70 * r) @ qrot(wn, (0, 1, 0), sg * 12 * r)
    # head/neck nod towards the mug, jaw, tail sway
    nod = jaw = tilt = 0.0
    if t is not None:
        lift = smooth((t - LIFT0) / (LIFT1 - LIFT0)) - smooth((t - LOW0) / (LOW1 - LOW0))
        sip = smooth((t - SIP0) / 8) - smooth((t - SIP1 + 8) / 8)
        nod = 14 * lift + 6 * sip
        jaw = 10 * smooth((t - LIFT1 + 10) / 10) - 10 * smooth((t - LOW0) / 8) + 4 * sip * math.sin(math.pi * (t - SIP0) / 6) ** 2
        tilt = 25 * sip
    nod += 12 * r  # look along the ground towards the claw
    P['Bip01 Neck'].rotation_quaternion = qrot('Bip01 Neck', (1, 0, 0), -0.4 * nod) @ qrot('Bip01 Neck', (0, 0, 1), 8 * r)
    P['Bip01 Head'].rotation_quaternion = qrot('Bip01 Head', (1, 0, 0), -0.6 * nod) @ qrot('Bip01 Head', (0, 1, 0), -10 * r)
    P['Bip01 Ponytail1'].rotation_quaternion = qrot('Bip01 Ponytail1', (1, 0, 0), max(0.0, jaw))
    P['Bip01 L Finger0'].rotation_quaternion = qrot('Bip01 L Finger0', (1, 0, 0), 15 * r)
    P['Bip01 L Finger01'].rotation_quaternion = qrot('Bip01 L Finger01', (1, 0, 0), 25 * r)
    P['Bip01 L Finger1'].rotation_quaternion = qrot('Bip01 L Finger1', (1, 0, 0), -20 * r)
    P['Bip01 L Finger11'].rotation_quaternion = qrot('Bip01 L Finger11', (1, 0, 0), -35 * r)
    mug.delta_rotation_euler = (0, 0, 0); mug.delta_rotation_euler[1] = math.radians(-tilt)
    mug.keyframe_insert('delta_rotation_euler', frame=f)
    tails = ['Bip01 Tail', 'Bip01 Tail1', 'Bip01 Tail2', 'Bip01 Tail3', 'Bip01 Tail4']
    for i, tn in enumerate(tails):
        sway = (7 + 2 * i) * math.sin(ph - 0.6 * i) * r
        P[tn].rotation_quaternion = qrot(tn, (1, 0, 0), sway) @ qrot(tn, (0, 0, 1), 3 * r)
    ik.influence = ik_w(f)

# Evaluate every frame and record visual local transforms (IK baked in)
names = [b.name for b in rig.data.bones]
baked = {}
for f in range(1, TOTAL + 1):
    sc.frame_set(f); setpose(f); bpy.context.view_layer.update()
    m = {}
    for pb in rig.pose.bones:
        m[pb.name] = rig.convert_space(pose_bone=pb, matrix=pb.matrix, from_space='POSE', to_space='LOCAL')
    baked[f] = m
rig.pose.bones['Bip01 L Finger1'].constraints.remove(ik)

def make_action(name, f0, n, props):
    act = bpy.data.actions.new(name)
    for k, v in props.items(): act[k] = v
    act["toee_frame_count"] = n
    rig.animation_data.action = act
    for i in range(n):
        f = f0 + i
        for pb in rig.pose.bones:
            loc, rot, scl = baked[f][pb.name].decompose()
            pb.location = loc; pb.rotation_quaternion = rot
            pb.keyframe_insert('location', frame=1 + i, group=pb.name)
            pb.keyframe_insert('rotation_quaternion', frame=1 + i, group=pb.name)
    return act

def props_of(n):
    o = bpy.data.actions[n]; return {k: o[k] for k in o.keys()}
pf, pp = props_of('falldown'), props_of('prone_idle')
for n in ('falldown', 'prone_idle'):
    bpy.data.actions.remove(bpy.data.actions[n])
fall = make_action('falldown', 1, ROLL_F, pf)
loop = make_action('prone_idle', ROLL_F, LOOP_F + 1, pp)   # first == last frame -> seamless loop
full = make_action('coffee_preview', 1, TOTAL, {})
full.use_fake_user = True
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'coffee.blend'))
# export the SKA (preview action is not part of the export)
bpy.data.actions.remove(full)
rig.animation_data.action = loop
bpy.context.view_layer.objects.active = rig
bpy.ops.export.ska_file(filepath=os.path.join(OUT, 'icelizard.ska'))
print('EXPORTED')
