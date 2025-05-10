#!/usr/bin/env python3

import platform
from enum import StrEnum
from pathlib import Path

SOKOL_SHDC_PATH = Path("sokol-shdc")
SOKOL_PATH = Path("source/sokol")


class Sys(StrEnum):
    win32 = "Windows"
    osx = "Darwin"
    linux = "Linux"

    def dll(self):
        match self:
            case Sys.win32:
                return ".dll"
            case Sys.osx:
                return ".dylib"
            case Sys.linux:
                return ".so"

    def executable(self):
        if self is Sys.win32:
            return ".exe"

        return ".bin"

    def is_arm64(self):
        arch = platform.machine()
        return "arm64" in arch or "aarch64" in arch

    def target_dir(self):
        if SYSTEM is Sys.win32:
            return self.name
        return f"{self.name}{'_arm64' if self.is_arm64() else ''}"

    def shader_compile_cmd(self):
        match SYSTEM:
            case Sys.win32:
                slang = "hlsl5"
                executable = "sokol-shdc.exe"
            case Sys.linux:
                slang = "glsl430"
                executable = "sokol-shdc"
            case Sys.osx:
                slang = "glsl410" if args.gl else "metal_macos"
                executable = "sokol-shdc"

        if args.web:
            slang = "glsl300es"

        path = SOKOL_SHDC_PATH / self.target_dir() / executable
        assert path.exists(), (
            "Could not find shader compiler. Try running this script with update-sokol parameter"
        )
        return [str(path), "-f", "sokol_odin", "-l", slang]


sys = platform.system()
try:
    SYSTEM = Sys(sys)
except KeyError as e:
    msg = f"Unsupported platform '{sys}'"
    raise Exception(msg) from e

import argparse
import functools

args_parser = argparse.ArgumentParser(
    prog="build.py",
    description="Odin + Sokol Hot Reload Template build script.",
    epilog="Made by Karl Zylinski.",
)
bool_flag = functools.partial(args_parser.add_argument, action="store_true")


bool_flag(
    "-hot-reload",
    help=(
        "Build hot reload game DLL."
        "Also builds executable if game not already running."
        "This is the default."
    ),
)
bool_flag(
    "-release",
    help=(
        "Build release game executable."
        "Note: Deletes everything in the 'build/release' directory to make sure you get a clean release."
    ),
)
bool_flag(
    "-update-sokol",
    help=(
        "Download latest Sokol bindings and latest Sokol shader compiler."
        f"Happens automatically when the '{SOKOL_SHDC_PATH}' and '{SOKOL_PATH}' directories are missing."
        f"Note: Deletes everything in '{SOKOL_SHDC_PATH}' and '{SOKOL_PATH}' directories."
        "Also causes -compile-sokol to happen."
    ),
)
bool_flag(
    "-compile-sokol",
    help=(
        "Compile Sokol C libraries for the current platform."
        "Also compile web (WASM) libraries if emscripten is found (optional)."
        "Use -emsdk-path to point out emscripten SDK if not in PATH."
    ),
)
bool_flag("-run", help="Run the executable after compiling it.")
bool_flag(
    "-debug",
    help=(
        "Create debuggable binaries."
        "Makes it possible to debug hot reload and release build in a debugger."
        "For the web build it means that better error messages are printed to console."
        "Debug mode comes with a performance penalty."
    ),
)
bool_flag("-no-shader-compile", help="Don't compile shaders.")
bool_flag(
    "-web",
    help="Build web release. Make sure emscripten (emcc) is in your PATH or use -emsdk-path flag to specify where it lives.",
)
args_parser.add_argument(
    "-emsdk-path",
    help=(
        "Path to where you have emscripten installed."
        "Should be the root directory of your emscripten installation."
        "Not necessary if emscripten is in your PATH."
        "Can be used with both -web and -compile-sokol (the latter needs it when building the Sokol web (WASM) libraries)."
    ),
)
bool_flag(
    "-gl",
    help=(
        "Force OpenGL Sokol backend."
        "Useful on some older computers, for example old MacBooks that don't support Metal."
    ),
)

args = args_parser.parse_args()

if sum([args.hot_reload, args.release, args.web]) > 1:
    print("Can only use one of: -hot-reload, -release and -web.")
    exit(1)

import shutil
import subprocess
import urllib.request
import zipfile
from os import chdir, chmod, environ


def main():
    if args.update_sokol or not (
        # Looks like a fresh setup, no sokol anywhere! Trigger automatic update.
        SOKOL_PATH.exists() or SOKOL_SHDC_PATH.exists()
    ):
        update_sokol()
        compile_sokol()
    elif args.compile_sokol:
        compile_sokol()

    if not args.no_shader_compile:
        build_shaders()

    if not args.web:
        if args.release:
            exe_path = build_release()
        else:
            exe_path = build_hot_reload()

        if exe_path and args.run:
            print("Starting " + exe_path)
            subprocess.Popen([exe_path])
    else:
        build_web()


def build_shaders():
    print("Building shaders...")
    shdc = SYSTEM.shader_compile_cmd()

    for s in [f for f in Path("source").iterdir() if f.suffix == ".glsl"]:
        out = (s.parent / f"gen__{s.name}").with_suffix(".odin")

        execute(shdc + ["-i", str(s), "-o", str(out)])


def build_hot_reload():
    out_dir = Path("build/hot_reload")
    out_dir.mkdir(parents=True, exist_ok=True)

    exe = "game_hot_reload" + SYSTEM.executable()
    dll_final_name = (out_dir / "game").with_suffix(SYSTEM.dll())

    if SYSTEM is not Sys.win32:
        dll = (out_dir / "game_tmp").with_suffix(SYSTEM.dll())
    else:
        dll = dll_final_name

    game_running = process_exists(exe)

    if SYSTEM is Sys.win32:
        pdb_dir = out_dir / "game_pdbs"
        pdb_number = 0

        if not game_running:
            for f in out_dir.iterdir():
                if f.suffix == ".dll":
                    f.unlink()

            if pdb_dir.exists():
                shutil.rmtree(pdb_dir)

        if not pdb_dir.exists():
            pdb_dir.mkdir(parents=True)
        else:
            prefix = len("game_")
            if pdbs := [
                int(f.stem[prefix:]) for f in pdb_dir.iterdir() if f.suffix == ".pdb"
            ]:
                pdb_number = max(pdbs)
            else:
                pdb_number = 0

        # On windows we make sure the PDB name for the DLL is unique on each
        # build. This makes debugging work properly.
        dll_extra_args = [f"-pdb-name:{pdb_dir / f'game_{pdb_number + 1}'}.pdb"]
    else:
        dll_extra_args = []

    if args.debug:
        dll_extra_args.append("-debug")

    if args.gl:
        dll_extra_args.append("-define:SOKOL_USE_GL=true")

    print(f"Building {dll_final_name}...")
    execute(
        [
            "odin",
            "build",
            "source",
            "-define:SOKOL_DLL=true",
            "-build-mode:dll",
            f"-out:{dll}",
        ]
        + dll_extra_args
    )

    if SYSTEM is not Sys.win32:
        dll.rename(dll_final_name)

    if game_running:
        print("Hot reloading...")

        # Hot reloading means the running executable will see the new dll.
        # So we can just return empty string here. This makes sure that the main
        # function does not try to run the executable, even if `run` is specified.
        return ""

    if SYSTEM is Sys.win32:
        exe_extra_args = [f"-pdb-name:{out_dir / 'main_hot_reload.pdb'}"]
    else:
        exe_extra_args = []

    if args.debug:
        exe_extra_args.append("-debug")

    if args.gl:
        exe_extra_args.append("-define:SOKOL_USE_GL=true")

    print(f"Building {exe}...")
    execute(
        [
            "odin",
            "build",
            "source/main_hot_reload",
            "-strict-style",
            "-define:SOKOL_DLL=true",
            "-vet",
            f"-out:{exe}",
        ]
        + exe_extra_args
    )

    if SYSTEM is Sys.win32:
        dll_name = Path(
            f"sokol_dll_windows_x64_d3d11_{'debug' if args.debug else 'release'}.dll"
        )

        if not dll_name.exists():
            print("Copying %s" % dll_name)
            shutil.copyfile(SOKOL_PATH / dll_name, dll_name)

    if SYSTEM is Sys.osx:
        dylib_folder = SOKOL_PATH / "dylib"

        if not dylib_folder.exists():
            print(
                "Dynamic libraries for OSX don't seem to be built. Please re-run 'build.py -compile-sokol'."
            )
            exit(1)

        out_dir = Path("dylib")
        out_dir.mkdir(exist_ok=True)

        for src in [f for f in dylib_folder.iterdir() if not f.is_dir()]:
            dest = out_dir / src.name

            if not dest.exists() or dest.stat().st_size != src.stat().st_size:
                print("Copying %s to %s" % (src, dest))
                shutil.copyfile(src, dest)

    return "./" + exe


def build_release():
    out_dir = Path("build/release")

    if out_dir.exists():
        shutil.rmtree(out_dir)

    out_dir.mkdir(parents=True)

    exe = (out_dir / "game_release").with_suffix(SYSTEM.executable())

    print(f"Building {exe}...")

    if not args.debug:
        extra_args = ["-no-bounds-check", "-o:speed"]

        if SYSTEM is Sys.win32:
            extra_args.append("-subsystem:windows")
    else:
        extra_args = ["-debug"]

    if args.gl:
        extra_args.append("-define:SOKOL_USE_GL=true")

    execute(
        ["odin", "build", "source/main_release", f"-out:{exe}", "-strict-style", "-vet"]
        + extra_args
    )
    shutil.copytree("assets", out_dir / "assets")

    return str(exe)


def build_web():
    if emsdk_env := emscripten_env():
        emcc_prefix = emsdk_env + ["&&"]
    else:
        emcc_prefix = []

    if shutil.which("emcc") is None:
        print(
            "Could not find emcc. Try providing emscripten SDK path using '-emsdk-path PATH' or run the emsdk_env script inside the emscripten folder before running this script."
        )
        exit(1)

    out_dir = Path("build/web")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.debug:
        odin_extra_args = ["-debug"]
    else:
        odin_extra_args = []

    print("Building js_wasm32 game object...")
    execute(
        [
            "odin",
            "build",
            "source/main_web",
            "-target:js_wasm32",
            "-build-mode:obj",
            "-vet",
            "-strict-style",
            f"-out:{out_dir / 'game'}",
            "%s",
        ]
        + odin_extra_args
    )
    odin_path = Path(
        execute(["odin", "root"], shell=True, capture_output=True, text=True)
    )

    shutil.copyfile(
        odin_path / "core/sys/wasm/js/odin.js",
        out_dir / "odin.js",
    )

    # -g is the emcc debug flag, it makes the errors in the browser console better.
    if args.debug:
        build_flags = ["-g"]
    else:
        build_flags = []

    print(f"Building web application using emscripten to {out_dir}...")

    # Note --preload-file assets, this bakes in the whole assets directory into the web build.
    wasm_lib_suffix = "debug.a" if args.debug else "release.a"
    execute(
        emcc_prefix
        + ["emcc"]
        + build_flags
        + ["-o", str(out_dir / "index.html")]
        + [str(out_dir / "game.wasm.o")]
        + [
            str(SOKOL_PATH / (f + wasm_lib_suffix))
            for f in (
                "glue/sokol_glue_wasm_gl_"
                "gfx/sokol_gfx_wasm_gl_"
                "shape/sokol_shape_wasm_gl_"
                "log/sokol_log_wasm_gl_"
                "gl/sokol_gl_wasm_gl_"
            )
        ]
        + [
            "--shell-file",
            "source/web/index_template.html",
            "--preload-file",
            "assets",
            "-sWASM_BIGINT",
            "-sWARN_ON_UNDEFINED_SYMBOLS=0",
            "-sMAX_WEBGL_VERSION=2",
            "-sASSERTIONS",
        ]
    )

    # Not needed
    (out_dir / "game.wasm.o").unlink()


def execute(args: list[str], **kwargs):
    print("Running", args)
    res = subprocess.run(args, **kwargs)
    if res.returncode != 0:
        print("Failed running:", args, res.stdout, res.stderr)
        exit(1)
    return res.stdout


def update_sokol():
    def update_sokol_bindings():
        SOKOL_ZIP_URL = (
            "https://github.com/floooh/sokol-odin/archive/refs/heads/main.zip"
        )

        if SOKOL_PATH.exists():
            shutil.rmtree(SOKOL_PATH)

        temp_zip = Path("sokol-temp.zip")
        temp_folder = Path("sokol-temp")
        print(f"Downloading Sokol Odin bindings to directory {SOKOL_PATH}...")
        urllib.request.urlretrieve(SOKOL_ZIP_URL, temp_zip)

        with zipfile.ZipFile(temp_zip) as zip_file:
            zip_file.extractall(temp_folder)
            shutil.copytree(temp_folder / "sokol-odin-main/sokol", SOKOL_PATH)

        temp_zip.unlink()
        shutil.rmtree(temp_folder)

    def update_sokol_shdc():
        if SOKOL_SHDC_PATH.exists():
            shutil.rmtree(SOKOL_SHDC_PATH)

        TOOLS_ZIP_URL = (
            "https://github.com/floooh/sokol-tools-bin/archive/refs/heads/master.zip"
        )
        temp_zip = Path("sokol-tools-temp.zip")
        temp_folder = Path("sokol-tools-temp")

        print("Downloading Sokol Shader Compiler to directory sokol-shdc...")
        urllib.request.urlretrieve(TOOLS_ZIP_URL, temp_zip)

        with zipfile.ZipFile(temp_zip) as zip_file:
            zip_file.extractall(temp_folder)
            shutil.copytree(temp_folder / "sokol-tools-bin-master/bin", SOKOL_SHDC_PATH)

        if SYSTEM is not Sys.win32:
            chmod(SOKOL_SHDC_PATH / SYSTEM.target_dir() / "sokol-shdc", 755)

        temp_zip.unlink()
        shutil.rmtree(temp_folder)

    update_sokol_bindings()
    update_sokol_shdc()


def compile_sokol():
    owd = Path.cwd()
    chdir(SOKOL_PATH)

    emsdk_env = emscripten_env()

    print("Building Sokol C libraries...")

    match SYSTEM:
        case Sys.win32:
            if shutil.which("cl.exe") is not None:
                execute(["build_clibs_windows.cmd"], shell=True)
            else:
                print(
                    "cl.exe not in PATH. Try re-running build.py with flag -compile-sokol from a Visual Studio command prompt."
                )
            if emsdk_env or shutil.which("emcc.bat"):
                execute(emsdk_env + ["build_clibs_wasm.bat"], shell=True)
            else:
                print(
                    "emcc not in PATH, skipping building of WASM libs. Tip: You can also use -emsdk-path to specify where emscripten lives."
                )

        case Sys.linux:
            execute(["bash", "build_clibs_linux.sh"])

            if emsdk_env or shutil.which("emcc"):
                execute(emsdk_env + ["bash", "build_clibs_wasm.sh"])
            else:
                print(
                    "emcc not in PATH, skipping building of WASM libs. Tip: You can also use -emsdk-path to specify where emscripten lives."
                )
        case Sys.osx:
            execute(["bash", "build_clibs_macos.sh"])
            execute(["bash", "build_clibs_macos_dylib.sh"])

            if emsdk_env or shutil.which("emcc"):
                execute(emsdk_env + ["bash", "build_clibs_wasm.sh"])
            else:
                print(
                    "emcc not in PATH, skipping building of WASM libs. Tip: You can also use -emsdk-path to specify where emscripten lives."
                )

    chdir(owd)


def emscripten_env():
    if args.emsdk_path is None:
        return []

    if SYSTEM is Sys.win32:
        envcmd_path = Path(args.emsdk_path) / "emsdk_env.bat"
    else:
        environ["EMSDK_QUIET"] = "1"
        envcmd_path = Path("source") / args.emsdk_path / "emsdk_env.sh"
    return [str(envcmd_path.resolve()), "&&"]


def process_exists(process_name):
    if SYSTEM is Sys.win32:
        call = "TASKLIST", "/NH", "/FI", "imagename eq %s" % process_name
        return process_name in str(subprocess.check_output(call))
    out = subprocess.run(
        ["pgrep", "-f", process_name], capture_output=True, text=True
    ).stdout
    return out != ""


print = functools.partial(print, flush=True)

main()
