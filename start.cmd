@echo off
cd /d "%~dp0"
if exist "dist\ShuangliCompanion\ShuangliCompanion.exe" (
  start "" "dist\ShuangliCompanion\ShuangliCompanion.exe"
) else (
  start "" ".venv\Scripts\pythonw.exe" "run.py"
)
