@echo off
setlocal
where uv >nul 2>nul
if not errorlevel 1 (
  uv run --frozen --project "%~dp0." python "%~dp0zine.py" %*
  exit /b
)
if not exist "%~dp0.venv\Scripts\python.exe" (
  py -3 -m venv "%~dp0.venv" || exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -c "import PIL, pypdfium2, reportlab, filelock, cv2, numpy" 2>nul
if errorlevel 1 (
  "%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt" || exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0zine.py" %*
