
# if "bpy" in locals():
#     import importlib
#     if "export_ska" in locals():
#         importlib.reload(export_ska)

import bpy
from bpy.props import (
        BoolProperty,
        FloatProperty,
        StringProperty,
        EnumProperty,
        )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        orientation_helper,
        axis_conversion,
        )


@orientation_helper(axis_forward='Y', axis_up='Z')
class SkaExport(bpy.types.Operator, ExportHelper):
    """Export animation to ToEE's SKA (Skeletal Animation) format"""
    bl_idname = "export.ska_file"
    bl_label = "Export SKA Data"

    filename_ext = ".ska"
    filter_glob: StringProperty(
            default="*.ska",
            options={'HIDDEN'},
            )
            
    use_selection: BoolProperty(
            name="Selection Only",
            description="Export selected objects only",
            default=False,
            )
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    write_skm: BoolProperty(
            name="Also write SKM",
            description="Write the mesh (.skm) next to the .ska (see SKM export caveats)",
            default=False,
            )
    toee_axis_conversion: BoolProperty(
            name="Blender -> ToEE axes",
            description="Undo the importer's ToEE->Blender root transform (the rig object transform "
                        "is dropped; data is written in rig-local ToEE space)",
            default=True,
            )
    auto_fix: BoolProperty(
            name="Auto-fix (temporary copy)",
            description="Triangulate non-triangle faces and limit weights to 6 per vertex (dropping zero weights, "
                        "renormalizing) in a temporary copy; the scene's mesh is never modified",
            default=True,
            )
    only_active_action: BoolProperty(
            name="Active action only",
            description="Export only the rig's active action instead of all ToEE actions",
            default=False,
            )

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
    
        from . import export_ska
        
        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "filter_glob",
                                            "check_existing",
                                            ))
        global_matrix = axis_conversion(to_forward=self.axis_forward,
                                        to_up=self.axis_up,
                                        ).to_4x4()
        keywords["global_matrix"] = global_matrix

        return export_ska.save(self, context, **keywords)
        
        #file = open(self.filepath, 'w')
        #file.write("Hello World " + context.object.name)
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

@orientation_helper(axis_forward='Y', axis_up='Z')
class SkmExport(bpy.types.Operator, ExportHelper):
    """Export animation to ToEE's SKM (Skeletal Model) format"""
    bl_idname = "export.skm_file"
    bl_label = "Export SKM Data"

    filename_ext = ".skm"
    filter_glob: StringProperty(
            default="*.skm",
            options={'HIDDEN'},
            )
            
    use_selection: BoolProperty(
            name="Selection Only",
            description="Export selected objects only",
            default=False,
            )
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    auto_fix: BoolProperty(
            name="Auto-fix (temporary copy)",
            description="Triangulate non-triangle faces and limit weights to 6 per vertex (dropping zero weights, "
                        "renormalizing) in a temporary copy; the scene's mesh is never modified",
            default=True,
            )

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
    
        from . import export_ska
        
        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "filter_glob",
                                            "check_existing",
                                            ))
        global_matrix = axis_conversion(to_forward=self.axis_forward,
                                        to_up=self.axis_up,
                                        ).to_4x4()
        keywords["global_matrix"] = global_matrix

        return export_ska.blender_save_skm(self, context, **keywords)

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}



def menu_func_export_ska(self, context):
    self.layout.operator(SkaExport.bl_idname, text="ToEE animation (.SKA + .SKM)")

def menu_func_export_skm(self, context):
    self.layout.operator(SkmExport.bl_idname, text="ToEE model (.SKM)")


def register():
    # print('Registering GITHUB/SKA_Import/export_op.py')
    # Register and add to the file selector
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export_ska)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export_skm)



def unregister():
    # print('Unregistering GITHUB/SKA_Import/export_op.py!')
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_ska)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_skm)
