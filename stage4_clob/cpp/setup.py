"""
setup.py — Build script for order_book_cpp pybind11 C++ extension module.
Supports MSVC and MinGW compilers.

Build commands:
  MSVC:  python stage4_clob/cpp/setup.py build_ext --inplace
  MinGW: python stage4_clob/cpp/setup.py build_ext --compiler=mingw32 --inplace
  Or:    python stage4_clob/cpp/build_mingw.py
"""
import sys
from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension, build_ext

compile_args = ["-O3"] if "--compiler=mingw32" in sys.argv else ["/O2"]

ext_modules = [
    Pybind11Extension(
        "order_book_cpp",
        ["stage4_clob/cpp/order_book_cpp.cpp"],
        cxx_std=14,
        extra_compile_args=compile_args
    ),
]

setup(
    name="order_book_cpp",
    version="1.0",
    author="Antigravity",
    description="C++ PyBind11 OrderBook Extension",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
)
