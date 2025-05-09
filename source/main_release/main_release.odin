/*
For making a release exe that does not use hot reload.

Note how this just uses a `game` package to call the game code. No DLL is loaded.
*/

package main_release

import "core:log"
import "core:os"
import "core:os/os2"
import "base:runtime"
import "core:mem"
import game ".."
import sapp "../sokol/app"

_ :: mem

USE_TRACKING_ALLOCATOR :: #config(USE_TRACKING_ALLOCATOR, false)

main :: proc() {
	if exe_dir, exe_dir_err := os2.get_executable_directory(context.temp_allocator); exe_dir_err == nil {
		os2.set_working_directory(exe_dir)
	}

	mode: int = 0
	when ODIN_OS == .Linux || ODIN_OS == .Darwin {
		mode = os.S_IRUSR | os.S_IWUSR | os.S_IRGRP | os.S_IROTH
	}

	logh, logh_err := os.open("log.txt", (os.O_CREATE | os.O_TRUNC | os.O_RDWR), mode)

	if logh_err == os.ERROR_NONE {
		os.stdout = logh
		os.stderr = logh
	}

	logger_alloc := context.allocator
	logger := logh_err == os.ERROR_NONE ? log.create_file_logger(logh, allocator = logger_alloc) : log.create_console_logger(allocator = logger_alloc)
	context.logger = logger
	custom_context = context

	when USE_TRACKING_ALLOCATOR {
		default_allocator := context.allocator
		tracking_allocator: mem.Tracking_Allocator
		mem.tracking_allocator_init(&tracking_allocator, default_allocator)
		context.allocator = mem.tracking_allocator(&tracking_allocator)
	}

	app_desc := game.game_app_default_desc()

	app_desc.init_cb = init
	app_desc.frame_cb = frame
	app_desc.cleanup_cb = cleanup
	app_desc.event_cb = event

	sapp.run(app_desc)

	free_all(context.temp_allocator)

	when USE_TRACKING_ALLOCATOR {
		for _, value in tracking_allocator.allocation_map {
			log.errorf("%v: Leaked %v bytes\n", value.location, value.size)
		}

		mem.tracking_allocator_destroy(&tracking_allocator)
	}

	if logh_err == os.ERROR_NONE {
		log.destroy_file_logger(logger, logger_alloc)
	}
}

custom_context: runtime.Context

init :: proc "c" () {
	context = custom_context
	game.game_init()
}

frame :: proc "c" () {
	context = custom_context
	game.game_frame()
}

event :: proc "c" (e: ^sapp.Event) {
	context = custom_context
	game.game_event(e)
}

cleanup :: proc "c" () {
	context = custom_context
	game.game_cleanup()
}

// make game use good GPU on laptops etc

@(export)
NvOptimusEnablement: u32 = 1

@(export)
AmdPowerXpressRequestHighPerformance: i32 = 1