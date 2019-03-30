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

import os
import platform
import random

# -----------------------------------------------------------------------------

def randomHash(length=7):
	alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
	return ''.join([random.choice(alphabet) for i in range(length)])

# -----------------------------------------------------------------------------

def getBinaryDir():
	"""Get the directory where the RenderDoc binaries is located. This is platform specific"""
	platform_dir = {
		"Windows": {
			"32bit": "win32",
			"64bit": "win64",
		},
		"Linux": {
			"32bit": "linux32",
			"64bit": "linux64",
		},
	}[platform.system()][platform.architecture()[0]]
	return os.path.join(os.path.dirname(os.path.realpath(__file__)), "bin", platform_dir)

# -----------------------------------------------------------------------------

def makeTmpDir(pref, filepath=None):
	"""Create a temporary directory in the tmp dir specified in preferences. filepath can be specified to hint the name.
	@return prefix, with the temporary dir plus a prefix if filepath was provided"""
	prefix = ""
	if filepath is not None:
		prefix = os.path.splitext(os.path.basename(filepath))[0] + "-"
	parent = pref.tmp_dir
	if not parent:
		if filepath is not None:
			parent = os.path.dirname(filepath)
		else:
			parent = "C:\tmp" if platform.system() == "Windows" else "/tmp"
	base = os.path.join(parent, prefix + randomHash(7))
	while os.path.isdir(base):
		base = os.path.join(parent, prefix + randomHash(7))
	os.makedirs(base)
	return os.path.join(base, prefix)
