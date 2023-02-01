REM Set the python version and make shure lib.exe is in the path (e.g. run from the developer command prompt)
set PYTHON_VERSION=python310

dumpbin /EXPORTS %PYTHON_VERSION%.dll > %PYTHON_VERSION%.exports

echo EXPORTS > %PYTHON_VERSION%.def
type %PYTHON_VERSION%.exports >> %PYTHON_VERSION%.def

REM manually edit %PYTHON_VERSION%.def to only keep symbol names

lib /def:%PYTHON_VERSION%.def /machine:x64 /out:%PYTHON_VERSION%.lib
