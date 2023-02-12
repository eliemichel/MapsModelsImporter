# Copyright (c) 2019 - 2021 Elie Michel
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
import numpy as np

from .profiling import Timer, profiling_counters
from .utils import getBinaryDir, makeTmpDir
from .preferences import getPreferences

SCRIPT_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "google_maps_rd.py")

MSG_CONSOLE_DEBUG_OUTPUT = """\nPlease report to MapsModelsImporter developers providing the full console log with debug information.
First turn on debug output by activating the "Debug Info"-checkbox under Edit > Preferences > Add-ons > MapsModelsImporter
On Windows systems console log is accessible in Windows > Toggle System Console (right click to copy).
On Linux systems you have to run Blender from the console to get the debug output"""
MSG_INCORRECT_RDC = """Invalid RDC capture file. Please make sure that:
1. You are using the recommended RenderDoc Version for this Add-on
   - RenderDoc Version 1.5 - 1.9 for MapsModelsImporter <= 0.3.2
   - RenderDoc Version = 1.10 for MapsModelsImporter >= 0.3.3 and <= 0.3.7
   - RenderDoc Version 1.13 - 1.14 for MapsModelsImporter >= 0.4.0  and <= 0.4.2
   - RenderDoc Version = 1.19 for MapsModelsImporter >= 0.5.0
2. You are importing from Google Maps or Google Earth web
3. You were MOVING in the 3D view while taking the capture (you can use the "Capture after delay"-button in RenderDoc).

Before opening a new Issue on GitHub please download a working sample file to check if this works on your Computer.
Please be patient. If there's no error message it might still be loading. 
It can take a minute or two to load it and Blender will get unresponsive during this time.
Find sample files here: https://github.com/eliemichel/MapsModelsImporter-samples

If it works with a sample file you most probably shouldn't open a new issue on GitHub but figure out how to use RenderDoc.
Find instructions about using RenderDoc by searching YouTube for "Capturing Google Maps with RenderDoc"

If the sample file doesn't work:""" + MSG_CONSOLE_DEBUG_OUTPUT
MSG_RDMODULE_NOT_FOUND = "Error: Can't find the RenderDoc Module." + MSG_CONSOLE_DEBUG_OUTPUT
MSG_RDMODULE_IMPORT_ERROR = "Error: Failed to load the RenderDoc Module." + MSG_CONSOLE_DEBUG_OUTPUT
MSG_UNKNOWN_ERROR = "Error: An unknown Error occurred!" + MSG_CONSOLE_DEBUG_OUTPUT

class MapsModelsImportError(Exception):
    pass

def captureToFiles(context, filepath, prefix, max_blocks):
    """Extract binary files and textures from a RenderDoc capture file.
    This spawns a standalone Python interpreter because renderdoc module cannot be loaded in embedded Python"""
    pref = getPreferences(context)
    if bpy.app.version < (2,91,0):
        blender_dir = os.path.dirname(sys.executable)
        blender_version = ("{0}.{1}").format(*bpy.app.version)
        python_home = os.path.join(blender_dir, blender_version, "python")
        python = os.path.join(python_home, "bin", "python.exe" if sys.platform == "win32" else "python3.7m") # warning: hardcoded python version for non-windows might fail with Blender update
    else:
        python = sys.executable
        python_home = os.path.dirname(os.path.dirname(sys.executable))
    os.environ["PYTHONHOME"] = python_home
    os.environ["PYTHONPATH"] = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] += os.pathsep + os.path.abspath(getBinaryDir())
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PATH"] += os.pathsep + os.path.join(python_home, "bin")
    try:
        out = subprocess.check_output([python, SCRIPT_PATH, filepath, prefix, str(max_blocks)], stderr=subprocess.STDOUT, text=True)
        if pref.debug_info:
            print("google_maps_rd returned:")
            print(out)
    except subprocess.CalledProcessError as err:
        if pref.debug_info:
            print("\n==========================================================================================")
            print("google_maps_rd failed and returned:")
            print(err.output)
            print(f"\nExtra info:\n - python = {python}\n - python_home = {python_home}")
        if err.returncode == 20: #error codes 20 and 21 are defined in google_maps_rd.py
            ERROR_MESSAGE = MSG_RDMODULE_NOT_FOUND
        elif err.returncode == 21:
            ERROR_MESSAGE = MSG_RDMODULE_IMPORT_ERROR
        elif err.returncode == 1:
            ERROR_MESSAGE = MSG_INCORRECT_RDC
            if pref.debug_info:
                print(MSG_INCORRECT_RDC)
        else:
            ERROR_MESSAGE = MSG_UNKNOWN_ERROR + "\nReturncode: " + err.returncode
        raise MapsModelsImportError(ERROR_MESSAGE)

# -----------------------------------------------------------------------------

import bpy
import bmesh
import pickle
from bpy_extras import object_utils
from math import floor, pi
from mathutils import Matrix
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
        _uParams = makeMatrix(globUniforms['_uParams'])
        #uvOffsetScale = [0, -1, 1, -1]
        uvOffsetScale = [
            _uParams[2][2] / _uParams[0][2],
            (_uParams[3][2] - 1) / _uParams[1][2],
            _uParams[0][2],
            -_uParams[1][2],
        ]
        matrix = makeMatrix(globUniforms['_uMV'])

        """
        postMatrix = Matrix(
            ((0.682889997959137, 0.20221230387687683, 0.7019768357276917, -0.06431722640991211),
            (0.07228320091962814, 0.9375065565109253, -0.3403771221637726, -0.11041564494371414),
            (-0.7269363403320312, 0.28318125009536743, 0.6255972981452942, -1.349690556526184),
            (0.0, 0.0, 0.0, 1.0))
            ) @ Matrix.Scale(500, 4)
        """
    else:
        if refMatrix is None:
            print("globUniforms:")
            for k, v in globUniforms.items():
                print("  {}: {}".format(k, v))
            raise MapsModelsImportError(MSG_INCORRECT_RDC)
        else:
            return None, None, None
    
    if refMatrix is None:
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
    if img is not None:
        texture_node = nodes.new(type="ShaderNodeTexImage")
        texture_node.image = img
        links = mat.node_tree.links
        link = links.new(texture_node.outputs[0], principled.inputs[0])

def numpyLoad(file):
    (dim,) = np.fromfile(file, dtype=np.int, count=1)
    shape = np.fromfile(file, dtype=np.int, count=dim)
    dt = np.dtype(file.read(2).decode('ascii'))
    array = np.fromfile(file, dtype=dt)
    array = array.reshape(shape)
    return array

def loadData(prefix, drawcall_id):
    with open("{}{:05d}-indices.bin".format(prefix, drawcall_id), 'rb') as file:
        #indices = pickle.load(file)
        indices = numpyLoad(file)

    with open("{}{:05d}-positions.bin".format(prefix, drawcall_id), 'rb') as file:
        #positions = pickle.load(file)
        positions = numpyLoad(file)

    with open("{}{:05d}-uv.bin".format(prefix, drawcall_id), 'rb') as file:
        #uvs = pickle.load(file)
        uvs = numpyLoad(file)

    texture_filename = "{}{:05d}-texture.png".format(prefix, drawcall_id)
    if os.path.isfile(texture_filename):
        img = bpy.data.images.load(texture_filename)
    else:
        img = None

    with open("{}{:05d}-constants.bin".format(prefix, drawcall_id), 'rb') as file:
        constants = pickle.load(file)

    return indices, positions, uvs, img, constants

# -----------------------------------------------------------------------------

def filesToBlender(context, prefix, max_blocks=200, globalScale=1.0/256.0):
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

        timer = Timer()
        try:
            indices, positions, uvs, img, constants = loadData(prefix, drawcall_id)
        except FileNotFoundError as err:
            print("Skipping ({})".format(err))
            drawcall_id += 1
            continue
        profiling_counters["loadData"].add_sample(timer)

        uvOffsetScale, matrix, refMatrix = extractUniforms(constants, refMatrix)
        if uvOffsetScale is None:
            drawcall_id += 1
            continue
        
        timer = Timer()
        # Make triangles from triangle strip index buffer
        n = len(indices)
        if constants["DrawCall"]["topology"] == 'TRIANGLE_STRIP':
            tris = [ [ indices[i+j] for j in [[0,1,2],[0,2,1]][i%2] ] for i in range(n - 3)]
            tris = [ t for t in tris if t[0] != t[1] and t[0] != t[2] and t[1] != t[2] ]
        else:
            tris = [ [ indices[3*i+j] for j in range(3) ] for i in range(n//3) ]

        if len(indices) == 0:
            continue

        if constants["DrawCall"]["type"] == 'Google Maps':
            verts = positions[:,:3] * 256.0 # [ [ p[0] * 256.0, p[1] * 256.0, p[2] * 256.0 ] for p in positions ]
        elif constants["DrawCall"]["type"] == 'Mapy CZ':
            raw_verts = positions[:,:3]
            verts = []
            globUniforms = constants['$Globals']
            _uParamsSE = makeMatrix(globUniforms['_uParamsSE'])
            for v0 in raw_verts:
                r0 = [0.0, 0.0, 0.0, 0.0]
                r1 = np.zeros((3,), dtype=np.float32)
                r2 = np.zeros((3,), dtype=np.float32)
                r1[0] = v0[0] * _uParamsSE[3][0] + _uParamsSE[0][0]
                r1[1] = v0[1] * _uParamsSE[0][1] + _uParamsSE[1][0]
                r1[2] = (v0[2] * _uParamsSE[1][1] + _uParamsSE[2][0]) * _uParamsSE[3][3]
                r0[1] = np.linalg.norm(r1)
                r0[2] = r0[1] + 0.0001
                r0[1] = r0[1] - _uParamsSE[2][3]
                r0[2] = 1.0 / r0[2]
                r1 *= r0[2]
                r0[2] = min(max(r0[1], _uParamsSE[1][2]), _uParamsSE[3][2]) # clamp
                r0[2] = (r0[2] - _uParamsSE[1][2]) * _uParamsSE[0][3] * _uParamsSE[1][3] + _uParamsSE[2][2]
                r0[1] = r0[1] * r0[2] - r0[1]
                r2[0] = v0[0] * _uParamsSE[3][0]
                r2[1] = v0[1] * _uParamsSE[0][1]
                r2[2] = v0[2] * _uParamsSE[1][1]
                r2 += r1 * r0[1]
                verts.append(r2.tolist())
        else:
            verts = positions[:,:3] # [ [ p[0], p[1], p[2] ] for p in positions ]

        [ou, ov, su, sv] = uvOffsetScale
        if uvs is not None and uvs.shape[1] > 2: # len(uvs[0]) > 2:
            uvs = uvs[:,:2] # [u[:2] for u in uvs]

        if constants["DrawCall"]["type"] == 'Google Maps':
            #uvs = [ [ (floor(u * 65535.0 + 0.5) + ou) * su, (floor(v * 65535.0 + 0.5) + ov) * sv ] for u, v in uvs ]
            uvs = (uvs * 65535.0 + 0.5 + np.array([ou, ov])) * np.array([su, sv])
        else:
            #uvs = [ [ (u + ou) * su, (v + ov) * sv ] for u, v in uvs ]
            uvs = (uvs + np.array([ou, ov])) * np.array([su, sv])

        profiling_counters["processData"].add_sample(timer)


        mesh_name = "BuildingMesh-{:05d}".format(drawcall_id)
        timer = Timer()
        obj = addMesh(context, mesh_name, verts, tris, uvs)
        profiling_counters["addMesh"].add_sample(timer)
        obj.matrix_world = matrix * globalScale

        mat_name = "BuildingMat-{:05d}".format(drawcall_id)
        addImageMaterial(mat_name, obj, img)

        drawcall_id += 1

    # Save reference matrix
    if refMatrix:
        values = sum([list(v) for v in refMatrix], [])
        context.scene.maps_models_importer_ref_matrix = values
        context.scene.maps_models_importer_is_ref_matrix_valid = True

    pref = getPreferences(context)
    if pref.debug_info:
        print("Profiling counters:")
        for key, counter in profiling_counters.items():
            print(f" - {key}: {counter.summary()}")

    return None # no error

# -----------------------------------------------------------------------------

def importCapture(context, filepath, max_blocks, pref):
    prefix = makeTmpDir(pref, filepath)
    captureToFiles(context, filepath, prefix, max_blocks)
    filesToBlender(context, prefix, max_blocks)
