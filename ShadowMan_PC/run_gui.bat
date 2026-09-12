@echo off
cd /d "%~dp0"
python rsc_gui.py
if errorlevel 1 pause
