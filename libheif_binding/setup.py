"""Build the libheif_core SWIG extension.

Usage
-----
    python setup.py build_ext --inplace

or use the provided build.sh helper which also handles the SWIG code-gen step.

Requirements
------------
- SWIG 4.0+          :  swig --version
- libheif dev headers:  brew install libheif   (macOS)
                        apt install libheif-dev (Debian/Ubuntu)
"""

from __future__ import annotations

import os
import subprocess
import sys

from setuptools import Extension, setup


def _find_libheif() -> tuple[list[str], list[str], list[str]]:
    """Return (include_dirs, library_dirs, libraries) for libheif.

    Tries pkg-config first, then falls back to searching common installation
    prefixes.
    """
    # ── pkg-config ────────────────────────────────────────────────────
    try:
        cflags = subprocess.check_output(
            ["pkg-config", "--cflags", "libheif"], text=True
        ).split()
        libs = subprocess.check_output(
            ["pkg-config", "--libs", "libheif"], text=True
        ).split()
        inc_dirs  = [f[2:] for f in cflags if f.startswith("-I")]
        lib_dirs  = [f[2:] for f in libs   if f.startswith("-L")]
        libraries = [f[2:] for f in libs   if f.startswith("-l")]
        if libraries:
            return inc_dirs, lib_dirs, libraries
    except Exception:
        pass

    # ── common installation prefixes ──────────────────────────────────
    prefixes = [
        "/opt/homebrew",   # macOS Apple-silicon Homebrew
        "/usr/local",      # macOS Intel Homebrew / manual install
        "/usr",            # Linux system install
        os.path.expanduser("~/Downloads/libheif/build"),  # local dev build
    ]
    for prefix in prefixes:
        header = os.path.join(prefix, "include", "libheif", "heif.h")
        if os.path.exists(header):
            return (
                [os.path.join(prefix, "include")],
                [os.path.join(prefix, "lib")],
                ["heif"],
            )

    raise RuntimeError(
        "libheif headers not found.  Install with:\n"
        "  macOS : brew install libheif\n"
        "  Linux : apt install libheif-dev\n"
        "  source: https://github.com/strukturag/libheif"
    )


inc_dirs, lib_dirs, libraries = _find_libheif()

ext = Extension(
    "_libheif_core",
    sources=["libheif_core.i"],
    swig_opts=["-python"] + [f"-I{d}" for d in inc_dirs],
    include_dirs=inc_dirs,
    library_dirs=lib_dirs,
    libraries=libraries,
    # Suppress warnings from SWIG-generated C code.
    extra_compile_args=["-Wno-unused-function", "-Wno-strict-prototypes"],
    # Embed the run-path so the .so finds libheif at runtime without
    # setting LD_LIBRARY_PATH / DYLD_LIBRARY_PATH manually.
    runtime_library_dirs=lib_dirs if sys.platform != "darwin" else [],
    extra_link_args=(
        [f"-Wl,-rpath,{d}" for d in lib_dirs] if sys.platform == "darwin" else []
    ),
)

setup(
    name="libheif_core",
    version="0.1.0",
    description="SWIG Python binding for the libheif C API",
    long_description=__doc__,
    ext_modules=[ext],
    py_modules=["libheif_core"],
)
