const std = @import("std");

pub fn main() !void {
    var dbg_alloc = std.heap.DebugAllocator(.{}).init;
    defer {
        _ = dbg_alloc.deinit();
    }
    const allocator = dbg_alloc.allocator();
    var client: std.http.Client = .{ .allocator = allocator };
    const statusURI = try std.Uri.parse("http://localhost:8087/status");
    const server_header_buffer = try allocator.alloc(u8, 1024);
    defer allocator.free(server_header_buffer);
    var request = try client.open(.GET, statusURI, .{ .server_header_buffer = server_header_buffer });
    defer request.deinit();
}
