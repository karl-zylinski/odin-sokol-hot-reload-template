/*
This file is the starting point of your game.

Some importants procedures:
- game_init: Initializes sokol_gfx and sets up the game state.
- game_frame: Called one per frame, do your game logic and rendering in here.
- game_cleanup: Called on shutdown of game, cleanup memory etc.

The hot reload compiles the contents of this folder into a game DLL. A host
application loads that DLL and calls the procedures of the DLL. 

Special procedures that help facilitate the hot reload:
- game_memory: Run just before a hot reload. The hot reload host application can
	that way keep a pointer to the game's memory and feed it to the new game DLL
	after the hot reload is complete.
- game_hot_reloaded: Sets the `g` global variable in the new game DLL. The value
	comes from the value the host application got from game_memory before the
	hot reload.

When release or web builds are made, then this whole package is just
treated as a normal Odin package. No DLL is created.

The hot applications use sokol_app to open the window. They use the settings
returned by the `game_app_default_desc` procedure.
*/

package game

import "core:math/linalg"
import "core:image/png"
import "core:log"
import "core:slice"
import sapp "sokol/app"
import sg "sokol/gfx"
import sglue "sokol/glue"
import slog "sokol/log"

Game_Memory :: struct {
	pip: sg.Pipeline,
	bind: sg.Bindings,
	rx, ry: f32,
}

Mat4 :: matrix[4,4]f32
Vec3 :: [3]f32
g: ^Game_Memory

Vertex :: struct {
	x, y, z: f32,
	color: u32,
	u, v: u16,
}

@export
game_app_default_desc :: proc() -> sapp.Desc {
	return {
		width = 1280,
		height = 720,
		sample_count = 4,
		window_title = "Odin + Sokol hot reload template",
		icon = { sokol_default = true },
		logger = { func = slog.func },
		html5_update_document_title = true,
	}
}

@export
game_init :: proc() {
	g = new(Game_Memory)

	game_hot_reloaded(g)

	sg.setup({
		environment = sglue.environment(),
		logger = { func = slog.func },
	})

	// The remainder of this proc just sets up a sample cube and loads the
	// texture to put on the cube's sides.
	//
	// The cube is from https://github.com/floooh/sokol-odin/blob/main/examples/cube/main.odin

	/*
		Cube vertex buffer with packed vertex formats for color and texture coords.
		Note that a vertex format which must be portable across all
		backends must only use the normalized integer formats
		(BYTE4N, UBYTE4N, SHORT2N, SHORT4N), which can be converted
		to floating point formats in the vertex shader inputs.
	*/

	vertices := [?]Vertex {
		// pos               color       uvs
		{ -1.0, -1.0, -1.0,  0xFF0000FF,     0,     0 },
		{  1.0, -1.0, -1.0,  0xFF0000FF, 32767,     0 },
		{  1.0,  1.0, -1.0,  0xFF0000FF, 32767, 32767 },
		{ -1.0,  1.0, -1.0,  0xFF0000FF,     0, 32767 },

		{ -1.0, -1.0,  1.0,  0xFF00FF00,     0,     0 },
		{  1.0, -1.0,  1.0,  0xFF00FF00, 32767,     0 },
		{  1.0,  1.0,  1.0,  0xFF00FF00, 32767, 32767 },
		{ -1.0,  1.0,  1.0,  0xFF00FF00,     0, 32767 },

		{ -1.0, -1.0, -1.0,  0xFFFF0000,     0,     0 },
		{ -1.0,  1.0, -1.0,  0xFFFF0000, 32767,     0 },
		{ -1.0,  1.0,  1.0,  0xFFFF0000, 32767, 32767 },
		{ -1.0, -1.0,  1.0,  0xFFFF0000,     0, 32767 },

		{  1.0, -1.0, -1.0,  0xFFFF007F,     0,     0 },
		{  1.0,  1.0, -1.0,  0xFFFF007F, 32767,     0 },
		{  1.0,  1.0,  1.0,  0xFFFF007F, 32767, 32767 },
		{  1.0, -1.0,  1.0,  0xFFFF007F,     0, 32767 },

		{ -1.0, -1.0, -1.0,  0xFFFF7F00,     0,     0 },
		{ -1.0, -1.0,  1.0,  0xFFFF7F00, 32767,     0 },
		{  1.0, -1.0,  1.0,  0xFFFF7F00, 32767, 32767 },
		{  1.0, -1.0, -1.0,  0xFFFF7F00,     0, 32767 },

		{ -1.0,  1.0, -1.0,  0xFF007FFF,     0,     0 },
		{ -1.0,  1.0,  1.0,  0xFF007FFF, 32767,     0 },
		{  1.0,  1.0,  1.0,  0xFF007FFF, 32767, 32767 },
		{  1.0,  1.0, -1.0,  0xFF007FFF,     0, 32767 },
	}
	g.bind.vertex_buffers[0] = sg.make_buffer({
		data = { ptr = &vertices, size = size_of(vertices) },
	})

	// create an index buffer for the cube
	indices := [?]u16 {
		0, 1, 2,  0, 2, 3,
		6, 5, 4,  7, 6, 4,
		8, 9, 10,  8, 10, 11,
		14, 13, 12,  15, 14, 12,
		16, 17, 18,  16, 18, 19,
		22, 21, 20,  23, 22, 20,
	}
	g.bind.index_buffer = sg.make_buffer({
		usage = {
			index_buffer = true,
		},
		data = { ptr = &indices, size = size_of(indices) },
	})

	if img_data, img_data_ok := read_entire_file("assets/round_cat.png", context.temp_allocator); img_data_ok {
		if img, img_err := png.load_from_bytes(img_data, allocator = context.temp_allocator); img_err == nil {
			sg_img := sg.make_image({
				width = i32(img.width),
				height = i32(img.height),
				data = {
					subimage = {
						0 = {
							0 = { ptr = raw_data(img.pixels.buf), size = uint(slice.size(img.pixels.buf[:])) },
						},
					},
				},
			})

			g.bind.views[VIEW_tex] = sg.make_view({
				texture = sg.Texture_View_Desc({image = sg_img}),
			})
		} else {
			log.error(img_err)
		}
	} else {
		log.error("Failed loading texture")
	}

	// a sampler with default options to sample the above image as texture
	g.bind.samplers[SMP_smp] = sg.make_sampler({})

	// shader and pipeline object
	g.pip = sg.make_pipeline({
		shader = sg.make_shader(texcube_shader_desc(sg.query_backend())),
		layout = {
			attrs = {
				ATTR_texcube_pos = { format = .FLOAT3 },
				ATTR_texcube_color0 = { format = .UBYTE4N },
				ATTR_texcube_texcoord0 = { format = .SHORT2N },
			},
		},
		index_type = .UINT16,
		cull_mode = .BACK,
		depth = {
			compare = .LESS_EQUAL,
			write_enabled = true,
		},
	})
}

@export
game_frame :: proc() {
	dt := f32(sapp.frame_duration())
	g.rx += 60 * dt
	g.ry += 120 * dt

	// vertex shader uniform with model-view-projection matrix
	vs_params := Vs_Params {
		mvp = compute_mvp(g.rx, g.ry),
	}

	pass_action := sg.Pass_Action {
		colors = {
			0 = { load_action = .CLEAR, clear_value = { 0.41, 0.68, 0.83, 1 } },
		},
	}

	sg.begin_pass({ action = pass_action, swapchain = sglue.swapchain() })
	sg.apply_pipeline(g.pip)
	sg.apply_bindings(g.bind)
	sg.apply_uniforms(UB_vs_params, { ptr = &vs_params, size = size_of(vs_params) })

	// 36 is the number of indices
	sg.draw(0, 36, 1)

	sg.end_pass()
	sg.commit()

	free_all(context.temp_allocator)
}

compute_mvp :: proc (rx, ry: f32) -> Mat4 {
	proj := linalg.matrix4_perspective(60.0 * linalg.RAD_PER_DEG, sapp.widthf() / sapp.heightf(), 0.01, 10.0)
	view := linalg.matrix4_look_at_f32({0.0, -1.5, -6.0}, {}, {0.0, 1.0, 0.0})
	view_proj := proj * view
	rxm := linalg.matrix4_rotate_f32(rx * linalg.RAD_PER_DEG, {1.0, 0.0, 0.0})
	rym := linalg.matrix4_rotate_f32(ry * linalg.RAD_PER_DEG, {0.0, 1.0, 0.0})
	model := rxm * rym
	return view_proj * model
}

force_reset: bool

@export
game_event :: proc(e: ^sapp.Event) {
	#partial switch e.type {
	case .KEY_DOWN:
		if e.key_code == .F6 {
			force_reset = true
		}
	}
}

@export
game_cleanup :: proc() {
	sg.shutdown()
	free(g)
}

@(export)
game_memory :: proc() -> rawptr {
	return g
}

@(export)
game_memory_size :: proc() -> int {
	return size_of(Game_Memory)
}

@(export)
game_hot_reloaded :: proc(mem: rawptr) {
	g = (^Game_Memory)(mem)

	// Here you can also set your own global variables. A good idea is to make
	// your global variables into pointers that point to something inside
	// `g`. Then that state carries over between hot reloads.
}

@(export)
game_force_restart :: proc() -> bool {
	return force_reset
}

