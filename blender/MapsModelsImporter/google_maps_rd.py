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

MSG_RD_IMPORT_FAILED = """Error: Failed to load the RenderDoc module. It however seems to exist.
This is most likely due to your Blender version uses another version of python. It might also be that a additional file is missing (i.E. DLL)
Remember, you must use exactly the same version of python to load the RenderDoc module as was used to build it.\n"""

import sys
import pickle
import struct
try:
    import renderdoc as rd
except ModuleNotFoundError as err:
    print("Error: Can't find RenderDoc library.")
    print("sys.path contains the following paths:\n")
    print(*sys.path, sep = "\n")
except ImportError as err:
    print(MSG_RD_IMPORT_FAILED)
    print("Python version used by your Blender installation: ",sys.version)
    print("err.name: ",err.name)
    print("err.path: ",err.path)
    print("Error Message: ", err,"\n")

from meshdata import MeshData, makeMeshData
from rdutils import CaptureWrapper

_, CAPTURE_FILE, FILEPREFIX, MAX_BLOCKS_STR = sys.argv[:4]
MAX_BLOCKS = int(MAX_BLOCKS_STR)

class CaptureScraper():
    def __init__(self, controller):
        self.controller = controller

    def findDrawcallBatch(self, drawcalls, first_call_prefix, drawcall_prefix, last_call_prefix):
        batch = []
        has_batch_started = False
        for last_call_index, draw in enumerate(drawcalls):
            if has_batch_started:
                if not draw.name.startswith(drawcall_prefix):
                    if draw.name.startswith(last_call_prefix) and batch != []:
                        break
                    else:
                        print("(Skipping drawcall {})".format(draw.name))
                        continue
                batch.append(draw)
            else:
                print(f"Not relevant yet: {draw.name}")
            if draw.name.startswith(first_call_prefix):
                has_batch_started = True
                if draw.name.startswith(drawcall_prefix):
                    batch.append(draw)
        return batch, last_call_index

    def getVertexShaderConstants(self, draw, state=None):
        controller = self.controller
        if state is None:
            controller.SetFrameEvent(draw.eventId, True)
            state = controller.GetPipelineState()

        shader = state.GetShader(rd.ShaderStage.Vertex)
        ep = state.GetShaderEntryPoint(rd.ShaderStage.Vertex)
        ref = state.GetShaderReflection(rd.ShaderStage.Vertex)
        constants = {}
        for cbn, cb in enumerate(ref.constantBlocks):
            block = {}
            cbuff = state.GetConstantBuffer(rd.ShaderStage.Vertex, cbn, 0)
            variables = controller.GetCBufferVariableContents(
                state.GetGraphicsPipelineObject(),
                shader,
                ep,
                cb.bindPoint,
                cbuff.resourceId,
                0,
                0
            )
            for var in variables:
                val = 0
                if var.members:
                    val = []
                    for member in var.members:
                        memval = 0
                        if member.type == rd.VarType.Float:
                            memval = member.value.fv[:member.rows * member.columns]
                        elif member.type == rd.VarType.Int:
                            memval = member.value.iv[:member.rows * member.columns]
                        else:
                            print("Unsupported type!")
                        # ...
                        val.append(memval)
                else:
                    if var.type == rd.VarType.Float:
                        val = var.value.fv[:var.rows * var.columns]
                    elif var.type == rd.VarType.Int:
                        val = var.value.iv[:var.rows * var.columns]
                    else:
                        print("Unsupported type!")
                    # ...
                block[var.name] = val
            constants[cb.name] = block
        return constants

    def hasUniform(self, draw, uniform):
        constants = self.getVertexShaderConstants(draw)
        return uniform in constants['$Globals']

    def extractRelevantCalls(self, drawcalls, _strategy=0):
        """List the drawcalls related to drawing the 3D meshes thank to a ad hoc heuristic
        It may different in RenderDoc UI and in Python module, for some reason
        """
        first_call = ""
        last_call = "glDrawArrays(4)"
        drawcall_prefix = "glDrawElements"
        min_drawcall = 0
        capture_type = "Google Maps"
        if _strategy == 0:
            first_call = "glClear(Color = <0.000000, 0.000000, 0.000000, 1.000000>, Depth = <1.000000>)"
        elif _strategy == 1:
            first_call = "glClear(Color = <0.000000, 0.000000, 0.000000, 1.000000>, Depth = <1.000000>, Stencil = <0x00>)"
        elif _strategy == 2:
            first_call = "glClear(Color = <0.000000, 0.000000, 0.000000, 1.000000>, Depth = <0.000000>)"
        elif _strategy == 3:
            first_call = "glClear(Color = <0.000000, 0.000000, 0.000000, 1.000000>, Depth = <0.000000>, Stencil = <0x00>)"
        elif _strategy == 4:
            first_call = ""
            last_call = "ClearDepthStencilView"
            drawcall_prefix = "DrawIndexed"
            capture_type = "Mapy CZ"
        elif _strategy == 5:
            # With Google Earth there are two batches of DrawIndexed calls, we are interested in the second one
            first_call = "DrawIndexed"
            last_call = ""
            drawcall_prefix = "DrawIndexed"
            capture_type = "Google Earth"
            skipped_drawcalls, min_drawcall = self.findDrawcallBatch(drawcalls, first_call, drawcall_prefix, last_call)
            if not skipped_drawcalls or not self.hasUniform(skipped_drawcalls[0], "_uProjModelviewMatrix"):
                first_call = "INVALID CASE, SKIP ME"
        elif _strategy == 6:
            # Actually sometimes there's only one batch
            first_call = "DrawIndexed"
            last_call = ""
            drawcall_prefix = "DrawIndexed"
            capture_type = "Google Earth (single)"
        elif _strategy == 7:
            first_call = "ClearRenderTargetView(0.000000, 0.000000, 0.000000"
            last_call = "Draw(4)"
            drawcall_prefix = "DrawIndexed"
        elif _strategy == 8:
            first_call = "" # Try from the beginning on
            last_call = "Draw(4)"
            drawcall_prefix = "DrawIndexed"
        else:
            print("Error: Could not find the beginning of the relevant 3D draw calls")
            return [], "none"

        print(f"Trying scrapping strategy #{_strategy}...")
        relevant_drawcalls, _ = self.findDrawcallBatch(
            drawcalls[min_drawcall:],
            first_call,
            drawcall_prefix,
            last_call)
        
        if not relevant_drawcalls:
            return self.extractRelevantCalls(drawcalls, _strategy=_strategy+1)

        if capture_type == "Mapy CZ" and not self.hasUniform(relevant_drawcalls[0], "_uMV"):
            return self.extractRelevantCalls(drawcalls, _strategy=_strategy+1)

        if capture_type == "Google Earth (single)":
            if not self.hasUniform(relevant_drawcalls[0], "_uMeshToWorldMatrix"):
                return self.extractRelevantCalls(drawcalls, _strategy=_strategy+1)
            else:
                capture_type = "Google Earth"

        return relevant_drawcalls, capture_type

    def run(self):
        controller = self.controller
        drawcalls = controller.GetDrawcalls()
        relevant_drawcalls, capture_type = self.extractRelevantCalls(drawcalls)
        print(f"Scrapping capture from {capture_type}...")

        if MAX_BLOCKS <= 0:
            max_drawcall = len(relevant_drawcalls)
        else:
            max_drawcall = min(MAX_BLOCKS, len(relevant_drawcalls))

        for drawcallId, draw in enumerate(relevant_drawcalls[:max_drawcall]):
            print("Draw call: " + draw.name)
            
            controller.SetFrameEvent(draw.eventId, True)
            state = controller.GetPipelineState()

            ib = state.GetIBuffer()
            vbs = state.GetVBuffers()
            attrs = state.GetVertexInputs()
            meshes = [makeMeshData(attr, ib, vbs, draw) for attr in attrs]

            try:
                # Position
                m = meshes[0]
                m.fetchTriangle(controller)
                indices = m.fetchIndices(controller)
                with open("{}{:05d}-indices.bin".format(FILEPREFIX, drawcallId), 'wb') as file:
                    pickle.dump(indices, file)
                unpacked = m.fetchData(controller)
                with open("{}{:05d}-positions.bin".format(FILEPREFIX, drawcallId), 'wb') as file:
                    pickle.dump(unpacked, file)

                # UV
                m = meshes[2 if capture_type == "Google Earth" else 1]
                m.fetchTriangle(controller)
                unpacked = m.fetchData(controller)
                with open("{}{:05d}-uv.bin".format(FILEPREFIX, drawcallId), 'wb') as file:
                    pickle.dump(unpacked, file)
            except Exception as err:
                print("(Skipping because of error: {})".format(err))
                continue

            # Vertex Shader Constants
            shader = state.GetShader(rd.ShaderStage.Vertex)
            ep = state.GetShaderEntryPoint(rd.ShaderStage.Vertex)
            ref = state.GetShaderReflection(rd.ShaderStage.Vertex)
            constants = self.getVertexShaderConstants(draw, state=state)
            constants["DrawCall"] = {
                "topology": 'TRIANGLE_STRIP' if draw.topology == rd.Topology.TriangleStrip else 'TRIANGLES',
                "type": capture_type
            }
            with open("{}{:05d}-constants.bin".format(FILEPREFIX, drawcallId), 'wb') as file:
                pickle.dump(constants, file)

            self.extractTexture(drawcallId, state)

    def extractTexture(self, drawcallId, state):
        """Save the texture in a png file (A bit dirty)"""
        bindpoints = state.GetBindpointMapping(rd.ShaderStage.Fragment)
        if not bindpoints.samplers:
            print(f"Warning: No texture found for drawcall {drawcallId}")
            return
        texture_bind = bindpoints.samplers[-1].bind
        resources = state.GetReadOnlyResources(rd.ShaderStage.Fragment)
        rid = resources[texture_bind].resources[0].resourceId
    
        texsave = rd.TextureSave()
        texsave.resourceId = rid
        texsave.mip = 0
        texsave.slice.sliceIndex = 0
        texsave.alpha = rd.AlphaMapping.Preserve
        texsave.destType = rd.FileType.PNG
        controller.SaveTexture(texsave, "{}{:05d}-texture.png".format(FILEPREFIX, drawcallId))

def main(controller):
    scraper = CaptureScraper(controller)
    scraper.run()

if __name__ == "__main__":
    if 'pyrenderdoc' in globals():
        pyrenderdoc.Replay().BlockInvoke(main)
    else:
        print("Loading capture from {}...".format(CAPTURE_FILE))
        with CaptureWrapper(CAPTURE_FILE) as controller:
            main(controller)
    
