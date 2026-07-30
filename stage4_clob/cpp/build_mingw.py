"""
build_mingw.py — Standalone build script to compile all C++ extensions using MinGW (g++).
"""
import os
import sys
import subprocess
import sysconfig
import pybind11

def build_all_with_mingw():
    modules = [
        ("stage4_clob/cpp/order_book_cpp.cpp", "order_book_cpp.pyd"),
        ("stage4_clob/cpp/clob_replay_engine.cpp", "clob_replay_engine.pyd"),
        ("stage1_parse/cpp/line_parser_cpp.cpp", "line_parser_cpp.pyd")
    ]

    py_include = sysconfig.get_path("include")
    py_lib_dir = os.path.join(sys.prefix, "libs")
    pybind_include = pybind11.get_include()

    major, minor = sys.version_info[:2]
    py_lib_name = f"python{major}{minor}"

    for cpp_source, output_pyd in modules:
        cmd = [
            "g++", "-O3", "-shared", "-std=c++14",
            f"-I{py_include}",
            f"-I{pybind_include}",
            cpp_source,
            f"-L{py_lib_dir}",
            f"-l{py_lib_name}",
            "-o", output_pyd
        ]
        print(f"[MinGW BUILD] Compiling {output_pyd}...")
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"[SUCCESS] Built {output_pyd}")
        except FileNotFoundError:
            print("[ERROR] 'g++' not found in system PATH. Ensure MinGW-w64 is installed.")
            break
        except subprocess.CalledProcessError as e:
            print(f"[FAIL] {output_pyd} compilation failed:\n{e.stderr}")

if __name__ == "__main__":
    build_all_with_mingw()
