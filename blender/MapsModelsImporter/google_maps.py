# Copyright (c) 2019-2020 Elie Michel
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

import sys
import os
import subprocess

from .utils import getBinaryDir, makeTmpDir

SCRIPT_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "google_maps_rd.py")

def captureToFiles(filepath, prefix, max_blocks):
    """Extract binary files and textures from a RenderDoc capture file.
    This spawns a standalone Python interpreter because renderdoc module cannot be loaded in embedded Python"""
    blender_dir = os.path.dirname(sys.executable)
    blender_version = ("{0}.{1}").format(*bpy.app.version)
    python_home = os.path.join(blender_dir, blender_version, "python")
    os.environ["PYTHONHOME"] = python_home
    os.environ["PYTHONPATH"] = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] += os.pathsep + os.path.abspath(getBinaryDir())
    python = os.path.join(python_home, "bin", "python.exe" if sys.platform == "win32" else "python3.7m") # warning: hardcoded python version for non-windows might fail with Blender update
    subprocess.run([python, SCRIPT_PATH, filepath, prefix, str(max_blocks)])

# -----------------------------------------------------------------------------

import bpy
import bmesh
import pickle
from bpy_extras import object_utils
from math import floor, pi
from mathutils import Matrix
import os

def extractUniforms(constants, refMatrix):
    """Extract from constant buffer the model matrix and uv offset
    The reference matrix is used to cancel the view part of teh modelview matrix
    """

    # Extract constants, which have different names depending on the browser/GPU driver
    globUniforms = constants['$Globals']
    if '_w' in globUniforms and '_s' in globUniforms:
        [ou, ov, su, sv] = globUniforms['_w']
        ov -= 1.0 / sv
        sv = -sv
        uvOffsetScale = [ou, ov, su, sv]
        mdata = globUniforms['_s']
    elif 'webgl_fa7f624db8ab37d1' in globUniforms and 'webgl_3c7b7f37a9bd4c1d' in globUniforms:
        uvOffsetScale = globUniforms['webgl_fa7f624db8ab37d1']
        mdata = globUniforms['webgl_3c7b7f37a9bd4c1d']
    elif '_webgl_fa7f624db8ab37d1' in globUniforms and '_webgl_3c7b7f37a9bd4c1d' in globUniforms:
        [ou, ov, su, sv] = globUniforms['_webgl_fa7f624db8ab37d1']
        ov -= 1.0 / sv
        sv = -sv
        uvOffsetScale = [ou, ov, su, sv]
        mdata = globUniforms['_webgl_3c7b7f37a9bd4c1d']
    else:
        print("globUniforms:")
        for k, v in globUniforms.items():
            print("  {}: {}".format(k, v))
        print("Capture file not supported. Please report to MapsModelsImporter developers providing the previous log line as well as the .rdc file.")
    
    matrix = Matrix([
        mdata[0:4],
        mdata[4:8],
        mdata[8:12],
        mdata[12:16]
    ]).transposed()

    if refMatrix is None:
        # Rotate around Y because Google Maps uses X as up axis
        refMatrix = Matrix.Rotation(-pi/2, 4, 'Y') @ matrix.inverted()
    matrix = refMatrix @ matrix

    return uvOffsetScale, matrix, refMatrix

def addMesh(context, name, verts, tris, uvs):
    mesh = bpy.data.meshes.new(name)

    mesh.from_pydata(verts, [], tris)
    mesh.update()

    bm = bmesh.new()
    bm.from_mesh(mesh)
    uv_layer = bm.loops.layers.uv.verify()
    for f in bm.faces:
        for l in f.loops:
            luv = l[uv_layer]
            luv.uv = tuple(uvs[l.vert.index])
    bm.to_mesh(mesh)

    obj = object_utils.object_data_add(context, mesh, operator=None)
    return obj

def addImageMaterial(name, obj, img):
    bpy.ops.material.new()
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    obj.data.materials.append(mat)
    nodes = mat.node_tree.nodes
    principled = nodes["Principled BSDF"]
    principled.inputs["Specular"].default_value = 0.0
    principled.inputs["Roughness"].default_value = 1.0
    texture_node = nodes.new(type="ShaderNodeTexImage")
    texture_node.image = img
    links = mat.node_tree.links
    link = links.new(texture_node.outputs[0], principled.inputs[0])

def loadData(prefix, drawcallId):
    with open("{}{:05d}-indices.bin".format(prefix, drawcallId), 'rb') as file:
        indices = pickle.load(file)

    with open("{}{:05d}-positions.bin".format(prefix, drawcallId), 'rb') as file:
        positions = pickle.load(file)

    with open("{}{:05d}-uv.bin".format(prefix, drawcallId), 'rb') as file:
        uvs = pickle.load(file)

    img = bpy.data.images.load("{}{:05d}-texture.png".format(prefix, drawcallId))

    with open("{}{:05d}-constants.bin".format(prefix, drawcallId), 'rb') as file:
        constants = pickle.load(file)

    return indices, positions, uvs, img, constants

# -----------------------------------------------------------------------------

def filesToBlender(context, prefix, max_blocks=200, globalScale=1.0/256.0):
    """Import data from the files extracted by captureToFiles"""
    # Get reference matrix
    refMatrix = None
    if context.scene.maps_models_importer_is_ref_matrix_valid:
        values = context.scene.maps_models_importer_ref_matrix
        refMatrix = Matrix((values[0:4], values[4:8], values[8:12], values[12:16]))

    if max_blocks <= 0:
        # If no specific bound, max block is the number of .bin files in the directory
        max_blocks = len([file for file in os.listdir(os.path.dirname(prefix)) if file.endswith(".bin")])

    drawcallId = 0
    while drawcallId < max_blocks:
        if not os.path.isfile("{}{:05d}-indices.bin".format(prefix, drawcallId)):
            drawcallId += 1
            continue

        try:
            indices, positions, uvs, img, constants = loadData(prefix, drawcallId)
        except FileNotFoundError as err:
            print("Skipping ({})".format(err))
            drawcallId += 1
            continue

        uvOffsetScale, matrix, refMatrix = extractUniforms(constants, refMatrix)

        # Make triangles from triangle strip index buffer
        n = len(indices)
        tris = [ [ indices[i+j] for j in [[0,1,2],[0,2,1]][i%2] ] for i in range(n - 3)]
        tris = [ t for t in tris if t[0] != t[1] and t[0] != t[2] and t[1] != t[2] ]
        verts = [ [ p[0] * 256.0, p[1] * 256.0, p[2] * 256.0 ] for p in positions ]

        [ou, ov, su, sv] = uvOffsetScale
        uvs = [ [ (floor(u * 65535.0 + 0.5) + ou) * su, (floor(v * 65535.0 + 0.5) + ov) * sv ] for u, v in uvs ]

        if len(indices) == 0:
            continue

        mesh_name = "BuildingMesh-{:05d}".format(drawcallId)
        obj = addMesh(context, mesh_name, verts, tris, uvs)
        obj.matrix_world = matrix * globalScale

        mat_name = "BuildingMat-{:05d}".format(drawcallId)
        addImageMaterial(mat_name, obj, img)

        drawcallId += 1

    # Save reference matrix
    if refMatrix:
        values = sum([list(v) for v in refMatrix], [])
        context.scene.maps_models_importer_ref_matrix = values
        context.scene.maps_models_importer_is_ref_matrix_valid = True

# -----------------------------------------------------------------------------

def importCapture(context, filepath, max_blocks, pref):
    prefix = makeTmpDir(pref, filepath)
    captureToFiles(filepath, prefix, max_blocks)
    filesToBlender(context, prefix, max_blocks)
