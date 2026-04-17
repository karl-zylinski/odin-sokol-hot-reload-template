#+build !js
package game

import "core:os"

@(require_results)
read_entire_file :: proc(name: string, allocator := context.allocator, loc := #caller_location) -> (data: []byte, success: bool) {
	err: os.Error
	data, err = os.read_entire_file(name, allocator, loc)
	return data, err == nil
}

write_entire_file :: proc(name: string, data: []byte, truncate := true) -> (success: bool) {
	return os.write_entire_file(name, data, truncate = truncate) == nil
}