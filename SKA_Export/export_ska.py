import struct
import os
import bpy
import mathutils    
from bpy_extras import io_utils, node_shader_utils
import time
from bpy_extras.wm_utils.progress_report import (
    ProgressReport,
    ProgressReportSubstep,
)

from .ska import FixedLengthName, SkmFile, SkmBone, SkmMaterial, SkaFile, SkaBone, MdfFile, SkmVertex, SkmFace, \
    SkaAnim, SkaAnimHeader, SkaAnimStreamHeader, SkaEvent, encode_stream

progress = None

def matrix4_to_3x4_array(mat):
    """Concatenate matrix's columns into a single, flat tuple"""
    return [tuple(v) for v in mat[0:3]]

def vector_to_array(vec):
    result = tuple(f for f in vec)
    return result

def mat_to_mdf_file(mat_wrap, mdf_file_path):
    mdf_file = MdfFile()

    # source_dir = os.path.dirname(bpy.data.filepath)
    # dest_dir   = os.path.dirname(filepath)

    # Currently supporting only mat_wrap.base_color_texture
    mat_wrap_key = 'base_color_texture'
    tex_wrap = getattr(mat_wrap, mat_wrap_key, None)
    if tex_wrap is None:
        return
    image = tex_wrap.image
    if image is None:
        return
    
    mdf_file.texture_filepath = image.filepath
    # path_mode = 'AUTO'
    # filepath = io_utils.path_reference(image.filepath, source_dir, dest_dir,
    #                                                 path_mode, "", copy_set, image.library)
    
    def proc_node_tex(nodetex):
        # TODO handle texture scaling & translation
        tex_offset = nodetex.translation
        tex_scale  = nodetex.scale
        tex_coord  = nodetex.texcoords
        assert tex_offset[0] == 0.0
        assert tex_offset[1] == 0.0
        assert tex_offset[2] == 0.0
        assert tex_scale[0] == 1.0
        assert tex_scale[1] == 1.0
        assert tex_scale[2] == 1.0
        assert tex_coord == 'UV'
        return

    proc_node_tex(mat_wrap.base_color_texture)
    # elif mapto == 'SPECULARITY':
    #     _generic_tex_set(mat_wrap.specular_texture, image, 'UV', tex_offset, tex_scale)
    # elif mapto == 'ALPHA':
    #     _generic_tex_set(mat_wrap.alpha_texture, image, 'UV', tex_offset, tex_scale)
    # elif mapto == 'NORMAL':
    #     _generic_tex_set(mat_wrap.normalmap_texture, image, 'UV', tex_offset, tex_scale)

    with open(mdf_file_path, 'w') as file:
        mdf_file.write(file)

    return
    


def blender_to_skm(mesh, rig, WRITE_MDF):
    skm_data = SkmFile()

    contextMaterial = None
    context_mat_wrap = None
    contextMatrix_rot = None

    contextObName = "ToEE Model"
    rigObName = "ToEE Rig"
    armatureName = "ToEE Model Skeleton"

    TEXTURE_DICT = {}
    MATDICT = {}
    WRAPDICT = {}
    copy_set = set() # set of files to copy (texture images...)
    
        
    def mesh_to_skm_mesh(skm_data):  # myContextMesh_vertls, myContextMesh_facels, myContextMeshMaterials):
        '''
        Creates Mesh Object from vertex/face/material data
        '''
        bmesh = bpy.data.meshes['ToEE Model']

        vertex_count = len(bmesh.vertices)
        face_count   = len(bmesh.polygons)

        print("%d vertices, %d faces" % (vertex_count, face_count))

        # Create vertices
        for vtx in bmesh.vertices:
            skm_vtx = SkmVertex()
            skm_vtx.pos = vtx.co.to_tuple() + (0.0,)
            skm_vtx.normal = vtx.normal.to_tuple() + (0.0,)
            skm_data.vertex_data.append(skm_vtx)
        assert len(skm_data.vertex_data) == vertex_count

        # Create faces (Triangles). Note: face should be triangles only!
        for p in bmesh.polygons:
            loop_start = p.loop_start
            loop_total = p.loop_total
            assert loop_total == 3, "Faces must be triangles!"
            face = bmesh.loops[loop_start+0].vertex_index, bmesh.loops[loop_start+1].vertex_index, bmesh.loops[loop_start+2].vertex_index
            skm_face = SkmFace()
            skm_face.vertex_ids = face
            skm_data.face_data.append(skm_face)
        assert len(skm_data.face_data) == face_count

        
        # Get UV coordinates for each polygon's vertices
        print("Setting UVs")
        uvl = bmesh.uv_layers[0].data[:]
        for fidx, fa in enumerate(skm_data.face_data):
            fa.material_id = bmesh.polygons[fidx].material_index

        for fidx, pl in enumerate(bmesh.polygons):
            face = skm_data.face_data[fidx]
            v1, v2, v3 = face.vertex_ids

            skm_data.vertex_data[v1].uv = uvl[pl.loop_start + 0].uv
            skm_data.vertex_data[v2].uv = uvl[pl.loop_start + 1].uv 
            skm_data.vertex_data[v3].uv = uvl[pl.loop_start + 2].uv
        
    def rig_to_skm_bones(skm_data):
        '''
        Converts rig/armature objects to SKM Bones
        '''
        # Bones
        print("Getting bones")
        obj = bpy.data.objects[contextObName]
        barm = bpy.data.armatures[armatureName]
        rig = bpy.data.objects[rigObName]
        
        bpy.context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')  # set to Edit Mode so bones can be accessed

        bone_ids = {}

        for bone_id, bone in enumerate(barm.edit_bones):
            bone_name = bone.name
            bone_ids[bone_name] = bone_id

            skm_bone = SkmBone(Name = bone_name)

            if bone.parent is None:
                skm_bone.parent_id = -1
            else:
                skm_bone.parent_id = bone_ids[bone.parent.name]

            world = bone.matrix
            wi = world.inverted_safe()
            skm_bone.world_inverse = matrix4_to_3x4_array(wi)

            skm_data.bone_data.append(skm_bone)
        
        # Exit edit mode
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')
        
        for vidx, vtx in enumerate(obj.data.vertices):
            for i, vg in enumerate(vtx.groups):
                bone_id = vg.group
                bone_wt = vg.weight
                skm_data.vertex_data[vidx].attachment_bones.append(bone_id)
                skm_data.vertex_data[vidx].attachment_weights.append(bone_wt)
            if skm_data.vertex_data[vidx].attachment_count > 6:
                raise Exception(f"Too many bone attachments for vertex {vidx}! Max is 6")
        
        return
    
    def material_to_skm_mat(mat_wrap, mdf_file_path):
        skm_mat = SkmMaterial(mdf_file_path)
        return skm_mat

    ## Create materials
    progress.enter_substeps(3, "Processing data...")
    progress.step("Processing Materials and images...")
    for mm in bpy.data.materials: #skm_data.material_data:  

        material_name = mm.name
        if not material_name.lower().endswith('mdf'):
            print('Skipping material whose name doesn\'t end with .mdf: %r' % material_name)
            continue

        assert mm.use_nodes, "export_ska assumes use_nodes = True!"
        contextMaterial = mm

        mat_wrap = node_shader_utils.PrincipledBSDFWrapper(contextMaterial, is_readonly=False)
        assert mat_wrap.use_nodes == True, "huh? no use_nodes in wrapper?"
        context_mat_wrap = mat_wrap


        
        print("Converting material to SKM format: %s" % material_name)

        skm_mat = material_to_skm_mat(mat_wrap, material_name)
        if WRITE_MDF:
            mat_to_mdf_file(mat_wrap, skm_mat.id)

        MATDICT[material_name] = contextMaterial
        WRAPDICT[contextMaterial] = context_mat_wrap
        
        skm_data.material_data.append(skm_mat)


    # Convert Mesh object
    progress.step("Processing Mesh...")
    mesh_to_skm_mesh(skm_data)

    # Create Rig
    progress.step("Processing Rig...")
    rig_to_skm_bones(skm_data)

    # copy all collected files.
    io_utils.path_reference_copy(copy_set)

    progress.leave_substeps("Finished SKM conversion.")
    return skm_data



def _write_skm(context, filepath, 
    EXPORT_ANIMATION = False,
    WRITE_MDF = False,
    global_matrix = None):
    global progress    

    with ProgressReport(context.window_manager) as progress:
        # Exit edit mode before exporting, so current object states are exported properly.
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        mesh = bpy.context.scene.objects['ToEE Model']
        rig = bpy.context.scene.objects['ToEE Rig']
        skm_data = blender_to_skm(mesh, rig, WRITE_MDF)
        
        
        skm_filepath = os.path.splitext(filepath)[0] + '.skm'
        with open(skm_filepath, 'wb') as skm_file:
            skm_data.write(skm_file)
    return


def _rig_ska_skeleton(rig):
    """SKA skeleton table for the rig: the table saved by the importer if present (keeps the
    original bone order, bones missing from the SKM and the initial states), else one built
    from the Blender bones (order of rig.data.bones, initial state = rest pose)."""
    import json
    bones = []
    if "toee_ska_bones" in rig.keys():
        for d in json.loads(rig["toee_ska_bones"]):
            b = SkaBone(d["name"], d["parent"])
            b.flags = d.get("flags", 0)
            b.scale = tuple(d["scale"]); b.rotation = tuple(d["rotation"]); b.translation = tuple(d["translation"])
            bones.append(b)
        return bones
    names = [b.name for b in rig.data.bones]
    for bb in rig.data.bones:
        b = SkaBone(bb.name, names.index(bb.parent.name) if bb.parent else -1)
        rel = bb.matrix_local if bb.parent is None else bb.parent.matrix_local.inverted() @ bb.matrix_local
        loc, rot, sca = rel.decompose()
        b.scale = tuple(sca); b.rotation = (rot.x, rot.y, rot.z, rot.w); b.translation = tuple(loc)
        bones.append(b)
    return bones


def _rest_state(rig, bone_name):
    """(rest_loc, rest_rot) relative to the parent; inverse of import_ska.RestBoneState."""
    bb = rig.data.bones[bone_name]
    if "toee_rest_rot" in bb.keys():
        return mathutils.Vector(bb["toee_rest_loc"]), mathutils.Quaternion(bb["toee_rest_rot"])
    rel = bb.matrix_local if bb.parent is None else bb.parent.matrix_local.inverted() @ bb.matrix_local
    loc, rot, _ = rel.decompose()
    return loc, rot


def _sample_action(rig, action, ska_bones, frame_start, frame_count):
    """Dense engine-space samples at each integer SKA frame, from the action's F-Curves.
    Engine rotation  = rest_rot @ pose_rot,  translation = rest_rot @ pose_loc + rest_loc
    (exact inverse of the importer). Bones without curves are left out of the stream, so the
    engine uses the skeleton's initial state for them, as for vanilla files."""
    curves = dict()
    for fc in action.fcurves:
        dp = fc.data_path
        if not dp.startswith('pose.bones["'):
            continue
        bname = dp[len('pose.bones["'):dp.index('"]')]
        prop = dp[dp.rindex('.') + 1:]
        curves.setdefault(bname, dict())[(prop, fc.array_index)] = fc
    by_name = {str(b.name).lower(): i for i, b in enumerate(ska_bones)}
    out = dict()
    for bname, cv in curves.items():
        bi = by_name.get(bname.lower())
        if bi is None or bname not in rig.pose.bones:
            continue
        pb = rig.pose.bones[bname]
        rest_loc, rest_rot = _rest_state(rig, bname)
        ss, rs, ts = [], [], []
        for f in range(frame_count):
            bf = frame_start + f
            def ev(prop, idx, default):
                fc = cv.get((prop, idx))
                return fc.evaluate(bf) if fc is not None else default
            if pb.rotation_mode == 'QUATERNION':
                q = mathutils.Quaternion([ev('rotation_quaternion', k, (1, 0, 0, 0)[k]) for k in range(4)])
            else:
                q = mathutils.Euler([ev('rotation_euler', k, 0.0) for k in range(3)], pb.rotation_mode).to_quaternion()
            q.normalize()
            # channels without a curve take the rest pose / skeleton default, never the current
            # (possibly stale, left over from another action) pose-bone value
            loc = mathutils.Vector([ev('location', k, 0.0) for k in range(3)])
            sca = [ev('scale', k, ska_bones[bi].scale[k]) for k in range(3)]
            qe = rest_rot @ q
            te = rest_rot @ loc + rest_loc
            ss.append(tuple(sca)); rs.append((qe.x, qe.y, qe.z, qe.w)); ts.append(tuple(te))
        out[bi] = (ss, rs, ts)
    return out


def blender_to_ska(rig, actions, rot_tol=1e-4):
    import json
    ska_data = SkaFile()
    ska_data.bone_data = _rig_ska_skeleton(rig)
    streams_by_bytes = dict()
    for action in actions:
        start = int(round(action.frame_range[0]))
        if "toee_frame_count" in action.keys():
            start = 1  # importer convention: SKA frame f is Blender frame 1 + f
            frame_count = int(action["toee_frame_count"])
        else:
            frame_count = int(round(action.frame_range[1])) - start + 1
        samples = _sample_action(rig, action, ska_data.bone_data, start, frame_count)
        # Bones that never leave the skeleton's initial state need no stream entry (the importer
        # adds constant keys for them, so drop those again).
        for bi in list(samples):
            sk = ska_data.bone_data[bi]
            ss, rs, ts = samples[bi]
            q0 = mathutils.Quaternion((sk.rotation[3], sk.rotation[0], sk.rotation[1], sk.rotation[2])).normalized()  # some Nub defaults are not unit (0,0,0,0.707)
            if all(max(abs(a - b) for a, b in zip(s, sk.scale)) < 1e-4 and
                   max(abs(a - b) for a, b in zip(t, sk.translation)) < 1e-3 and
                   q0.rotation_difference(mathutils.Quaternion((r[3], r[0], r[1], r[2]))).angle < 1e-4
                   for s, r, t in zip(ss, rs, ts)):
                del samples[bi]
        stream = encode_stream(action.name, samples, rot_tol=rot_tol)
        # identical keyframe data is stored once (vanilla files share streams, e.g. walk/run)
        from io import BytesIO
        bio = BytesIO(); stream.write(bio)
        stream = streams_by_bytes.setdefault(bio.getvalue(), stream)

        anim = SkaAnim()
        anim.header = SkaAnimHeader(action.name)
        anim.header.drive_type = int(action.get("toee_drive_type", 0))
        anim.header.loopable = int(action.get("toee_loopable", 0))
        sh = SkaAnimStreamHeader()
        sh.frame_count = frame_count
        sh.variation_id = int(action.get("toee_variation_id", -1))
        sh.frame_rate = float(action.get("toee_frame_rate", 30.0))
        sh.dps = float(action.get("toee_dps", 0.0))
        anim.header.stream_headers = [sh]
        anim.header.stream_count = 1
        anim.streams = [stream]
        anim.events = [SkaEvent(fr, ty, ac) for fr, ty, ac in json.loads(action.get("toee_events", "[]"))]
        anim.header.event_count = len(anim.events)
        ska_data.animation_data.append(anim)
    return ska_data


def _ska_actions(rig):
    """Actions that animate the rig's bones, in original SKA order (imported ones first)."""
    names = set(b.name for b in rig.data.bones)
    acts = [a for a in bpy.data.actions
            if any(fc.data_path.startswith('pose.bones["') and fc.data_path.split('"')[1] in names for fc in a.fcurves)]
    return sorted(acts, key=lambda a: (int(a.get("toee_index", 1 << 30)), a.name))


def _write_ska(context, filepath, WRITE_SKM=False, WRITE_MDF=False, ONLY_ACTIVE_ACTION=False, **_):
    global progress
    print("\n*** Exporting SKA ***")
    time1 = time.perf_counter()
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    rig = _find_rig(context)
    if ONLY_ACTIVE_ACTION and rig.animation_data and rig.animation_data.action:
        actions = [rig.animation_data.action]
    else:
        actions = _ska_actions(rig)
    ska_data = blender_to_ska(rig, actions)
    ska_filepath = os.path.splitext(filepath)[0] + '.ska'
    with open(ska_filepath, 'wb') as f:
        ska_data.write(f)
    print("Wrote %s: %d bones, %d animations, %d streams" % (ska_filepath, len(ska_data.bone_data),
          len(ska_data.animation_data), len(set(id(s) for s in ska_data.streams))))
    if WRITE_SKM:
        _write_skm(context, filepath, WRITE_MDF=WRITE_MDF)
    print("SKA export time: %.2f" % (time.perf_counter() - time1))
    return


def _find_rig(context):
    ob = context.object
    if ob is not None and ob.type == 'ARMATURE':
        return ob
    if ob is not None and ob.parent is not None and ob.parent.type == 'ARMATURE':
        return ob.parent
    rig = bpy.context.scene.objects.get('ToEE Rig')
    if rig is None:
        raise RuntimeError("No armature selected (and no 'ToEE Rig' in the scene)")
    return rig


def save(operator, context, filepath="", write_skm=False, only_active_action=False, **_):
    _write_ska(context, filepath, WRITE_SKM=write_skm, ONLY_ACTIVE_ACTION=only_active_action)
    return {'FINISHED'}


def blender_save_ska(operator, context, filepath="", use_selection=True, global_matrix=None,):
    _write_ska(context, filepath)
    return {'FINISHED'}

def blender_save_skm(operator, context, filepath="", use_selection=True, global_matrix=None,):
    _write_skm(context, filepath)
    return {'FINISHED'}
