∩╗┐# ChronosEngine Build and Installation Guide

## 1. Overview

ChronosEngine is a financial order-matching project built using Python,
Cython, C++, and memory-mapped inter-process communication (IPC).

The matching engine is compiled into a native C++ extension using Cython
and setuptools. The IPC components provide shared-memory communication
between processes.

Windows is the primary documented environment because the current IPC
implementation uses Windows-specific file-locking functionality.

## 2. Prerequisites

Install the following software:

- 64-bit Python.
- Git.
- Microsoft Visual Studio Build Tools.
- Visual C++ x64 compiler tools.
- Windows SDK.

The Visual Studio installation must include the C++ build tools workload.

## 3. Verify the compiler

Open the x64 Native Tools Command Prompt for Visual Studio or Visual Studio
Developer PowerShell.

Run:

```powershell
where.exe cl
cl
```

The compiler should be available through the developer environment.

## 4. Clone the repository

```powershell
git clone https://github.com/pareddysruthi46-crypto/ChronosEngine.git
cd ChronosEngine
```

Use the main branch for the complete project build. The IPC feature branch
does not contain all matching-engine source files.

Confirm that these files exist:

- `setup.py`
- `pyproject.toml`
- `chronosengine/matching_engine.pyx`
- `chronosengine/matching_engine.pxd`

## 5. Create a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks virtual-environment activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

## 6. Install the project

Upgrade the packaging tools:

```powershell
python -m pip install --upgrade pip setuptools wheel
```

Install the project in editable mode:

```powershell
python -m pip install -e .
```

The build system obtains its build requirements from `pyproject.toml`.
These include setuptools, wheel, and Cython.

The runtime dependency `psutil>=7.0.0` is declared in `setup.py`.

The installation compiles the Cython matching-engine extension.

## 7. Verify the installation

Run:

```powershell
python -c "import chronosengine.matching_engine; print('Matching engine import successful')"
```

A successful import confirms that Python can load the compiled extension.

## 8. Run tests

Run the test suite from the repository root:

```powershell
python -m pytest -q
```

To run individual IPC tests:

```powershell
python -m pytest -q test_ringbuffer.py
python -m pytest -q test_atomic_sequence.py
python -m pytest -q test_mmap_trade_ringbuffer.py
python -m pytest -q test_shutdown_cross_process.py
```

## 9. Troubleshooting

### Microsoft C++ compiler not found

Open the Visual Studio x64 Native Tools Command Prompt and retry.

Verify that the Visual C++ x64 compiler tools and Windows SDK are installed.

### Cython extension import fails

Check that the matching-engine source files exist:

- `chronosengine/matching_engine.pyx`
- `chronosengine/matching_engine.pxd`

Then rebuild the project:

```powershell
python -m pip install -e . --force-reinstall
```

### Build fails after changing Python versions

Native extension files are specific to the Python version and platform.
Use the intended Python interpreter and rebuild the extension.

### Generated files appear in Git status

Generated `.cpp`, `.pyd`, build directories, and Python cache files should
not be committed as source files unless explicitly required by the project.

## 10. Development notes

- Build the complete matching-engine project from `main`.
- Use a compatible 64-bit Python interpreter and Visual C++ toolchain.
- Rebuild native extensions after changing Python versions.
- Run relevant tests before submitting changes.
- Consult `docs/ipc_design.md` for IPC implementation details.
