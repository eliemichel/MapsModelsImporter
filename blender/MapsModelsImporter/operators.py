# Copyright (c) 2019 Elie Michel
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the “Software”), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# The Software is provided “as is”, without warranty of any kind, express or
# implied, including but not limited to the warranties of merchantability,
# fitness for a particular purpose and noninfringement. In no event shall
# the authors or copyright holders be liable for any claim, damages or other
# liability, whether in an action of contract, tort or otherwise, arising from,
# out of or in connection with the software or the use or other dealings in the
# Software.
#
# This file is part of MapsModelsImporter, a set of addons to import 3D models
# from Maps services

import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, IntProperty
from bpy.types import Operator

from .google_maps import importCapture, MapsModelsImportError
from .preferences import getPreferences

class IMP_OP_GoogleMapsCapture(Operator, ImportHelper):
    """Import a capture of a Google Maps frame recorded with RenderDoc"""
    bl_idname = "import_rdc.google_maps"
    bl_label = "Import Google Maps Capture"

    filename_ext = ".rdc"

    filter_glob: StringProperty(
        default="*.rdc",
        options={'HIDDEN'},
        maxlen=1024,  # Max internal buffer length, longer would be clamped.
    )

    max_blocks: IntProperty(
        name="Max Blocks",
        description="Maximum number of draw calls to load",
        default=-1,
    )

    def execute(self, context):
        pref = getPreferences(context)
        try:
            importCapture(context, self.filepath, self.max_blocks, pref)
            error = None
        except MapsModelsImportError as err:
            error = err.args[0]
        if error is not None:
            self.report({'ERROR'}, error)
        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(IMP_OP_GoogleMapsCapture.bl_idname, text="Google Maps Capture (.rdc)")


def register():
    bpy.utils.register_class(IMP_OP_GoogleMapsCapture)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(IMP_OP_GoogleMapsCapture)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
