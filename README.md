∩╗┐# ChronosEngine

ChronosEngine is a high-performance financial order-matching project built
with Python, Cython, C++, and memory-mapped inter-process communication (IPC).

It explores low-latency order processing, matching-engine performance,
shared-memory communication, and trade persistence.

## Features

- Cython/C++ order-matching engine.
- Memory-mapped circular order buffer.
- Outbound matched-trade ring buffer.
- Binary order and trade record schemas.
- Graceful shutdown signaling across processes.
- Buffer-capacity watermark monitoring and consumer-lag metrics.
- IPC round-trip latency benchmarking.
- SQLite-based trade persistence and asynchronous ingestion.
- Latency monitoring and terminal dashboard components.

## Project structure

```text
ChronosEngine/
Γö£ΓöÇΓöÇ chronosengine/
Γöé   Γö£ΓöÇΓöÇ matching_engine.pyx
Γöé   Γö£ΓöÇΓöÇ matching_engine.pxd
Γöé   Γö£ΓöÇΓöÇ production_pipeline.py
Γöé   Γö£ΓöÇΓöÇ trade_consumer.py
Γöé   Γö£ΓöÇΓöÇ trade_ledger.py
Γöé   ΓööΓöÇΓöÇ ui/
Γö£ΓöÇΓöÇ docs/
Γöé   Γö£ΓöÇΓöÇ build_guide.md
Γöé   Γö£ΓöÇΓöÇ ipc_design.md
Γöé   Γö£ΓöÇΓöÇ sim_runbook.md
Γöé   ΓööΓöÇΓöÇ system_architecture_zero_copy_ipc.md
Γö£ΓöÇΓöÇ mmap_ringbuffer.py
Γö£ΓöÇΓöÇ mmap_trade_ringbuffer.py
Γö£ΓöÇΓöÇ order_schema.py
Γö£ΓöÇΓöÇ trade_schema.py
Γö£ΓöÇΓöÇ shutdown_signal.py
Γö£ΓöÇΓöÇ setup.py
Γö£ΓöÇΓöÇ pyproject.toml
ΓööΓöÇΓöÇ README.md
```

## Requirements

- 64-bit Python.
- Git.
- Microsoft Visual C++ Build Tools with x64 compiler support.
- Windows SDK.

The current IPC implementation uses Windows-specific file-locking
functionality. Windows is the primary documented environment.

See [Build and Installation Guide](docs/build_guide.md) for compiler setup
and installation instructions.

## Installation

Clone the repository:

```powershell
git clone https://github.com/pareddysruthi46-crypto/ChronosEngine.git
cd ChronosEngine
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install the project:

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

The build system installs its declared build requirements, including Cython.
The project runtime dependency `psutil>=7.0.0` is declared in `setup.py`.

The editable installation builds the native Cython matching-engine extension.

## Verify installation

```powershell
python -c "import chronosengine.matching_engine; print('ChronosEngine installed successfully')"
```

## Run tests

Run the test suite from the repository root:

```powershell
python -m pytest -q
```

To run an individual IPC test:

```powershell
python -m pytest -q test_ringbuffer.py
```

## Documentation

- [Build and Installation Guide](docs/build_guide.md)
- [IPC Design](docs/ipc_design.md)
- [Simulation Runbook](docs/sim_runbook.md)
- [System Architecture](docs/system_architecture_zero_copy_ipc.md)

## Development notes

- Build the complete matching-engine project from the `main` branch.
- Use a compatible 64-bit Python interpreter and Visual C++ toolchain.
- Rebuild native extensions after changing Python versions or platforms.
- Do not commit generated binaries, temporary databases, or Python cache files.
- Run relevant tests before submitting changes.
