# Legacy Python application

These are the original EXIFexit Python sources, retained for reference and compatibility. Active .NET development lives in the top-level `src` directory.

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r legacy/python/requirements.txt
.\.venv\Scripts\python legacy/python/exifexit.py
```

`EXIFexit.bat` in the repository root remains a compatibility launcher using Python on PATH. The legacy dependencies use minimum-version constraints and are not a reproducible lockfile.
