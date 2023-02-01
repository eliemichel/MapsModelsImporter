```
Get python source code in Python-X.X.X
Get embedable release in python-X.X.X-embed-amd64

Edit qrenderdoc/pythonXX.natvis

Copy Python-X.X.X\Include\*.h to qrenderdoc\3rdparty\python\include

Copy python-X.X.X-embed-amd64/pythonXX.zip to qrenderdoc\3rdparty\python
Copy python-X.X.X-embed-amd64/pythonXX.dll and _ctypes.pyd to qrenderdoc\3rdparty\python\x64

In qrenderdoc/qrenderdoc_local.vcxproj replace
<Natvis Include="python36.natvis" />
with
<Natvis Include="pythonXX.natvis" />

In qrenderdoc/Code/pyrenderdoc/python.props replace
<PythonMajorMinor>36</PythonMajorMinor>
with
<PythonMajorMinor>XX</PythonMajorMinor>

In qrenderdoc/qrenderdoc.pro replace
python36.lib
with
pythonXX.lib
(twice)

Copy python310.dll in qrenderdoc\3rdparty\python\x64
Manually run the lines of dll2lib.bat in qrenderdoc\3rdparty\python\x64

Right click on the solution, "Retarget Solution" to your latest
Make sure you build the x64 version, not x86

Build pyrenderdoc_module
Copy x64/Release/renderdoc.dll and x64/Release/pymodules/renderdoc.pyd to MapsModelsImporter/blender/bin/win64
```