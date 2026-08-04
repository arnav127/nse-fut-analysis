"""
build_mingw.py — Standalone build script to compile C++ extensions using MinGW (g++).
"""
import os
import sys
import shutil
import subprocess
import sysconfig
from pathlib import Path
import pybind11

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def find_gpp_compiler():
    gpp_path = shutil.which("g++")
    if gpp_path:
        return gpp_path
    
    known_paths = [
        r"C:\msys64\ucrt64\bin\g++.exe",
        r"C:\msys64\mingw64\bin\g++.exe",
        r"C:\msys64\usr\bin\g++.exe",
        r"C:\MinGW\bin\g++.exe",
        r"C:\tools\mingw64\bin\g++.exe",
    ]
    for path in known_paths:
        if os.path.exists(path):
            compiler_dir = str(Path(path).parent)
            if compiler_dir not in os.environ["PATH"]:
                os.environ["PATH"] = compiler_dir + os.pathsep + os.environ["PATH"]
            return path
    return "g++"

def build_all_with_mingw():
    gpp_exe = find_gpp_compiler()
    print(f"[MinGW BUILD] Using g++ compiler executable: {gpp_exe}")

    modules = [
        (PROJECT_ROOT / "stage4_clob" / "cpp" / "order_book_cpp.cpp", PROJECT_ROOT / "order_book_cpp.pyd"),
        (PROJECT_ROOT / "stage4_clob" / "cpp" / "clob_replay_engine.cpp", PROJECT_ROOT / "clob_replay_engine.pyd"),
    ]

    py_include = sysconfig.get_path("include")
    py_lib_dir = os.path.join(sys.prefix, "libs")
    pybind_include = pybind11.get_include()

    major, minor = sys.version_info[:2]
    py_lib_name = f"python{major}{minor}"

    for cpp_source, output_pyd in modules:
        cpp_source_str = str(cpp_source)
        output_pyd_str = str(output_pyd)

        cmd = [
            gpp_exe, "-O3", "-shared", "-std=c++17",
            f"-I{py_include}",
            f"-I{pybind_include}",
            cpp_source_str,
            f"-L{py_lib_dir}",
            f"-l{py_lib_name}",
            "-o", output_pyd_str
        ]
        print(f"[MinGW BUILD] Compiling {output_pyd.name} from {cpp_source}...")
        try:
            res = subprocess.run(cmd, check=True, capture_output=True, text=True, env=os.environ)
            print(f"[SUCCESS] Built {output_pyd.name} -> {output_pyd_str}")
        except FileNotFoundError:
            print(f"[ERROR] Compiler '{gpp_exe}' not found. Ensure MinGW g++ is installed.")
            break
        except subprocess.CalledProcessError as e:
            print(f"[FAIL] {output_pyd.name} compilation failed:\n{e.stderr}\n{e.stdout}")

if __name__ == "__main__":
    build_all_with_mingw()
