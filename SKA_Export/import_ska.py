import math
import os
import time

import bpy
from . import anim_compat
from . import materials, ska_events
import mathutils
from mathutils import Vector, Quaternion

from .ska import SkaAnimStream, _q_slerp
from .ska import SkmFile, SkaFile, MdfFile
from bpy_extras.wm_utils.progress_report import ProgressReport
from bpy_extras import node_shader_utils

global scn
scn = None
progress = None

object_dictionary = {}
object_matrix = {}
# rig_dictionary = {}
global ToEE_data_dir
SLERP_BAKE_ANGLE = 0.35  # rad (~20 deg); nlerp error above this becomes visible
ToEE_data_dir = ""  # ToEE data dir. Extracted from the filename, assuming it is located inside the data/art folder, and its textures are all present there.


def load_material_image(mat_wrap, image, texture, scale, offset, extension, mapto):
    
    if mapto not in {'COLOR', 'SPECULARITY', 'ALPHA', 'NORMAL'}:
        print(
            "\tError: Cannot map to %r\n\tassuming diffuse color. modify material %r later." %
            (mapto, mat_wrap.name)
        )
        raise Exception("Invalid mapto %r" % mapto)
        mapto = "COLOR"

    if image:
        texture.image = image
    
    def _generic_tex_set(nodetex, image, texcoords, translation, scale):
        nodetex.image = image
        nodetex.texcoords = texcoords
        if translation is not None:
            nodetex.translation = translation
        if scale is not None:
            nodetex.scale = scale

    
    tex_scale = (scale[0], scale[1], 1.0)
    tex_offset = (offset[0], offset[1], 0.0)

    
    if mapto == 'COLOR':
        _generic_tex_set(mat_wrap.base_color_texture, image, 'UV', tex_offset, tex_scale)
    elif mapto == 'SPECULARITY':
        _generic_tex_set(mat_wrap.specular_texture, image, 'UV', tex_offset, tex_scale)
    elif mapto == 'ALPHA':
        _generic_tex_set(mat_wrap.alpha_texture, image, 'UV', tex_offset, tex_scale)
    elif mapto == 'NORMAL':
        _generic_tex_set(mat_wrap.normalmap_texture, image, 'UV', tex_offset, tex_scale)


def skm_to_blender(skm_data, importedObjects, IMAGE_SEARCH):
    from bpy_extras.image_utils import load_image

    contextObName = None
    contextMaterial = None
    context_mat_wrap = None
    contextMatrix_rot = None  # Blender.mathutils.Matrix(); contextMatrix.identity()
    # contextMatrix_tx = None # Blender.mathutils.Matrix(); contextMatrix.identity()

    TEXTURE_DICT = {}
    MATDICT = {}
    WRAPDICT = {}
    # mdf_resolve
        # read_texture
            # bpy_extras.image_utils.load_image
            # load_material_image

    
    def read_texture(texture_path, name, mapto):
        new_texture = bpy.data.textures.new(name, type='IMAGE')

        u_scale, v_scale, u_offset, v_offset = 1.0, 1.0, 0.0, 0.0
        mirror = False
        extension = 'wrap'  # 'mirror', 'decal'

        img = TEXTURE_DICT[contextMaterial.name] = load_image(texture_path, ToEE_data_dir)

        # add the map to the material in the right channel
        if img:
            load_material_image(context_mat_wrap, img, new_texture, (u_scale, v_scale),
                                    (u_offset, v_offset), extension, mapto)

    def mdf_resolve(mdf_filename):
        mdf_fullpath = os.path.join(ToEE_data_dir, mdf_filename)
        if not os.path.exists(mdf_fullpath):
            print("MDF %s not found" % mdf_fullpath)
            return
        
        with open(mdf_fullpath, 'rb') as mdf_file:
            mdf_raw = mdf_file.read()

        mdf_data = MdfFile()
        mdf_data.from_raw_data(mdf_raw)
        
        print("Registering texture: %s" % mdf_data.texture_filepath)
        read_texture(mdf_data.texture_filepath, "Diffuse",
                     "COLOR")  # "Specular / SPECULARITY", "Opacity / ALPHA", "Bump / NORMAL"
        return
    
        
    def putContextMesh(skm_data):  # myContextMesh_vertls, myContextMesh_facels, myContextMeshMaterials):
        '''
        Creates Mesh Object from vertex/face/material data
        '''
        # Create new mesh
        bmesh = bpy.data.meshes.new(contextObName)

        vertex_count = len(skm_data.vertex_data)
        face_count = len(skm_data.face_data)
        print("------------ FLAT ----------------")
        print("%d vertices, %d faces" % (vertex_count, face_count))

        # Create vertices
        bmesh.vertices.add(vertex_count)
        flattened_vtx_pos = [t for vtx in skm_data.vertex_data for t in vtx.pos[0:3]]
        bmesh.vertices.foreach_set("co", flattened_vtx_pos)

        # Create faces (Triangles) - make face_count Polygons, each loop defined by 3 vertices
        bmesh.polygons.add(face_count)
        bmesh.loops.add(face_count * 3)
        bmesh.polygons.foreach_set("loop_start", range(0, face_count * 3, 3))
        bmesh.polygons.foreach_set("loop_total", (3,) * face_count)
        flattened_face_vtx_map = [t for fa in skm_data.face_data for t in fa.vertex_ids]
        bmesh.loops.foreach_set("vertex_index", flattened_face_vtx_map)

        # Apply Materials
        for mm in skm_data.material_data:
            mat_name = mm.id.name
            bmat = MATDICT.get(mm.id.name)
            if bmat:
                img = TEXTURE_DICT.get(bmat.name)
            else:
                print(" WARNING! Material %s not defined!" % mat_name)
                bmat = MATDICT[mat_name] = bpy.data.materials.new(mat_name)
                img = None
            bmesh.materials.append(bmat)
        # keep the exact SKM material list (incl. non-.mdf placeholders like CHEST/BOOTS) for export
        bmesh["toee_materials"] = [mm.id.name for mm in skm_data.material_data]
        # vanilla files have junk after the NUL in the 128-byte name field; keep it for byte-exact export
        bmesh["toee_materials_raw"] = [bytes(getattr(mm.id, 'raw', None) or b'').hex() for mm in skm_data.material_data]

        # Get UV coordinates for each polygon's vertices
        print("Setting UVs")
        bmesh.uv_layers.new(do_init = False)
        uv_faces = bmesh.uv_layers.active.data[:]
        if uv_faces:
            for fidx, fa in enumerate(skm_data.face_data):
                bmesh.polygons[fidx].material_index = fa.material_id
                # bmat = bmesh.materials[fa.material_id]
                # img = TEXTURE_DICT.get(bmat.name)
                # uv_faces[fidx].image = img
            uvl = bmesh.uv_layers.active.data[:]
            for fidx, pl in enumerate(bmesh.polygons):
                face = skm_data.face_data[fidx]
                v1, v2, v3 = face.vertex_ids

                uvl[pl.loop_start + 0].uv = skm_data.vertex_data[v1].uv
                uvl[pl.loop_start + 1].uv = skm_data.vertex_data[v2].uv
                uvl[pl.loop_start + 2].uv = skm_data.vertex_data[v3].uv

        # Finish up
        n_before = len(bmesh.polygons)
        bmesh.validate()
        if len(bmesh.polygons) != n_before:
            # Blender drops duplicate faces (stock double-sided parts repeat a triangle with the same vertices);
            # keep the original face list so an unchanged mesh exports the same faces
            bmesh["toee_faces"] = [x for fa in skm_data.face_data for x in (*fa.vertex_ids, fa.material_id)]
            print("note: %d duplicate face(s) merged by Blender; kept for export" % (n_before - len(bmesh.polygons)))
        bmesh.update()
        # preserve the SKM vertex normals instead of letting Blender/exporter recompute them
        try:
            if hasattr(bmesh, 'use_auto_smooth'):  # Blender < 4.1
                bmesh.use_auto_smooth = True
            bmesh.normals_split_custom_set_from_vertices(
                [Vector(vtx.normal[0:3]).normalized() for vtx in skm_data.vertex_data])
        except Exception as e:
            print(" WARNING! could not set custom normals: %s" % e)
        # exact SKM normals (custom normals are stored compressed); used on export while the
        # custom normal still matches, i.e. the normal was not edited
        attr = bmesh.attributes.new("toee_skm_normal", 'FLOAT_VECTOR', 'POINT')
        attr.data.foreach_set("vector", [t for vtx in skm_data.vertex_data for t in vtx.normal[0:3]])
        # marks imported vertices, so stored zero-length normals (51 of 76 in PC_AsianHat) export as zero too
        flag = bmesh.attributes.new("toee_skm_normal_set", 'BOOLEAN', 'POINT')
        flag.data.foreach_set("value", [True] * len(skm_data.vertex_data))

        # Create new object from mesh
        ob = bpy.data.objects.new(contextObName, bmesh)
        object_dictionary[contextObName] = ob
        importedObjects.append(ob)

        collection = SCN.collection
        collection.objects.link(ob)
        ob.select_set(True)

        if contextMatrix_rot:
            ob.matrix_local = contextMatrix_rot
            object_matrix[ob] = contextMatrix_rot.copy()

    def putRig(skm_data):
        '''
        Creates rig object for Mesh Object, and parents it (Armature type parenting, so it deforms it via bones)
        '''
        # Bones
        print("Getting bones")
        obj = object_dictionary[contextObName]
        barm = bpy.data.armatures.new(armatureName)
        rig = bpy.data.objects.new(rigObName, barm)
        SCN.collection.objects.link(rig)
        bpy.context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')  # set to Edit Mode so bones can be added
        bone_dump = open(os.path.join(ToEE_data_dir, "bone_dump.txt"), 'w')

        fh = open(os.path.join(ToEE_data_dir, "bones.txt"), "wt")

        vertex_groups = dict()

        for bone_id, bd in enumerate(skm_data.bone_data):
            bone_name = str(bd.name)
            bone = barm.edit_bones.new(bone_name)  # type: bpy.types.EditBone
            # engine: a bone's own rotation/scale ignore the parent's scale, only its position follows it
            # (aas_animated_model.cpp parent-scale compensation) == Blender's inherit_scale NONE
            bone.inherit_scale = 'NONE'
            bone.select = True

            wi = mathutils.Matrix(bd.world_inverse_matrix)
            world = wi.inverted_safe()

            bone.head = Vector([0, 0, 0])
            bone.tail = Vector([0, 0, 5])
            bone.matrix = world

            print("****************************************************************************", file=fh)
            print(bone_name, file=fh)
            print("BONE MATRIX:", file=fh)
            print(bone.matrix, file=fh)
            print("WORLD INVERSE:", file=fh)
            print(world, file=fh)
            print("****************************************************************************", file=fh)

            vg = obj.vertex_groups.new(name = bone_name)  # Create matching vertex groups
            vertex_groups[bone_id] = vg

        # set parents after all bones exist (SKA parent may come later in SKM order)
        for bone_id, bd in enumerate(skm_data.bone_data):
            if bd.parent_id != -1:
                barm.edit_bones[bone_id].parent = barm.edit_bones[bd.parent_id]
        fh.close()
        bone_dump.close()
        bpy.ops.object.mode_set(mode='OBJECT')  # do an implicit update
        # Remember original SKM bone data so the exporter can write it back verbatim
        # unless the bone was edited (detected via the stored rest matrix).
        for bone_id, bd in enumerate(skm_data.bone_data):
            b = barm.bones[str(bd.name)]  # bones are re-sorted by hierarchy after edit mode
            b["toee_skm_index"] = bone_id
            b["toee_skm_flags"] = int(bd.flags)
            pid = getattr(bd, 'skm_parent_id', bd.parent_id)
            b["toee_skm_parent"] = str(skm_data.bone_data[pid].name) if pid >= 0 else ""
            b["toee_skm_world_inverse"] = [float(x) for row in bd.world_inverse for x in row]
            b["toee_rest_matrix"] = [x for row in b.matrix_local for x in row]
            b["toee_rest_parent"] = b.parent.name if b.parent else ""
        # parent obj with rig, using Armaturre type parenting so Bones will deform vertices
        obj.parent = rig
        obj.parent_type = 'ARMATURE'

        print("********************************************************")
        print("BONE WEIGHTS")
        print("********************************************************")

        # Set Vertex bone weights
        for vidx, vtx in enumerate(skm_data.vertex_data):
            attachment_count = len(vtx.attachment_bones)
            for i in range(0, attachment_count):
                bone_id = vtx.attachment_bones[i]
                bone_wt = vtx.attachment_weights[i]
                vertex_groups[bone_id].add((vidx,), bone_wt, 'ADD')

        # object_dictionary[rigObName] = obj
        # rig_dictionary[contextObName] = obj
        importedObjects.append(obj)

    def dump_bones():
        bone_dump = open(os.path.join(ToEE_data_dir, 'bone_dump_skm.txt'), 'w')
        for skm_bone_id, bd in enumerate(skm_data.bone_data):
            bone_dump.write(
                "\n\n*******  %d %s  ********** " % (skm_bone_id, str(bd.name)) + " Parent: (%d)" % (bd.parent_id))
            bone_dump.write("\n")
            bone_dump.write("WorldInverse matrix: " + str(bd.world_inverse))
            bone_dump.write("\n")
        bone_dump.close()
    contextObName = "ToEE Model"
    rigObName = "ToEE Rig"
    armatureName = "ToEE Model Skeleton"
    
    ## Create materials
    progress.step("Loading materials and images...")
    # create_materials(skm_data)
    for mm in skm_data.material_data:  
        mdf_path = mm.id.name  # path relative to data_dir (that's how ToEE rolls)
        material_name = mdf_path

        if material_name in MATDICT:
            continue
        # MDF -> node material (stages, blend, color, UV anim), HEAD/CHEST/... -> placeholder
        contextMaterial = materials.material_for_slot(material_name, ToEE_data_dir)
        print("Registering material: %s" % material_name)
        MATDICT[material_name] = contextMaterial

    # Create Mesh object
    progress.step("Creating Mesh...")
    putContextMesh(skm_data)

    # Create Rig
    progress.step("Creating Rig...")
    putRig(skm_data)

    dump_bones()
    return


class RestBoneState:
    def __init__(self, loc, rot, sca):
        self.loc = loc
        self.rot = rot
        self.sca = sca

    def get_rel_rot(self, rot):
        return self.rot.inverted() @ rot

    def get_rel_loc(self, loc):
        return self.rot.inverted() @ (loc - self.loc)  # basis loc is in the bone rest frame (cf. dirty branch)

    def apply_to_posebone(self, posebone, loc=None, rot=None, sca=None):
        
        if rot is not None:
            posebone.rotation_quaternion = self.get_rel_rot(rot)
        if loc is not None:
            posebone.location = self.get_rel_loc(loc)
        


def ska_to_blender(ska_data, skm_data, importedObjects, USE_INHERIT_ROTATION, USE_LOCAL_LOCATION,
                   APPLY_ANIMATIONS):
    print("Importing animations")
    contextObName = "ToEE Model"
    ska_rig_name = "SKA Rig"
    ska_armature_name = "SKA Armature"

    ob = object_dictionary[contextObName]
    rig = ob.parent
    barm = rig.data
    scn = bpy.context.scene

    def dump_bones():
        bone_dump = open(os.path.join(ToEE_data_dir, 'bone_dump_ska.txt'), 'w')
        for ska_bone_id, bd in enumerate(ska_data.bone_data):
            bone_dump.write(
                "\n\n*******  %d %s  ********** " % (ska_bone_id, str(bd.name)) + " Parent: (%d)" % (bd.parent_id))
            bone_dump.write("\n")
            bone_dump.write("Scale vec: " + str(bd.scale))
            bone_dump.write("\n")
            bone_dump.write("Rotation vec: " + str(bd.rotation))
            bone_dump.write("\n")
            bone_dump.write("Translation vec: " + str(bd.translation))
            bone_dump.write("\n")
        bone_dump.close()

    
    dump_bones()
    ska_to_skm_bone_mapping = ska_data.get_ska_to_skm_bone_map(skm_data)

    # State (loc, rot, sca) for each of the bones in rest position, relative to parent
    bone_rest_state = dict()
    for ska_bone_id, skm_bone_id in ska_to_skm_bone_mapping.items():
        skm_bone = skm_data.bone_data[skm_bone_id]
        ska_bone = ska_data.bone_data[ska_bone_id]
        
        rest_world = mathutils.Matrix(skm_bone.world_inverse_matrix).inverted()
        if ska_bone.parent_id == -1:
            # rest_world = mathutils.Matrix(skm_data.bone_data[0].world_inverse_matrix) @ rest_world
            # rest_world = mathutils.Matrix(skm_data.bone_data[0].world_inverse_matrix)
            pass
        elif ska_bone.parent_id != -1:
            rest_world = mathutils.Matrix(skm_data.bone_data[skm_bone.parent_id].world_inverse_matrix) @ rest_world
        rest_loc, rest_rot, rest_sca = rest_world.decompose()
        bone_rest_state[ska_bone_id] = RestBoneState(rest_loc, rest_rot, rest_sca)

    # Metadata for SKA export (export_ska.py): the full SKA skeleton table (incl. bones missing
    # from the SKM), and per bone the exact rest state used to convert keys to pose space.
    import json
    rig["toee_ska_bones"] = json.dumps([dict(name=str(b.name), parent=b.parent_id, flags=b.flags,
                                              scale=list(b.scale), rotation=list(b.rotation),
                                              translation=list(b.translation)) for b in ska_data.bone_data])
    for ska_bone_id, skm_bone_id in ska_to_skm_bone_mapping.items():
        if skm_bone_id < 0 or ska_bone_id not in bone_rest_state:
            continue
        rs = bone_rest_state[ska_bone_id]
        bb = barm.bones.get(str(skm_data.bone_data[skm_bone_id].name))
        if bb is not None:
            bb["toee_ska_index"] = ska_bone_id
            bb["toee_rest_loc"] = list(rs.loc)
            bb["toee_rest_rot"] = list(rs.rot)  # w, x, y, z

    anim_count = len(ska_data.animation_data)
    # anim_count = 10  # DEBUG (upstream limited import to 10 anims)
    # SKA keys are in engine frames; most anims play at 30 fps (turns/walks are rotation/distance driven)
    bpy.context.scene.render.fps = 30
    rig.animation_data_create()
    bpy.ops.object.mode_set(mode='POSE')
    # poselib.pose_add removed in Blender 3.0 (T Pose marker dropped)
    
    for ska_idx, ska_bd in enumerate(ska_data.bone_data):
        skm_bone_id = ska_to_skm_bone_mapping[ska_idx]
        if skm_bone_id == -1:
            print(f'SKA bone {ska_idx} not present in SKM')
            continue  # Skip bone not present in SKM

        posebone = rig.pose.bones[str(skm_data.bone_data[skm_bone_id].name)]

        rest_state = bone_rest_state[ska_idx]

        posebone.scale = mathutils.Vector(ska_bd.scale)
        rest_state.apply_to_posebone(posebone, loc=Vector(ska_bd.translation), rot=Quaternion(ska_bd.rotation_quaternion) )
    
    # poselib removed in Blender 3.0 (Rest Pose marker dropped)
    
    progress.enter_substeps(anim_count, "Generating animation F-Curves (%d)..." % anim_count)
    for i in range(0, anim_count):
        progress.step()
        ad = ska_data.animation_data[i]
        anim_header = ad.header
        action_name = str(anim_header.name)
        print(action_name)
        action = bpy.data.actions.new(action_name)
        action.use_fake_user = True
        # Header data for SKA export
        action["toee_index"] = i
        action["toee_drive_type"] = anim_header.drive_type
        action["toee_loopable"] = anim_header.loopable
        if anim_header.stream_headers:
            _sh = anim_header.stream_headers[0]
            action["toee_frame_count"] = _sh.frame_count
            action["toee_variation_id"] = _sh.variation_id
            action["toee_frame_rate"] = _sh.frame_rate
            action["toee_dps"] = _sh.dps
        ska_events.store_events(action, ad.events)  # pose markers + exact copy in "toee_events"
        writer = anim_compat.ActionWriter(action, rig)
        stream_count = anim_header.stream_count
        if stream_count <= 0:
            continue
        assert stream_count == 1, "TODO more than one stream (never happened as far as I've seen?)"

        # Group FCurves by the bone they affect
        curve_groups = dict()

        def get_curve_group(bone_idx):
            if bone_idx in curve_groups:
                return curve_groups[bone_idx].name
            bone_name = str(skm_data.bone_data[bone_idx].name)
            group = writer.group(bone_name)
            curve_groups[bone_idx] = group
            return group.name

        if not APPLY_ANIMATIONS:
            continue

        for j in range(0, stream_count):
            stream = ad.streams[j]  # type: SkaAnimStream

            # Scale keys: kept as pose-bone scale F-Curves (engine scale value) when they ever leave
            # unity, e.g. the human HandL_ref/HandR_ref scale animations, so SKA export keeps them.
            # Note: Blender's scale inheritance differs from the engine's parent-scale compensation.
            for bone_idx, keyframes in stream.scale_channels.items():
                if all(max(abs(c - 1.0) for c in sc) < 1e-4 for _, sc in keyframes):
                    continue
                skm_bone_idx = ska_to_skm_bone_mapping[bone_idx]
                if skm_bone_idx < 0:
                    continue
                posebone = rig.pose.bones[str(skm_data.bone_data[skm_bone_idx].name)]
                prop = posebone.path_from_id("scale")
                group = get_curve_group(skm_bone_idx)
                curves = [writer.fcurve(prop, k, group) for k in range(3)]
                for frame, scaling in keyframes:
                    for k in range(3):
                        curves[k].keyframe_points.insert(1 + frame, scaling[k], options={'FAST'}).interpolation = 'LINEAR'
                for c in curves:
                    c.update()

            # Bones the stream never keys keep the skeleton's initial state in the engine
            # (AnimPlayerStream::Initialize). Blender would instead keep a stale pose from the
            # previously evaluated action, so give them a constant key.
            for _bi, _bd in enumerate(ska_data.bone_data):
                stream.rotation_channels.setdefault(_bi, [(0, list(_bd.rotation_quaternion))])
                stream.location_channels.setdefault(_bi, [(0, list(_bd.translation))])
            raw_frames = stream.raw_frames
            
            for bone_idx, keyframes in stream.rotation_channels.items():
                skm_bone_idx = ska_to_skm_bone_mapping[bone_idx]
                if skm_bone_idx < 0:  # SKA-only bone (e.g. fire_Snake 'IK Chain01'): -1 would index the last SKM bone
                    continue
                skm_bone = skm_data.bone_data[skm_bone_idx]
                # print("Skm bone idx: %d" % skm_bone_idx)
                # rest_pose = bone_rest_state[skm_bone_idx]
                rest_pose = bone_rest_state[bone_idx]

                posebone = rig.pose.bones[str(skm_data.bone_data[skm_bone_idx].name)]
                prop = posebone.path_from_id("rotation_quaternion")
                group = get_curve_group(skm_bone_idx)
                curve_w = writer.fcurve(prop, 0, group)
                curve_x = writer.fcurve(prop, 1, group)
                curve_y = writer.fcurve(prop, 2, group)
                curve_z = writer.fcurve(prop, 3, group)
                prev_rot = None
                prev_frame = None
                for frame, rotation in keyframes:
                    # Transform rotation to be relative to rest pose
                    # if skm_bone.parent_id != -1:
                    raw_rot = Quaternion(rotation)  # engine space, as stored
                    rotation = rest_pose.get_rel_rot(raw_rot)
                    # Keep consecutive keys on the same hemisphere (engine slerp takes the shortest arc;
                    # flipping on w<0 made Blender's component-wise lerp swing through ~180 deg)
                    if prev_rot is not None and prev_rot.dot(rotation) < 0:
                        rotation = -rotation
                    # The engine slerps between keys; Blender lerps the components. For large
                    # spans (e.g. the ~170 deg root turn in *_rturn) add slerp-sampled keys at
                    # every integer frame so the curves follow the engine's great arc.
                    if prev_rot is not None and prev_frame is not None and frame - prev_frame > 1 \
                            and prev_rot.rotation_difference(rotation).angle > SLERP_BAKE_ANGLE:
                        for _f in range(prev_frame + 1, frame):
                            # the engine's slerp on the stored values decides the direction (matters when the
                            # keys are ~180 deg apart, e.g. firebat rturn 'Root')
                            _q = rest_pose.get_rel_rot(Quaternion(_q_slerp(tuple(prev_raw), tuple(raw_rot),
                                                                            (_f - prev_frame) / (frame - prev_frame))).normalized())
                            if _q.dot(prev_rot) < 0: _q = -_q
                            for _c, _v in ((curve_w, _q.w), (curve_x, _q.x), (curve_y, _q.y), (curve_z, _q.z)):
                                _c.keyframe_points.insert(1 + _f, _v, options={'FAST'}).interpolation = 'LINEAR'
                    prev_rot = rotation
                    prev_raw = raw_rot
                    prev_frame = frame

                    kf = curve_w.keyframe_points.insert(1 + frame, rotation.w, options={'FAST'})
                    kf.interpolation = 'LINEAR'
                    kf = curve_x.keyframe_points.insert(1 + frame, rotation.x, options={'FAST'})
                    kf.interpolation = 'LINEAR'
                    kf = curve_y.keyframe_points.insert(1 + frame, rotation.y, options={'FAST'})
                    kf.interpolation = 'LINEAR'
                    kf = curve_z.keyframe_points.insert(1 + frame, rotation.z, options={'FAST'})
                    kf.interpolation = 'LINEAR'

                curve_w.update()
                curve_x.update()
                curve_y.update()
                curve_z.update()

            for bone_idx, keyframes in stream.location_channels.items():
                skm_bone_idx = ska_to_skm_bone_mapping[bone_idx]
                if skm_bone_idx < 0:  # SKA-only bone (e.g. fire_Snake 'IK Chain01'): -1 would index the last SKM bone
                    continue
                skm_bone = skm_data.bone_data[skm_bone_idx]
                # rest_pose = bone_rest_state[skm_bone_idx]
                rest_pose = bone_rest_state[bone_idx]

                posebone = rig.pose.bones[str(skm_data.bone_data[skm_bone_idx].name)]
                prop = posebone.path_from_id("location")
                group = get_curve_group(skm_bone_idx)
                curve_x = writer.fcurve(prop, 0, group)
                curve_y = writer.fcurve(prop, 1, group)
                curve_z = writer.fcurve(prop, 2, group)
                for frame, location in keyframes:
                    # Transform location to be relative to rest pose
                    # if skm_bone.parent_id != -1:
                    location = Vector(location)
                    location = rest_pose.get_rel_loc(location)
                    
                    kf = curve_x.keyframe_points.insert(1 + frame, location.x, options={'FAST'})
                    kf.interpolation = 'LINEAR'
                    kf = curve_y.keyframe_points.insert(1 + frame, location.y, options={'FAST'})
                    kf.interpolation = 'LINEAR'
                    kf = curve_z.keyframe_points.insert(1 + frame, location.z, options={'FAST'})
                    kf.interpolation = 'LINEAR'

                curve_x.update()
                curve_y.update()
                curve_z.update()
    progress.leave_substeps("Finished")
    return

# ToEE model space: +Y up, model faces +Z, character's left at +X, right-handed, 1 unit ~ 1 inch
# (PC_Human_Male is 71.8 units tall). Blender: +Z up, front faces -Y. The mapping is a pure
# rotation of +90 deg about X (ToEE (x,y,z) -> Blender (x,-z,y), det +1, no mirroring) plus a
# uniform scale. It is applied as the rig object's transform only: mesh, bones, rest poses,
# bone rolls and keys stay in ToEE model space inside the rig, so the exporter (which works in
# rig-local space) round-trips bit-for-bit regardless of this setting.
TOEE_UNIT_METERS = 0.0254


def toee_to_blender_matrix(scale=TOEE_UNIT_METERS):
    return mathutils.Matrix.Rotation(math.radians(90.0), 4, 'X') @ mathutils.Matrix.Scale(scale, 4)


def apply_axis_conversion(rig, scale=TOEE_UNIT_METERS):
    rig.matrix_world = toee_to_blender_matrix(scale)
    rig["toee_axis_conversion"] = scale


def _new_rig(before):
    new = [o for o in bpy.data.objects if o.name not in before and o.type == 'ARMATURE']
    return new[-1] if new else None


def get_ToEE_data_dir(filepath):
    '''
    Gets the ToEE data dir, assuming filepath is of the form
    <ToEE data dir>\\art\\etc
    '''
    import re
    data_dir = os.path.abspath(filepath)
    data_dir = os.path.dirname(data_dir)
    data_dir = data_dir.replace("\\", "/")
    data_dir = re.split("/art", data_dir, flags=re.IGNORECASE)[0]
    return data_dir


def get_skm_filepath(ska_filepath):
    import re
    base = re.split(r"\.ska$", ska_filepath, flags=re.IGNORECASE)[0]
    for ext in ('.SKM', '.skm', '.Skm'):
        if os.path.exists(base + ext):
            return base + ext
    d, stem = os.path.split(base)  # case-insensitive file systems aside: demon.SKM next to Demon.SKA
    try:
        hit = next((n for n in os.listdir(d or '.') if n.lower() == stem.lower() + '.skm'), None)
    except OSError:
        hit = None
    return os.path.join(d, hit) if hit else base + '.SKM'


def load_skm(filepath, context, IMAGE_SEARCH=True):
    global SCN, ToEE_data_dir, progress
    time1 = time.perf_counter()  # for timing the import duration
    with ProgressReport(context.window_manager) as progress:

        print("importing SKA: %r..." % (filepath), end="")
        # filepath = 'D:/GOG Games/ToEECo8/data/art/meshes/Monsters/Giants/Hill_Giants/Hill_Giant_2/Zomb_giant_2.SKA'
        skm_filepath = filepath

        if bpy.ops.object.select_all.poll():
            bpy.ops.object.select_all(action='DESELECT')

        ToEE_data_dir = get_ToEE_data_dir(filepath)
        print("Data dir: %s", ToEE_data_dir)

        # Read data into intermediate SkmFile and SkaFile objects
        skm_data = SkmFile()

        # SKM file
        progress.enter_substeps(1, "Reading SKM File %r..." %skm_filepath)
        with open(skm_filepath, 'rb') as file:
            print('Opened file: ', skm_filepath)
            skm_data.read(file)

        # fixme, make unglobal, clear in case
        object_dictionary.clear()
        object_matrix.clear()

        scn = context.scene
        SCN = scn
        
        importedObjects = []  # Fill this list with objects
        progress.enter_substeps(3, "Converting SKM to Blender model...")
        skm_to_blender(skm_data, importedObjects, IMAGE_SEARCH)
        progress.leave_substeps("Finished SKM conversion.")
        progress.step()
        
        # In Blender 2.80 API new objects mast be linked not to the scene, but to the scene collections:
        view_layer = context.view_layer
        view_layer.update()

        for ob in importedObjects:
            ob.select_set(True)
        
        # fixme, make unglobal
        object_dictionary.clear()
        object_matrix.clear()
        
    print(" done in %.4f sec." % (time.perf_counter() - time1))
    return


def load_ska_and_skm(filepath, context, IMPORT_CONSTRAIN_BOUNDS=10.0,
             IMAGE_SEARCH=True,
             APPLY_MATRIX=True,
             USE_INHERIT_ROTATION=True,
             USE_LOCAL_LOCATION=True,
             APPLY_ANIMATIONS=False,
             global_matrix=None):
    global SCN, ToEE_data_dir, progress

    # XXX
    # 	if BPyMessages.Error_NoFile(filepath):
    # 		return
    time1 = time.perf_counter()  # for timing the import duration
    # progress = ProgressReport(context.window_manager)
    with ProgressReport(context.window_manager) as progress:
        

        print("importing SKA: %r..." % (filepath), end="")
        # filepath = 'D:/GOG Games/ToEECo8/data/art/meshes/Monsters/Giants/Hill_Giants/Hill_Giant_2/Zomb_giant_2.SKA'
        ska_filepath = filepath
        skm_filepath = get_skm_filepath(ska_filepath)

        if bpy.ops.object.select_all.poll():
            bpy.ops.object.select_all(action='DESELECT')

        ToEE_data_dir = get_ToEE_data_dir(filepath)
        print("Data dir: %s", ToEE_data_dir)

        # Read data into intermediate SkmFile and SkaFile objects
        skm_data = SkmFile()
        ska_data = SkaFile()
        progress.enter_substeps(5, "Reading SKM & SKA Files %r..." %skm_filepath)

        # SKM file
        print("Reading SKM data")
        progress.step()
        with open(skm_filepath, 'rb') as file:
            print('Opened file: ', skm_filepath)
            skm_data.read(file)


        # SKA file
        
        print("Reading SKA File %r..." % ska_filepath)
        progress.step()
        with open(ska_filepath, 'rb') as file:
            print('Opened file: ', ska_filepath)
            if APPLY_ANIMATIONS:
                ska_data.read(file)

        # fixme, make unglobal, clear in case
        object_dictionary.clear()
        object_matrix.clear()

        scn = context.scene
        # 	scn = bpy.data.scenes.active
        SCN = scn
        # SCN_OBJECTS = scn.objects
        # SCN_OBJECTS.selected = [] # de select all

        importedObjects = []  # Fill this list with objects
        progress.enter_substeps(3, "Converting SKM to Blender model...")
        # The engine animates the SKA skeleton: a bone's keyframes are local to its SKA parent
        # (aas_animated_model.cpp: W_i = W_parent(ska) * T * S_p^-1 * R * S). Some models have a
        # different SKM hierarchy (e.g. Ice Lizard thighs/tail: SKM parent Pelvis, SKA parent Spine),
        # so build the rig with the SKA parents and keep the SKM parent for reference/export.
        if APPLY_ANIMATIONS and ska_data.bone_data:
            _skm_idx = {str(b.name).lower(): i for i, b in enumerate(skm_data.bone_data)}
            for _b in skm_data.bone_data:
                _b.skm_parent_id = _b.parent_id
                _sb = next((x for x in ska_data.bone_data if str(x.name).lower() == str(_b.name).lower()), None)
                if _sb is not None and _sb.parent_id >= 0:
                    _pn = str(ska_data.bone_data[_sb.parent_id].name).lower()
                    if _pn in _skm_idx and _skm_idx[_pn] != _b.parent_id:
                        print('Reparenting %s: SKM parent %d -> SKA parent %d' % (_b.name, _b.parent_id, _skm_idx[_pn]))
                        _b.parent_id = _skm_idx[_pn]
        skm_to_blender(skm_data, importedObjects, IMAGE_SEARCH)
        
        # In Blender 2.80 API new objects mast be linked not to the scene, but to the scene collections:
        view_layer = context.view_layer
        view_layer.update()

        # print(importedObjects)
        if global_matrix:
            print(global_matrix)
            for ob in importedObjects:
                if True: # ob.parent is None:
                    ob.matrix_world = global_matrix
                else:
                    ob.parent.matrix_world = ob.parent.matrix_world @ global_matrix 

        # if True:
        #     for ob in importedObjects:
        #         if ob.type == 'MESH':
        #             me = ob.data
        #             me.transform(ob.matrix_local.inverted())

        for ob in importedObjects:
            ob.select_set(True)

        progress.enter_substeps(1, "Converting SKA to Blender animations...")
        if APPLY_ANIMATIONS:
            ska_to_blender(ska_data, skm_data, importedObjects, USE_INHERIT_ROTATION, USE_LOCAL_LOCATION,
                        APPLY_ANIMATIONS)
        
        # fixme, make unglobal
        object_dictionary.clear()
        object_matrix.clear()
        
        view_layer = context.view_layer
        view_layer.update()
        
    # Select all new objects.
    print(" done in %.4f sec." % (time.perf_counter() - time1))


def blender_load_ska(operator, context, filepath="",
         constrain_size=0.0,
         use_image_search=True,
         use_apply_transform=True,
         use_inherit_rot=True,
         use_local_location=True,
         apply_animations=True,
         global_matrix=None,
         toee_axis_conversion=True,
         toee_scale=TOEE_UNIT_METERS,
         ):
    _before = set(o.name for o in bpy.data.objects)
    load_ska_and_skm(filepath, context, IMPORT_CONSTRAIN_BOUNDS=constrain_size,
             IMAGE_SEARCH=use_image_search,
             APPLY_MATRIX=use_apply_transform,
             USE_INHERIT_ROTATION=use_inherit_rot,
             USE_LOCAL_LOCATION=use_local_location,
             APPLY_ANIMATIONS=apply_animations,
             global_matrix=global_matrix,
             )
    _rig = _new_rig(_before)
    if toee_axis_conversion and _rig is not None:
        apply_axis_conversion(_rig, toee_scale)
    return {'FINISHED'}

def blender_load_skm(operator, context, filepath="",
         constrain_size=0.0,
         use_image_search=True,
         use_apply_transform=True,
         use_inherit_rot=True,
         use_local_location=True,
         apply_animations=True,
         global_matrix=None,
         toee_axis_conversion=True,
         toee_scale=TOEE_UNIT_METERS,
         ):
    _before = set(o.name for o in bpy.data.objects)
    load_skm(filepath, context, IMAGE_SEARCH=use_image_search)
    _rig = _new_rig(_before)
    if toee_axis_conversion and _rig is not None:
        apply_axis_conversion(_rig, toee_scale)
    return {'FINISHED'}
