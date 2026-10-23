
from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension, setup

ROOT = Path(__file__).parent
ENGINE_SOURCE = ROOT / "chronosengine" / "matching_engine.pyx"

extensions = []

if ENGINE_SOURCE.exists():
    extensions.append(
        Extension(
            name="chronosengine.matching_engine",
            sources=[str(ENGINE_SOURCE)],
            language="c++",
            extra_compile_args=["/O2"] if __import__("os").name == "nt" else ["-O3"],
        )
    )

setup(
    name="chronosengine",
    version="0.1.0",
    description="High-performance financial order matching engine",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": 3,
        },
    ),
)

