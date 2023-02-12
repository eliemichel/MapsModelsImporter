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

MSG_RD_IMPORT_FAILED = """Error: Failed to load the RenderDoc Module. It however seems to exist.
This might be due to one of the following reasons:
 - Your Blender version uses another version of python than used to build the RenderDoc Module
 - An additional file required by the RenderDoc Module is missing (i.E. renderdoc.dll)
 - Something completely different

Remember, you must use exactly the same version of python to load the RenderDoc Module as was used to build it.
Find more information about building the RenderDoc Module here: https://github.com/baldurk/renderdoc/blob/v1.x/docs/CONTRIBUTING/Compiling.md\n"""

import sys
import pickle
import struct
import numpy as np

try:
    import renderdoc as rd
except ModuleNotFoundError as err:
    print("Error: Can't find the RenderDoc Module.")
    print("sys.path contains the following paths:\n")
    print(*sys.path, sep = "\n")
    sys.exit(20)
except ImportError as err:
    print(MSG_RD_IMPORT_FAILED)
    print("sys.platform: ", sys.platform)
    print("Python version: ",sys.version)
    print("err.name: ",err.name)
    print("err.path: ",err.path)
    print("Error Message: ", err,"\n")
    sys.exit(21)

from meshdata import MeshData, makeMeshData
from profiling import Timer, profiling_counters
from rdutils import CaptureWrapper

_, CAPTURE_FILE, FILEPREFIX, MAX_BLOCKS_STR = sys.argv[:4]
MAX_BLOCKS = int(MAX_BLOCKS_STR)

def numpySave(array, file):
    np.array([array.ndim], dtype=np.int32).tofile(file)
    np.array(array.shape, dtype=np.int32).tofile(file)
    dt = array.dtype.descr[0][1][1:3].encode('ascii')
    file.write(dt)
    array.tofile(file)

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
            elif draw.name.startswith(first_call_prefix):
                has_batch_started = True
                if draw.name.startswith(drawcall_prefix):
                    batch.append(draw)
            else:
                print(f"Not relevant yet: {draw.name}")
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
                rd.ShaderStage.Vertex,
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
                            memval = member.value.f32v[:member.rows * member.columns]
                        elif member.type == rd.VarType.Int:
                            memval = member.value.s32v[:member.rows * member.columns]
                        else:
                            print("Unsupported type!")
                        # ...
                        val.append(memval)
                else:
                    if var.type == rd.VarType.Float:
                        val = var.value.f32v[:var.rows * var.columns]
                    elif var.type == rd.VarType.Int:
                        val = var.value.s32v[:var.rows * var.columns]
                    else:
                        print("Unsupported type!")
                    # ...
                block[var.name] = val
            constants[cb.name] = block
        return constants

    def hasUniform(self, draw, uniform):
        constants = self.getVertexShaderConstants(draw)
        return uniform in constants['$Globals']

    def extractRelevantCalls(self, drawcalls, _strategy=4):
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
            min_drawcall = 0
            while True:
                skipped_drawcalls, new_min_drawcall = self.findDrawcallBatch(drawcalls[min_drawcall:], first_call, drawcall_prefix, last_call)
                if not skipped_drawcalls or self.hasUniform(skipped_drawcalls[0], "_uMeshToWorldMatrix"):
                    break
                min_drawcall += new_min_drawcall
        elif _strategy == 6:
            # Actually sometimes there's only one batch
            first_call = "DrawIndexed"
            last_call = ""
            drawcall_prefix = "DrawIndexed"
            capture_type = "Google Earth (single)"
        elif _strategy == 7:
            first_call = "ClearRenderTargetView(0.000000, 0.000000, 0.000000"
            last_call = "Draw()"
            drawcall_prefix = "DrawIndexed"
        elif _strategy == 8:
            first_call = "" # Try from the beginning on
            last_call = "Draw()"
            drawcall_prefix = "DrawIndexed"
            min_drawcall = 0
            while True:
                skipped_drawcalls, new_min_drawcall = self.findDrawcallBatch(drawcalls[min_drawcall:], first_call, drawcall_prefix, last_call)
                if not skipped_drawcalls or self.hasUniform(skipped_drawcalls[0], "_w"):
                    break
                min_drawcall += new_min_drawcall
        else:
            print("Error: Could not find the beginning of the relevant 3D draw calls")
            return [], "none"

        print(f"Trying scraping strategy #{_strategy} (from draw call #{min_drawcall})...")
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

        if capture_type == "Google Earth":
            relevant_drawcalls = [
                call for call in relevant_drawcalls
                if self.hasUniform(call, "_uMeshToWorldMatrix")
            ]

        return relevant_drawcalls, capture_type


    def consolidateEvents(self, rootList, accumulator = []):
        for root in rootList:
            name = root.GetName(self.controller.GetStructuredFile())
            event = root
            setattr(root, 'name', name.split('::', 1)[-1])
            accumulator.append(event)
            self.consolidateEvents(root.children, accumulator)
        return accumulator

    def run(self):
        controller = self.controller

        timer = Timer()
        drawcalls = self.consolidateEvents(controller.GetRootActions())
        profiling_counters['consolidateEvents'].add_sample(timer)
        
        timer = Timer()
        relevant_drawcalls, capture_type = self.extractRelevantCalls(drawcalls)
        profiling_counters['extractRelevantCalls'].add_sample(timer)

        print(f"Scraping capture from {capture_type}...")

        if MAX_BLOCKS <= 0:
            max_drawcall = len(relevant_drawcalls)
        else:
            max_drawcall = min(MAX_BLOCKS, len(relevant_drawcalls))

        for drawcallId, draw in enumerate(relevant_drawcalls[:max_drawcall]):
            timer = Timer()
            #print("Draw call: " + draw.name)
            
            controller.SetFrameEvent(draw.eventId, True)
            state = controller.GetPipelineState()

            ib = state.GetIBuffer()
            vbs = state.GetVBuffers()
            attrs = state.GetVertexInputs()
            meshes = [makeMeshData(attr, ib, vbs, draw) for attr in attrs]

            try:
                # Position
                m = meshes[0]
                #m.fetchTriangle(controller)
                indices = m.fetchIndices(controller)
                with open("{}{:05d}-indices.bin".format(FILEPREFIX, drawcallId), 'wb') as file:
                    numpySave(indices, file)

                subtimer = Timer()
                unpacked = m.fetchData(controller)
                with open("{}{:05d}-positions.bin".format(FILEPREFIX, drawcallId), 'wb') as file:
                    numpySave(unpacked, file)

                # UV
                if len(meshes) < 2:
                    raise Exception("No UV data")
                m = meshes[2 if capture_type == "Google Earth" else 1]
                #m.fetchTriangle(controller)
                unpacked = m.fetchData(controller)
                with open("{}{:05d}-uv.bin".format(FILEPREFIX, drawcallId), 'wb') as file:
                    numpySave(unpacked, file)
            except Exception as err:
                print("(Skipping because of error: {})".format(err))
                continue

            # Vertex Shader Constants
            shader = state.GetShader(rd.ShaderStage.Vertex)
            ep = state.GetShaderEntryPoint(rd.ShaderStage.Vertex)
            ref = state.GetShaderReflection(rd.ShaderStage.Vertex)
            constants = self.getVertexShaderConstants(draw, state=state)
            constants["DrawCall"] = {
                "topology": 'TRIANGLE_STRIP' if state.GetPrimitiveTopology() == rd.Topology.TriangleStrip else 'TRIANGLES',
                "type": capture_type
            }
            with open("{}{:05d}-constants.bin".format(FILEPREFIX, drawcallId), 'wb') as file:
                pickle.dump(constants, file)

            subtimer = Timer()
            self.extractTexture(drawcallId, state)
            profiling_counters['extractTexture'].add_sample(subtimer)

            profiling_counters['processDrawEvent'].add_sample(timer)

        print("Profiling counters:")
        for key, counter in profiling_counters.items():
            print(f" - {key}: {counter.summary()}")

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
        timer = Timer()
        controller.SaveTexture(texsave, "{}{:05d}-texture.png".format(FILEPREFIX, drawcallId))
        profiling_counters["SaveTexture"].add_sample(timer)

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
    
