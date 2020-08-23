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

addon_idname = __package__

# -----------------------------------------------------------------------------

def getPreferences(context):
    preferences = context.preferences
    addon_preferences = preferences.addons[addon_idname].preferences
    return addon_preferences

# -----------------------------------------------------------------------------

class MapsModelsAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = addon_idname

    tmp_dir: bpy.props.StringProperty(
        name="Temporary Directory",
        subtype='DIR_PATH',
        default="",
        )

    debug_info: bpy.props.BoolProperty(
        name="Debug Info",
        default=False,
        )

    def draw(self, context):
        layout = self.layout
        layout.label(text="The temporary directory is used for intermediate files and for textures.")
        layout.label(text="It can get heavy. If left empty, the capture file's directory is used.")
        layout.prop(self, "tmp_dir")
        layout.label(text="Turn on extra debug info:")
        layout.prop(self, "debug_info")

# -----------------------------------------------------------------------------

classes = (MapsModelsAddonPreferences,)

register, unregister = bpy.utils.register_classes_factory(classes)
