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

import sys
import os
import subprocess

from .utils import getBinaryDir, makeTmpDir
from .preferences import getPreferences

SCRIPT_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "google_maps_rd.py")
MSG_INCORRECT_RDC = """Invalid RDC capture file. Please make sure that:
1. You are importing from Google Maps (NOT Google Earth)
2. You were MOVING in the 3D view while taking the capture (you can use the Capture after delay button in RenderDoc).
Please report to MapsModelsImporter developers providing the .rdc file as well as the full console log.
Console log is accessible in Windows > Toggle System Console (right click to copy)."""

class MapsModelsImportError(Exception):
    pass

def captureToFiles(context, filepath, prefix, max_blocks):
    """Extract binary files and textures from a RenderDoc capture file.
    This spawns a standalone Python interpreter because renderdoc module cannot be loaded in embedded Python"""
    pref = getPreferences(context)
    blender_dir = os.path.dirname(sys.executable)
    blender_version = ("{0}.{1}").format(*bpy.app.version)
    python_home = os.path.join(blender_dir, blender_version, "python")
    os.environ["PYTHONHOME"] = python_home
    os.environ["PYTHONPATH"] = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] += os.pathsep + os.path.abspath(getBinaryDir())
    python = os.path.join(python_home, "bin", "python.exe" if sys.platform == "win32" else "python3.7m") # warning: hardcoded python version for non-windows might fail with Blender update
    try:
        out = subprocess.check_output([python, SCRIPT_PATH, filepath, prefix, str(max_blocks)], stderr=subprocess.STDOUT)
        if pref.debug_info:
            print("google_maps_rd returned:")
            print(out.decode())
        success = True
    except subprocess.CalledProcessError as err:
        if pref.debug_info:
            print("google_maps_rd failed and returned:")
            print(err.output.decode())
        success = False
    if not success:
        raise MapsModelsImportError(MSG_INCORRECT_RDC)

# -----------------------------------------------------------------------------

import bpy
import bmesh
import pickle
from bpy_extras import object_utils
from math import floor, pi
from mathutils import Matrix, Vector
import os

def makeMatrix(mdata):
    return Matrix([
        mdata[0:4],
        mdata[4:8],
        mdata[8:12],
        mdata[12:16]
    ]).transposed()

def extractUniforms(constants, refMatrix):
    """Extract from constant buffer the model matrix and uv offset
    The reference matrix is used to cancel the view part of teh modelview matrix
    """

    # Extract constants, which have different names depending on the browser/GPU driver
    globUniforms = constants['$Globals']
    postMatrix = None
    if '_w' in globUniforms and '_s' in globUniforms:
        [ou, ov, su, sv] = globUniforms['_w']
        ov -= 1.0 / sv
        sv = -sv
        uvOffsetScale = [ou, ov, su, sv]
        matrix = makeMatrix(globUniforms['_s'])
    elif 'webgl_fa7f624db8ab37d1' in globUniforms and 'webgl_3c7b7f37a9bd4c1d' in globUniforms:
        uvOffsetScale = globUniforms['webgl_fa7f624db8ab37d1']
        matrix = makeMatrix(globUniforms['webgl_3c7b7f37a9bd4c1d'])
    elif '_webgl_fa7f624db8ab37d1' in globUniforms and '_webgl_3c7b7f37a9bd4c1d' in globUniforms:
        [ou, ov, su, sv] = globUniforms['_webgl_fa7f624db8ab37d1']
        ov -= 1.0 / sv
        sv = -sv
        uvOffsetScale = [ou, ov, su, sv]
        matrix = makeMatrix(globUniforms['_webgl_3c7b7f37a9bd4c1d'])
    elif '_uMeshToWorldMatrix' in globUniforms:
        # Google Earth
        uvOffsetScale = [0, -1, 1, -1]
        matrix = makeMatrix(globUniforms['_uMeshToWorldMatrix'])
        matrix[3] = [0, 0, 0, 1]
        #matrix = makeMatrix(globUniforms['_uModelviewMatrix']) @ matrix
    elif '_uMV' in globUniforms:
        # Mapy CZ
        uvOffsetScale = [0, -1, 1, -1]
        matrix = makeMatrix(globUniforms['_uMV'])
        postMatrix = Matrix(
            ((0.682889997959137, 0.20221230387687683, 0.7019768357276917, -0.06431722640991211),
            (0.07228320091962814, 0.9375065565109253, -0.3403771221637726, -0.11041564494371414),
            (-0.7269363403320312, 0.28318125009536743, 0.6255972981452942, -1.349690556526184),
            (0.0, 0.0, 0.0, 1.0))
            ) @ Matrix.Scale(500, 4)
    elif '_f' in globUniforms or '_i' in globUniforms:
        # Google Chrome 85.0.4183.121 (64bit), RendorDoc 1.9, RTX 3090, https://smap.seoul.go.kr/
        uvOffsetScale = [0, 0, 1/65535., 1/65535.]
        matrix = makeMatrix(globUniforms['_f'])
        postMatrix = Matrix.Scale(3, 4, Vector((1.0, 0., 0.)))
    else:
        if refMatrix is None:
            print("globUniforms:")
            for k, v in globUniforms.items():
                print("  {}: {}".format(k, v))
            raise MapsModelsImportError(MSG_INCORRECT_RDC)
        else:
            return None, None, None
    
    if refMatrix is None:
        if '_f' in globUniforms or '_i' in globUniforms:
            # Rotate around Z, upside down for SMAP
            refMatrix = Matrix.Rotation(-pi, 4, 'Z') @ matrix.inverted()
        else:
            # Rotate around Y because Google Maps uses X as up axis
            refMatrix = Matrix.Rotation(-pi/2, 4, 'Y') @ matrix.inverted()
    matrix = refMatrix @ matrix

    if postMatrix is not None:
        matrix = postMatrix @ matrix

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

def loadData(prefix, drawcall_id):
    with open("{}{:05d}-indices.bin".format(prefix, drawcall_id), 'rb') as file:
        indices = pickle.load(file)

    with open("{}{:05d}-positions.bin".format(prefix, drawcall_id), 'rb') as file:
        positions = pickle.load(file)

    with open("{}{:05d}-uv.bin".format(prefix, drawcall_id), 'rb') as file:
        uvs = pickle.load(file)

    img = bpy.data.images.load("{}{:05d}-texture.png".format(prefix, drawcall_id))

    with open("{}{:05d}-constants.bin".format(prefix, drawcall_id), 'rb') as file:
        constants = pickle.load(file)

    return indices, positions, uvs, img, constants

# -----------------------------------------------------------------------------

def filesToBlender(context, prefix, max_blocks=200):
    """Import data from the files extracted by captureToFiles"""
    # Get reference matrix
    refMatrix = None
    
    if max_blocks <= 0:
        # If no specific bound, max block is the number of .bin files in the directory
        max_blocks = len([file for file in os.listdir(os.path.dirname(prefix)) if file.endswith(".bin")])

    drawcall_id = 0
    while drawcall_id < max_blocks:
        if not os.path.isfile("{}{:05d}-indices.bin".format(prefix, drawcall_id)):
            drawcall_id += 1
            continue

        try:
            indices, positions, uvs, img, constants = loadData(prefix, drawcall_id)
        except FileNotFoundError as err:
            print("Skipping ({})".format(err))
            drawcall_id += 1
            continue

        uvOffsetScale, matrix, refMatrix = extractUniforms(constants, refMatrix)
        if uvOffsetScale is None:
            drawcall_id += 1
            continue
        
        # Make triangles from triangle strip index buffer
        n = len(indices)
        if constants["DrawCall"]["topology"] == 'TRIANGLE_STRIP':
            tris = [ [ indices[i+j] for j in [[0,1,2],[0,2,1]][i%2] ] for i in range(n - 3)]
            tris = [ t for t in tris if t[0] != t[1] and t[0] != t[2] and t[1] != t[2] ]
        else:
            tris = [ [ indices[3*i+j] for j in range(3) ] for i in range(n//3) ]

        if constants["DrawCall"]["type"] == 'Google Maps':
            verts = [ [ p[0] * 256.0, p[1] * 256.0, p[2] * 256.0 ] for p in positions ]
        else:
            verts = [ [ p[0], p[1], p[2] ] for p in positions ]

        [ou, ov, su, sv] = uvOffsetScale
        if uvs and len(uvs[0]) > 2:
            print(f"uvs[0][2] = {uvs[0][2]}")
            uvs = [u[:2] for u in uvs]

        if constants["DrawCall"]["type"] == 'Google Maps':
            uvs = [ [ (floor(u * 65535.0 + 0.5) + ou) * su, (floor(v * 65535.0 + 0.5) + ov) * sv ] for u, v in uvs ]
        else:
            uvs = [ [ (u + ou) * su, (v + ov) * sv ] for u, v in uvs ]

        if len(indices) == 0:
            continue

        mesh_name = "BuildingMesh-{:05d}".format(drawcall_id)
        obj = addMesh(context, mesh_name, verts, tris, uvs)
        globalScale=1.0/256.0
        if constants["DrawCall"]["type"] == 'SeoulMap':
            globalScale=1.0
        obj.matrix_world = matrix * globalScale

        mat_name = "BuildingMat-{:05d}".format(drawcall_id)
        addImageMaterial(mat_name, obj, img)

        drawcall_id += 1

    # Save reference matrix
    if refMatrix:
        values = sum([list(v) for v in refMatrix], [])
        context.scene.maps_models_importer_ref_matrix = values
        context.scene.maps_models_importer_is_ref_matrix_valid = True

    return None # no error

# -----------------------------------------------------------------------------

def importCapture(context, filepath, max_blocks, pref):
    prefix = makeTmpDir(pref, filepath)
    captureToFiles(context, filepath, prefix, max_blocks)
    filesToBlender(context, prefix, max_blocks)
