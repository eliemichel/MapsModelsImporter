import bpy

class SCN_PT_maps_models_importer(bpy.types.Panel):
    """Panel showing information about the Maps Models Importer context"""
    bl_label = "Maps Models Context"
    bl_idname = "SCN_PT_maps_models_importer"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(context.scene, "maps_models_importer_is_ref_matrix_valid")
        row = layout.row()
        row.prop(context.scene, "maps_models_importer_ref_matrix")

def register():
    bpy.utils.register_class(SCN_PT_maps_models_importer)

def unregister():
    bpy.utils.unregister_class(SCN_PT_maps_models_importer)

