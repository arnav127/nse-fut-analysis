"""
setup.py — PyBind11 C++ module builder supporting MinGW (g++) and MSVC.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# If --compiler=mingw32 or mingw is passed, run build_all_with_mingw
if any("mingw" in arg.lower() for arg in sys.argv):
    from stage4_clob.cpp.build_mingw import build_all_with_mingw
    build_all_with_mingw()
    sys.exit(0)

from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension, build_ext

compile_args = ["-O3", "-std=c++17"] if "--compiler=mingw32" in sys.argv else ["/O2", "/std:c++17"]

ext_modules = [
    Pybind11Extension(
        "order_book_cpp",
        ["stage4_clob/cpp/order_book_cpp.cpp"],
        cxx_std=17,
        extra_compile_args=compile_args
    ),
    Pybind11Extension(
        "clob_replay_engine",
        ["stage4_clob/cpp/clob_replay_engine.cpp"],
        cxx_std=17,
        extra_compile_args=compile_args
    ),
]

setup(
    name="nse_cpp_accelerators",
    version="1.0",
    description="C++ PyBind11 Microstructure Accelerators",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
)
