# Starts the management app at http://127.0.0.1:8765 (local use only).
# First time: python -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r Requirements.txt
param([int] $Port = 8765)

Set-Location $PSScriptRoot
& .\.venv\Scripts\python.exe -m uvicorn App.Main:App --host 127.0.0.1 --port $Port
