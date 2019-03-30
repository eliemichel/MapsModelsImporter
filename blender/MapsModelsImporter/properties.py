import bpy
from bpy.props import BoolProperty, FloatVectorProperty

def register():
    bpy.types.Scene.maps_models_importer_is_ref_matrix_valid = BoolProperty(
        name="Is Reference Matrix Valid",
        description="Before loading any capture, it is not valid and will be overwritten",
        default=False,
    )

    bpy.types.Scene.maps_models_importer_ref_matrix = FloatVectorProperty(
        name="Reference Matrix",
        description="Matrix used for alignment of many captures",
        size=16,
        default=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
    )

def unregister():
    del bpy.types.Scene.maps_models_importer_ref_matrix

