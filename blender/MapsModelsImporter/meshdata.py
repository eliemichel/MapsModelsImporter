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

# This file contains substancial parts of RenderDoc's documentation examples.

import struct
import renderdoc as rd
from profiling import Timer, profiling_counters
import numpy as np

# -----------------------------------------------------------------------------

def fmt2struct(fmt):
    """Convert fmt format specification to struct-style format char"""
    if fmt.Special():
        raise RuntimeError("Packed formats are not supported!")
    #           012345678
    uintfmt  = "xBHxIxxxL"
    sintfmt  = "xbhxixxxl"
    floatfmt = "xxexfxxxd" # only 2, 4 and 8 are valid
    formatChars = {
        rd.CompType.UInt:    uintfmt,
        rd.CompType.SInt:    sintfmt,
        rd.CompType.Float:   floatfmt,
        rd.CompType.UNorm:   uintfmt,
        rd.CompType.UScaled: uintfmt,
        rd.CompType.SNorm:   sintfmt,
        rd.CompType.SScaled: sintfmt,
        #rd.CompType.Double:  floatfmt,
    }
    return str(fmt.compCount) + formatChars[fmt.compType][fmt.compByteWidth]

def unpackData(fmt, data):
    """Unpack raw data given a fmt format specification"""
    value = struct.unpack_from(fmt2struct(fmt), data, 0)

    # Post process
    if fmt.compType == rd.CompType.UNorm:
        divisor = float((1 << (fmt.compByteWidth * 8)) - 1)
        value = tuple(float(x) / divisor for x in value)
    elif fmt.compType == rd.CompType.SNorm:
        maxNeg = -(1 << (fmt.compByteWidth * 8 - 1))
        divisor = float(-(maxNeg-1))
        value = tuple((float(x) if (x == maxNeg) else (float(x) / divisor)) for x in value)
    if fmt.BGRAOrder():
        # If the format is BGRA, swap the two components
        value = tuple(value[i] for i in [2, 1, 0, 3])

    return value

def unpackDataNumpy(fmt, data, stride=None, count=-1):
    compType = {
        rd.CompType.UInt:    'u',
        rd.CompType.SInt:    'i',
        rd.CompType.Float:   'f',
        rd.CompType.UNorm:   'u',
        rd.CompType.UScaled: 'u',
        rd.CompType.SNorm:   'i',
        rd.CompType.SScaled: 'i',
        #rd.CompType.Double:  'f',
    }[fmt.compType]
    data_field = ('data', f"{fmt.compCount}{compType}{fmt.compByteWidth}")

    dtype = np.dtype([data_field])
    if stride is not None:
        missing = stride - dtype.itemsize
        if missing > 0:
            dtype = np.dtype([data_field, ('align', f"{missing}u1")])
            #data = np.array(data).reshape((-1, stride))
            #data = data[:,:dtype.itemsize].reshape(-1)
            data = data + b'\x00' * missing

    try:
        decoded = np.frombuffer(data, dtype, count=count)['data']
    except ValueError as err:
        print(err)
        print(data)
        print(f"len(data) = {len(data)}")
        print(f"dtype = {dtype}")
        print(f"dtype.itemsize = {dtype.itemsize}")
        print(f"stride = {stride}")
        print(f"count = {count}")
    #decoded = decoded.reshape((-1, fmt.compCount))

    # Post process
    if fmt.compType == rd.CompType.UNorm:
        divisor = float((1 << (fmt.compByteWidth * 8)) - 1)
        decoded = decoded.astype('f') / divisor
    elif fmt.compType == rd.CompType.SNorm:
        maxNeg = -(1 << (fmt.compByteWidth * 8 - 1))
        divisor = float(-(maxNeg-1))

        mask = decoded != maxNeg
        decoded = decoded.astype('f')
        decoded[mask] /= divisor
    if fmt.BGRAOrder():
        # If the format is BGRA, swap the two components
        decoded = decoded[:,[2, 1, 0, 3]]

    return decoded

# -----------------------------------------------------------------------------

class MeshData(rd.MeshFormat):
    indexOffset = 0
    name = ''

    def build(mesh, attr, ib, vbs, draw):
        # We don't handle instance attributes
        if attr.perInstance:
            raise RuntimeError("Instanced properties are not supported!")

        mesh.indexResourceId = ib.resourceId
        mesh.indexByteOffset = ib.byteOffset
        mesh.indexByteStride = ib.byteStride
        mesh.baseVertex = draw.baseVertex
        mesh.indexOffset = draw.indexOffset
        mesh.numIndices = draw.numIndices

        # If the draw doesn't use an index buffer, don't use it even if bound
        if not (draw.flags & rd.ActionFlags.Indexed):
            mesh.indexResourceId = rd.ResourceId.Null()

        # The total offset is the attribute offset from the base of the vertex
        mesh.vertexByteOffset = attr.byteOffset + vbs[attr.vertexBuffer].byteOffset
        mesh.format = attr.format
        mesh.vertexResourceId = vbs[attr.vertexBuffer].resourceId
        mesh.vertexByteStride = vbs[attr.vertexBuffer].byteStride
        mesh.name = attr.name

    def fetchIndices(mesh, controller):
        # If indexed draw call
        if mesh.indexResourceId != rd.ResourceId.Null():
            # struct-style format string
            ibdata = controller.GetBufferData(mesh.indexResourceId, mesh.indexByteOffset, 0)
            offset = mesh.indexOffset * mesh.indexByteStride

            dtype = np.dtype(f"u{mesh.indexByteStride}")
            indices = np.frombuffer(ibdata, dtype=dtype, count=mesh.numIndices, offset=offset) + mesh.baseVertex
        else:
            indices = np.range(mesh.baseVertex, mesh.baseVertex + mesh.numIndices)

        return indices

    def fetchData(mesh, controller):
        indices = mesh.fetchIndices(controller)

        if len(indices) == 0:
            return []
        data = controller.GetBufferData(mesh.vertexResourceId, mesh.vertexByteOffset, 0)

        maxi = max(indices) + 1
        unpacked = unpackDataNumpy(mesh.format, data, stride=mesh.vertexByteStride, count=maxi)

        return unpacked

    def fetchTriangle(mesh, controller):
        indices = mesh.fetchIndices(controller)
        unpacked = mesh.fetchData(controller)
        for idx in indices[:3]:
            value = unpacked[idx]

# -----------------------------------------------------------------------------

def makeMeshData(attr, ib, vbs, draw):
    """For some reason, it crashes when MeshData.build() is
    MeshData.__init__() so this wrapper works this around"""
    m = MeshData()
    m.build(attr, ib, vbs, draw)
    return m
