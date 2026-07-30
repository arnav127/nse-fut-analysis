"""
setup.py — Multi-module build script for C++ PyBind11 extensions:
- order_book_cpp
- clob_replay_engine
- line_parser_cpp
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
    Pybind11Extension(
        "clob_replay_engine",
        ["stage4_clob/cpp/clob_replay_engine.cpp"],
        cxx_std=14,
        extra_compile_args=compile_args
    ),
    Pybind11Extension(
        "line_parser_cpp",
        ["stage1_parse/cpp/line_parser_cpp.cpp"],
        cxx_std=14,
        extra_compile_args=compile_args
    ),
]

setup(
    name="nse_cpp_accelerators",
    version="1.0",
    author="Antigravity",
    description="C++ PyBind11 Microstructure Accelerators",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
)
