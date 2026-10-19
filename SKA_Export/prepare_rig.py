"""'Prepare rig for ToEE': convert an armature authored in Blender convention (Z up, front -Y,
metres, any object transform) into the layout the importer produces, so it exports like an
imported rig.

Imported rigs keep ToEE model-space data (Y up, front +Z, ~inches) inside the rig and show it in
Blender convention through the rig object transform K = Rx(+90 deg) * 0.0254 (import_ska.
toee_to_blender_matrix). For a fresh rig with object transform W this operator applies
M = K^-1 @ W to the armature data (rest pose: edit bones; animation: location keys scale by the
uniform scale of M, rotation/scale keys are unchanged because the basis change conjugates
every bone's local frame identically) and to its skinned meshes, then sets the rig transform to
K. World-space appearance is unchanged (exactly, up to float rounding)."""
import bpy
from . import anim_compat
import mathutils
from bpy.props import BoolProperty, FloatProperty

from .import_ska import toee_to_blender_matrix, TOEE_UNIT_METERS

# Bone names the engine looks up by name (Temple+ source):
#  - inventory.cpp:2522-2551 InventorySystem::GetAttachBone: HEAD_REF (helm), CHEST_REF (necklace,
#    armor), HANDR_REF (main hand, ring), HANDL_REF (off hand, ring, bows), "Bip01 L Forearm" (armor
#    items); names are compared case-insensitively (aas_skeleton.cpp FindBoneIdxByName, _stricmp)
#  - particlesystems.cpp:315-331 IsIgnoredBone/particle attach bones: Casting_ref, origin,
#    "Bip01 Footsteps", FootL_ref, FootR_ref, Head_ref, HandL_ref, HandR_ref, Chest_ref,
#    effects_ref, trap_ref ('#'-prefixed bones are cloth/collision bones, particlesystems.cpp:305)
#  - froggrapplecontroller.cpp:70/78: Tongue_Ref (giant frog), "Bip01 Spine1" (grapple target)
#  - aas_animated_model.cpp:312: "#ClothBone" (cloth simulation, optional)
REQUIRED_BONES = [  # (name, why) -> warning when missing
    ("Bip01", "Biped root; vanilla rigs and SKA events (action 'Bip01'/'origin') use it"),
    ("HandR_ref", "main-hand weapon / ring attachment (inventory.cpp GetAttachBone)"),
    ("HandL_ref", "off-hand, shield-hand, bow attachment (inventory.cpp GetAttachBone)"),
    ("Head_ref", "helmet attachment, head particles"),
    ("Chest_ref", "necklace/armor attachment, chest particles"),
    ("Casting_ref", "spell casting particles"),
]
OPTIONAL_BONES = [
    ("Bip01 L Forearm", "armor item attachment"),
    ("Bip01 Footsteps", "footstep particles"),
    ("FootL_ref", "particles"), ("FootR_ref", "particles"),
    ("Bip01 Spine1", "grapple target (frog)"),
    ("origin", "particles / SKA events"),
]


def is_toee_rig(rig):
    return any(k in rig.keys() for k in ("toee_ska_bones", "toee_axis_conversion", "toee_prepared"))


def check_bones(rig):
    names = {b.name.lower() for b in rig.data.bones}
    missing = [(n, why) for n, why in REQUIRED_BONES if n.lower() not in names]
    missing_opt = [(n, why) for n, why in OPTIONAL_BONES if n.lower() not in names]
    roots = [b.name for b in rig.data.bones if b.parent is None]
    return missing, missing_opt, roots


def _rig_actions(rig):
    names = set(b.name for b in rig.data.bones)
    return [a for a in bpy.data.actions
            if any(fc.data_path.startswith('pose.bones["') and fc.data_path.split('"')[1] in names for fc in anim_compat.action_fcurves(a))]


def _skinned_meshes(rig):
    out = []
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        if ob.parent == rig or any(m.type == 'ARMATURE' and m.object == rig for m in ob.modifiers):
            out.append(ob)
    return out


def _reorder_vertex_groups(ob, rig):
    """SKM export uses the vertex group index as the bone index: rebuild groups in bone order."""
    weights = {}
    for v in ob.data.vertices:
        for g in v.groups:
            weights.setdefault(ob.vertex_groups[g.group].name, []).append((v.index, g.weight))
    old = [vg.name for vg in ob.vertex_groups]
    ob.vertex_groups.clear()
    order = [b.name for b in rig.data.bones] + [n for n in old if n not in rig.data.bones]
    for n in order:
        vg = ob.vertex_groups.new(name=n)
        for vi, w in weights.get(n, []):
            vg.add([vi], w, 'REPLACE')
    return [n for n in old if n not in rig.data.bones]


def prepare_rig(rig, scale=TOEE_UNIT_METERS, add_placeholders=False, rename=True, report=print):
    if rig is None or rig.type != 'ARMATURE':
        raise RuntimeError("Select an armature")
    if is_toee_rig(rig):
        report("'%s' is already a ToEE rig (imported or prepared); nothing done" % rig.name)
        return False
    W = rig.matrix_world.copy()
    sc = W.to_scale()
    if max(sc) - min(sc) > 1e-5 * max(sc):
        raise RuntimeError("Rig object has non-uniform scale %s; apply it first" % tuple(sc))
    K = toee_to_blender_matrix(scale)
    M = K.inverted() @ W
    f = M.to_scale()[0]
    meshes = _skinned_meshes(rig)
    mesh_world = {ob.name: ob.matrix_world.copy() for ob in meshes}

    view = bpy.context.view_layer
    prev_active = view.objects.active
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    view.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    # EditBone.transform() recomputes roll and drifts for some orientations; set the frame directly
    Mrot = M.to_3x3().normalized()
    new = []
    for eb in rig.data.edit_bones:
        R = (Mrot @ eb.matrix.to_3x3()).normalized().to_4x4()
        R.translation = M @ eb.head
        new.append((eb, R, eb.length * f))
    for eb, R, ln in new:
        eb.matrix = R
        eb.length = ln
    bpy.ops.object.mode_set(mode='OBJECT')

    # location keys (and the current pose) are in bone-local rest frames: they only scale by f
    for act in _rig_actions(rig):
        for fc in anim_compat.action_fcurves(act):
            if fc.data_path.startswith('pose.bones["') and fc.data_path.endswith('.location'):
                for kp in fc.keyframe_points:
                    kp.co[1] *= f; kp.handle_left[1] *= f; kp.handle_right[1] *= f
                fc.update()
    for pb in rig.pose.bones:
        pb.location = pb.location * f

    rig.matrix_world = K
    for ob in meshes:
        ob.data.transform(K.inverted() @ mesh_world[ob.name])
        ob.parent = rig
        ob.matrix_parent_inverse = mathutils.Matrix.Identity(4)
        ob.matrix_basis = mathutils.Matrix.Identity(4)
        extra = _reorder_vertex_groups(ob, rig)
        if extra:
            report("WARNING: mesh '%s' has vertex groups without a bone: %s" % (ob.name, extra))

    missing, missing_opt, roots = check_bones(rig)
    if len(roots) != 1:
        report("WARNING: %d root bones %s (vanilla rigs have one root)" % (len(roots), roots))
    for n, why in missing:
        report("WARNING: missing bone '%s': %s" % (n, why))
    for n, why in missing_opt:
        report("note: optional bone '%s' not present (%s)" % (n, why))
    if add_placeholders and missing:
        view.objects.active = rig
        bpy.ops.object.mode_set(mode='EDIT')
        eb_root = rig.data.edit_bones[roots[0]] if roots else None
        for n, _ in missing:
            if n.lower() == "bip01":
                continue  # renaming the root is the user's call
            eb = rig.data.edit_bones.new(n)
            h = eb_root.head.copy() if eb_root else mathutils.Vector((0, 0, 0))
            eb.head = h; eb.tail = h + mathutils.Vector((0, 2.0, 0)); eb.parent = eb_root
            eb.use_deform = False
            report("added placeholder bone '%s' at the root; move it to its place" % n)
        bpy.ops.object.mode_set(mode='OBJECT')

    if rename:  # the SKM exporter expects these names
        for ob, want in ((rig, 'ToEE Rig'),):
            if bpy.data.objects.get(want) in (None, ob): ob.name = want
        if bpy.data.armatures.get('ToEE Model Skeleton') in (None, rig.data): rig.data.name = 'ToEE Model Skeleton'
        if len(meshes) == 1:
            ob = meshes[0]
            if bpy.data.objects.get('ToEE Model') in (None, ob): ob.name = 'ToEE Model'
            if bpy.data.meshes.get('ToEE Model') in (None, ob.data): ob.data.name = 'ToEE Model'
    rig["toee_prepared"] = 1
    rig["toee_axis_conversion"] = scale
    view.objects.active = prev_active if prev_active and prev_active.name in bpy.data.objects else rig
    report("Prepared '%s' for ToEE (basis change M scale %.4f, %d meshes, %d actions)"
           % (rig.name, f, len(meshes), len(_rig_actions(rig))))
    return True


class ToEEPrepareRig(bpy.types.Operator):
    """Convert a rig authored in Blender convention (Z up, front -Y, metres) to ToEE root bones and
    rest pose, keeping it unchanged in the viewport, so it exports like an imported rig"""
    bl_idname = "object.toee_prepare_rig"
    bl_label = "Prepare rig for ToEE"
    bl_options = {'REGISTER', 'UNDO'}

    toee_scale: FloatProperty(name="Unit scale", description="Metres per ToEE unit (1 unit ~ 1 inch)",
                              default=TOEE_UNIT_METERS, min=1e-6, max=1000.0)
    add_placeholders: BoolProperty(name="Add placeholder bones",
                                   description="Add missing *_ref attachment bones at the root", default=False)
    rename: BoolProperty(name="Rename for SKM export",
                         description="Rename rig/armature/mesh to 'ToEE Rig'/'ToEE Model Skeleton'/'ToEE Model'",
                         default=True)

    @classmethod
    def poll(cls, context):
        ob = context.object
        return ob is not None and (ob.type == 'ARMATURE' or (ob.parent is not None and ob.parent.type == 'ARMATURE'))

    def execute(self, context):
        ob = context.object
        rig = ob if ob.type == 'ARMATURE' else ob.parent
        def rep(msg):
            self.report({'WARNING'} if msg.startswith('WARNING') else {'INFO'}, msg); print(msg)
        try:
            prepare_rig(rig, self.toee_scale, self.add_placeholders, self.rename, rep)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e)); return {'CANCELLED'}
        return {'FINISHED'}


def menu_func(self, context):
    self.layout.operator(ToEEPrepareRig.bl_idname)


def register():
    bpy.types.VIEW3D_MT_object.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_object.remove(menu_func)
