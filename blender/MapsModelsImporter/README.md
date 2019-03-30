Maps Models Importer
====================

*Maps Models Importer* is a set of tools for importint 3D models from wide maps in 3D content softwares.
This is a proof of concept containing only a Blender add-on for importing 3D models from Google Maps.

The `blender` directory contains the source code of the Blender add-on importing captures recorded with [RenderDoc](https://renderdoc.org/):

![Screenshot of blender addon in action](doc/screenshot.png)

Disclaimer
----------

This is a proof of concept showcasing how the 3D render process of Google Maps can be inspected. This is intended for educational purpose only. For a more in-depth analysis, see [](TODO)

Do not use this for any commercial nor redistribution purpose. Actually, the use of such tool might be allowed for private read-only use, as this is what happens when browsing Google Maps, but not beyond. I do not take responsibility for any use of this tool.


Help Wanted
-----------

This repository does not provide the required RenderDoc binaries for linux nor for OSX. If you have such a system, build RenderDoc against Python 3.7.0 (the minor version matters) to be compatible with the version of Blender's Python distribution.

