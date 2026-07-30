"""
build_mingw.py — Standalone build script to compile C++ OrderBook extension using MinGW (g++).

Usage:
  python stage4_clob/cpp/build_mingw.py
"""
import os
import sys
import subprocess
import sysconfig
import pybind11

def build_with_mingw():
    cpp_source = r"stage4_clob/cpp/order_book_cpp.cpp"
    output_pyd = "order_book_cpp.pyd"

    # Get Python & PyBind11 include dirs
    py_include = sysconfig.get_path("include")
    py_lib_dir = os.path.join(sys.prefix, "libs")
    pybind_include = pybind11.get_include()

    # Determine Python library name (e.g. python313.lib or libpython313.a)
    major, minor = sys.version_info[:2]
    py_lib_name = f"python{major}{minor}"

    cmd = [
        "g++", "-O3", "-shared", "-std=c++14",
        f"-I{py_include}",
        f"-I{pybind_include}",
        cpp_source,
        f"-L{py_lib_dir}",
        f"-l{py_lib_name}",
        "-o", output_pyd
    ]

    print(f"[MinGW BUILD] Executing: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"[SUCCESS] Compiled {output_pyd} with MinGW g++!")
    except FileNotFoundError:
        print("[ERROR] 'g++' not found in system PATH. Please ensure MinGW-w64 is installed and added to PATH.")
    except subprocess.CalledProcessError as e:
        print(f"[FAIL] Compilation failed:\n{e.stderr}")

if __name__ == "__main__":
    build_with_mingw()
