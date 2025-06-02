#!/usr/bin/env python3

import argparse

args_parser = argparse.ArgumentParser(
	prog = "build.py",
	description = "Odin + Sokol Hot Reload Template build script.",
	epilog = "Made by Karl Zylinski.")

args_parser.add_argument("-hot-reload",        action="store_true",   help="Build hot reload game DLL. Also builds executable if game not already running. If the game is running, it will hot reload the game DLL.")
args_parser.add_argument("-release",           action="store_true",   help="Build release game executable. Note: Deletes everything in the 'build/release' directory to make sure you get a clean release.")
args_parser.add_argument("-update-sokol",      action="store_true",   help="Download latest Sokol bindings and latest Sokol shader compiler. Happens automatically when the 'sokol-shdc' and 'source/sokol' directories are missing. Note: Deletes everything in 'sokol-shdc' and 'source/sokol' directories. Also causes -compile-sokol to happen.")
args_parser.add_argument("-compile-sokol",     action="store_true",   help="Compile Sokol C libraries for the current platform. Also compile web (WASM) libraries if emscripten is found (optional). Use -emsdk-path to point out emscripten SDK if not in PATH.")
args_parser.add_argument("-run",               action="store_true",   help="Run the executable after compiling it.")
args_parser.add_argument("-debug",             action="store_true",   help="Create debuggable binaries. Makes it possible to debug hot reload and release build in a debugger. For the web build it means that better error messages are printed to console. Debug mode comes with a performance penalty.")
args_parser.add_argument("-no-shader-compile", action="store_true",   help="Don't compile shaders.")
args_parser.add_argument("-web",               action="store_true",   help="Build web release. Make sure emscripten (emcc) is in your PATH or use -emsdk-path flag to specify where it lives.")
args_parser.add_argument("-emsdk-path",                               help="Path to where you have emscripten installed. Should be the root directory of your emscripten installation. Not necessary if emscripten is in your PATH. Can be used with both -web and -compile-sokol (the latter needs it when building the Sokol web (WASM) libraries).")
args_parser.add_argument("-gl",                action="store_true",   help="Force OpenGL Sokol backend. Useful on some older computers, for example old MacBooks that don't support Metal.")

import urllib.request
import os
import zipfile
import shutil
import platform
import subprocess
import functools
from enum import Enum

args = args_parser.parse_args()

num_build_modes = 0
if args.hot_reload:
	num_build_modes += 1
if args.release:
	num_build_modes += 1
if args.web:
	num_build_modes += 1

if num_build_modes > 1:
	print("Can only use one of: -hot-reload, -release and -web.")
	exit(1)
elif num_build_modes == 0 and not args.update_sokol and not args.compile_sokol:
	print("You must use one of: -hot-reload, -release, -web, -update-sokol or -compile-sokol.")
	exit(1)

SYSTEM = platform.system()
IS_WINDOWS = SYSTEM == "Windows"
IS_OSX = SYSTEM == "Darwin"
IS_LINUX = SYSTEM == "Linux"

assert IS_WINDOWS or IS_OSX or IS_LINUX, "Unsupported platform."

def main():
	do_update = args.update_sokol

	# Looks like a fresh setup, no sokol anywhere! Trigger automatic update.
	if not os.path.exists(SOKOL_PATH) and not os.path.exists(SOKOL_SHDC_PATH):
		do_update = True

	if do_update:
		update_sokol()

	do_compile = do_update or args.compile_sokol

	if do_compile:
		compile_sokol()

	if not args.no_shader_compile:
		build_shaders()

	exe_path = ""
	
	if args.release:
		exe_path = build_release()
	elif args.web:
		exe_path = build_web()
	elif args.hot_reload:
		exe_path = build_hot_reload()
	
	if exe_path != "" and args.run:
		print("Starting " + exe_path)
		subprocess.Popen(exe_path)

def build_shaders():
	print("Building shaders...")
	shdc = get_shader_compiler()

	shaders = []

	for root, dirs, files in os.walk("source"):
		for file in files:
			if file.endswith(".glsl"):
				shaders.append(os.path.join(root, file))

	for s in shaders:
		out_dir = os.path.dirname(s)
		out_filename = os.path.basename(s)
		out = out_dir + "/gen__" + (out_filename.removesuffix("glsl") + "odin")

		langs = ""

		if args.web:
			langs = "glsl300es"
		elif IS_WINDOWS:
			langs = "hlsl5"
		elif IS_LINUX:
			langs = "glsl430"
		elif IS_OSX:
			langs = "glsl410" if args.gl else "metal_macos"

		execute(shdc + " -i %s -o %s -l %s -f sokol_odin" % (s, out, langs))

def get_shader_compiler():
	path = ""

	arch = platform.machine()

	if IS_WINDOWS:
		path = "sokol-shdc\\win32\\sokol-shdc.exe"
	elif IS_LINUX:
		if "arm64" in arch or "aarch64" in arch:
			path = "sokol-shdc/linux_arm64/sokol-shdc"
		else:
			path = "sokol-shdc/linux/sokol-shdc"
	elif IS_OSX:
		if "arm64" in arch or "aarch64" in arch:
			path = "sokol-shdc/osx_arm64/sokol-shdc"
		else:
			path = "sokol-shdc/osx/sokol-shdc"

	assert os.path.exists(path), "Could not find shader compiler. Try running this script with update-sokol parameter"
	return path

path_join = os.path.join


def build_hot_reload():
	out_dir = "build/hot_reload"

	if not os.path.exists(out_dir):
		make_dirs(out_dir)

	exe = "game_hot_reload" + executable_extension()
	dll_final_name = out_dir + "/game" + dll_extension()
	dll = dll_final_name

	if IS_LINUX or IS_OSX:
		dll = out_dir + "/game_tmp" + dll_extension()

	# Only used on windows
	pdb_dir = out_dir + "/game_pdbs"
	pdb_number = 0
	
	dll_extra_args = ""

	if args.debug:
		dll_extra_args += " -debug"

	if args.gl:
		dll_extra_args += " -define:SOKOL_USE_GL=true"

	game_running = process_exists(exe)

	if IS_WINDOWS:
		if not game_running:
			out_dir_files = os.listdir(out_dir)

			for f in out_dir_files:
				if f.endswith(".dll"):
					os.remove(os.path.join(out_dir, f))

			if os.path.exists(pdb_dir):
				shutil.rmtree(pdb_dir)

		if not os.path.exists(pdb_dir):
			make_dirs(pdb_dir)
		else:
			pdb_files = os.listdir(pdb_dir)

			for f in pdb_files:
				if f.endswith(".pdb"):
					n = int(f.removesuffix(".pdb").removeprefix("game_"))

					if n > pdb_number:
						pdb_number = n

		# On windows we make sure the PDB name for the DLL is unique on each
		# build. This makes debugging work properly.
		dll_extra_args += " -pdb-name:%s/game_%i.pdb" % (pdb_dir, pdb_number + 1)

	print("Building " + dll_final_name + "...")
	execute("odin build source -define:SOKOL_DLL=true -build-mode:dll -out:%s %s" % (dll, dll_extra_args))

	if IS_LINUX or IS_OSX:
		os.rename(dll, dll_final_name)

	if game_running:
		print("Hot reloading...")

		# Hot reloading means the running executable will see the new dll.
		# So we can just return empty string here. This makes sure that the main
		# function does not try to run the executable, even if `run` is specified.
		return ""

	exe_extra_args = ""

	if IS_WINDOWS:
		exe_extra_args += " -pdb-name:%s/main_hot_reload.pdb" % out_dir

	if args.debug:
		exe_extra_args += " -debug"

	if args.gl:
		exe_extra_args += " -define:SOKOL_USE_GL=true"

	print("Building " + exe + "...")
	execute("odin build source/main_hot_reload -strict-style -define:SOKOL_DLL=true -vet -out:%s %s" % (exe, exe_extra_args))

	if IS_WINDOWS:
		gfxapi = "gl" if args.gl else "d3d11"
		release_type = "debug" if args.debug else "release"
		dll_name = "sokol_dll_windows_x64_%s_%s.dll" % (gfxapi, release_type)
		src = SOKOL_PATH + "/" + dll_name
		dest = dll_name
		copy_file_if_different(src, dest)

	if IS_OSX:
		dylib_folder = "source/sokol/dylib"

		if not os.path.exists(dylib_folder):
			print("Dynamic libraries for OSX don't seem to be built. Please re-run 'build.py -compile-sokol'.")
			exit(1)

		if not os.path.exists("dylib"):
			os.mkdir("dylib")

		dylibs = os.listdir(dylib_folder)

		for d in dylibs:
			src = "%s/%s" % (dylib_folder, d)
			dest = "dylib/%s" % d
			copy_file_if_different(src, dest)

	return "./" + exe

def build_release():
	out_dir = "build/release"

	if os.path.exists(out_dir):
		shutil.rmtree(out_dir)

	make_dirs(out_dir)

	exe = out_dir + "/game_release" + executable_extension()

	print("Building " + exe + "...")

	extra_args = ""

	if not args.debug:
		extra_args += " -no-bounds-check -o:speed"

		if IS_WINDOWS:
			extra_args += " -subsystem:windows"
	else:
		extra_args += " -debug"

	if args.gl:
		extra_args += " -define:SOKOL_USE_GL=true"

	execute("odin build source/main_release -out:%s -strict-style -vet %s" % (exe, extra_args))
	shutil.copytree("assets", out_dir + "/assets")

	return exe

def build_web():
	out_dir = "build/web"
	make_dirs(out_dir)

	odin_extra_args = ""

	if args.debug:
		odin_extra_args += " -debug"

	print("Building js_wasm32 game object...")
	execute("odin build source/main_web -target:js_wasm32 -build-mode:obj -vet -strict-style -out:%s/game.wasm.o %s" % (out_dir, odin_extra_args))
	odin_path = subprocess.run(["odin", "root"], capture_output=True, text=True).stdout

	shutil.copyfile(os.path.join(odin_path, "core/sys/wasm/js/odin.js"), os.path.join(out_dir, "odin.js"))
	os.environ["EMSDK_QUIET"] = "1"

	wasm_lib_suffix = "debug.a" if args.debug else "release.a"

	emcc_files = [
		"%s/game.wasm.o" % out_dir,
		"source/sokol/app/sokol_app_wasm_gl_" + wasm_lib_suffix,
		"source/sokol/glue/sokol_glue_wasm_gl_" + wasm_lib_suffix,
		"source/sokol/gfx/sokol_gfx_wasm_gl_" + wasm_lib_suffix,
		"source/sokol/shape/sokol_shape_wasm_gl_" + wasm_lib_suffix,
		"source/sokol/log/sokol_log_wasm_gl_" + wasm_lib_suffix,
		"source/sokol/gl/sokol_gl_wasm_gl_" + wasm_lib_suffix,
	]

	emcc_files_str = " ".join(emcc_files)

	# Note --preload-file assets, this bakes in the whole assets directory into
	# the web build.
	emcc_flags = "--shell-file source/web/index_template.html --preload-file assets -sWASM_BIGINT -sWARN_ON_UNDEFINED_SYMBOLS=0 -sMAX_WEBGL_VERSION=2 -sASSERTIONS"

	build_flags = ""

	# -g is the emcc debug flag, it makes the errors in the browser console better.
	if args.debug:
		build_flags += " -g "

	emcc_command = "emcc %s -o %s/index.html %s %s" % (build_flags, out_dir, emcc_files_str, emcc_flags)

	emsdk_env = get_emscripten_env_command()

	if emsdk_env:
		if IS_WINDOWS:
			emcc_command = emsdk_env + " && " + emcc_command
		else:
			emcc_command = "bash -c \"" + emsdk_env + " && " + emcc_command + "\""
	else:
		if shutil.which("emcc") is None:
			print("Could not find emcc. Try providing emscripten SDK path using '-emsdk-path PATH' or run the emsdk_env script inside the emscripten folder before running this script.")
			exit(1)

	print("Building web application using emscripten to %s..." % out_dir)
	execute(emcc_command)

	# Not needed
	os.remove(os.path.join(out_dir, "game.wasm.o"))

def execute(cmd):
	res = os.system(cmd)
	if res != 0:
		print("Failed running:" + cmd)
		exit(1)

def dll_extension():
	if IS_WINDOWS:
		return ".dll"

	if IS_OSX:
		return ".dylib"

	return ".so"

def executable_extension():
	if IS_WINDOWS:
		return ".exe"

	return ".bin"

SOKOL_PATH = "source/sokol"
SOKOL_SHDC_PATH = "sokol-shdc"

def update_sokol():
	def update_sokol_bindings():
		SOKOL_ZIP_URL = "https://github.com/floooh/sokol-odin/archive/refs/heads/main.zip"

		if os.path.exists(SOKOL_PATH):
			shutil.rmtree(SOKOL_PATH)

		temp_zip = "sokol-temp.zip"
		temp_folder = "sokol-temp"
		print("Downloading Sokol Odin bindings to directory source/sokol...")
		urllib.request.urlretrieve(SOKOL_ZIP_URL, temp_zip)

		with zipfile.ZipFile(temp_zip) as zip_file:
			zip_file.extractall(temp_folder)
			shutil.copytree(temp_folder + "/sokol-odin-main/sokol", SOKOL_PATH)

		os.remove(temp_zip)
		shutil.rmtree(temp_folder)

	def update_sokol_shdc():
		if os.path.exists(SOKOL_SHDC_PATH):
			shutil.rmtree(SOKOL_SHDC_PATH)

		TOOLS_ZIP_URL = "https://github.com/floooh/sokol-tools-bin/archive/refs/heads/master.zip"
		temp_zip = "sokol-tools-temp.zip"
		temp_folder = "sokol-tools-temp"

		print("Downloading Sokol Shader Compiler to directory sokol-shdc...")
		urllib.request.urlretrieve(TOOLS_ZIP_URL, temp_zip)

		with zipfile.ZipFile(temp_zip) as zip_file:
			zip_file.extractall(temp_folder)
			shutil.copytree(temp_folder + "/sokol-tools-bin-master/bin", SOKOL_SHDC_PATH)

		if IS_LINUX:
			execute("chmod +x sokol-shdc/linux/sokol-shdc")
			execute("chmod +x sokol-shdc/linux_arm64/sokol-shdc")

		if IS_OSX:
			execute("chmod +x sokol-shdc/osx/sokol-shdc")
			execute("chmod +x sokol-shdc/osx_arm64/sokol-shdc")

		os.remove(temp_zip)
		shutil.rmtree(temp_folder)

	update_sokol_bindings()
	update_sokol_shdc()

def compile_sokol():
	owd = os.getcwd()
	os.chdir(SOKOL_PATH)

	emsdk_env = get_emscripten_env_command()
	
	print("Building Sokol C libraries...")

	if IS_WINDOWS:
		if shutil.which("cl.exe") is not None:
			execute("build_clibs_windows.cmd")
		else:
			print("cl.exe not in PATH. Try re-running build.py with flag -compile-sokol from a Visual Studio command prompt.")

		if emsdk_env:
			execute(emsdk_env + " && build_clibs_wasm.bat")
		else:
			if shutil.which("emcc.bat"):
				execute("build_clibs_wasm.bat")
			else:
				print("emcc not in PATH, skipping building of WASM libs. Tip: You can also use -emsdk-path to specify where emscripten lives.")

	elif IS_LINUX:
		execute("bash build_clibs_linux.sh")

		build_wasm_prefix = ""
		if emsdk_env:
			os.environ["EMSDK_QUIET"] = "1"
			build_wasm_prefix += emsdk_env + " && "
		elif shutil.which("emcc") is not None:
			execute("bash -c \"" + build_wasm_prefix + " bash build_clibs_wasm.sh\"")
		else:
			print("emcc not in PATH, skipping building of WASM libs. Tip: You can also use -emsdk-path to specify where emscripten lives.")
		
	elif IS_OSX:
		execute("bash build_clibs_macos.sh")
		execute("bash build_clibs_macos_dylib.sh")
		
		build_wasm_prefix = ""
		if emsdk_env:
			os.environ["EMSDK_QUIET"] = "1"
			build_wasm_prefix += emsdk_env + " && "
		elif shutil.which("emcc") is not None:
			execute("bash -c \"" + build_wasm_prefix + " bash build_clibs_wasm.sh\"")
		else:
			print("emcc not in PATH, skipping building of WASM libs. Tip: You can also use -emsdk-path to specify where emscripten lives.")

	os.chdir(owd)


def get_emscripten_env_command():
	if args.emsdk_path is None:
		return None

	if IS_WINDOWS:
		return os.path.join(args.emsdk_path, "emsdk_env.bat")
	elif IS_LINUX or IS_OSX:
		return "source " + os.path.join(args.emsdk_path, "emsdk_env.sh")

	return None

def process_exists(process_name):
	if IS_WINDOWS:
		call = 'TASKLIST', '/NH', '/FI', 'imagename eq %s' % process_name
		return process_name in str(subprocess.check_output(call))
	else:
		out = subprocess.run(["pgrep", "-f", process_name], capture_output=True, text=True).stdout
		return out != ""


	return False

def make_dirs(path):
	n = os.path.normpath(path)
	s = n.split(os.sep)
	p = ""

	for d in s:
		p = os.path.join(p, d)

		if not os.path.exists(p):
			os.mkdir(p)

def copy_file_if_different(src, dest):
	do_copy = False
	if not os.path.exists(dest):
		do_copy = True
	elif os.path.getsize(dest) != os.path.getsize(src) or os.path.getmtime(dest) != os.path.getmtime(src):
		do_copy = True

	if do_copy:
		print("Copying %s to %s" % (src, dest))
		shutil.copyfile(src, dest)
	return

print = functools.partial(print, flush=True)

main()
