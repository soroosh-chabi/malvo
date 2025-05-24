const std = @import("std");

pub fn main() !void {
    var dbg_alloc = std.heap.DebugAllocator(.{}).init;
    defer {
        _ = dbg_alloc.deinit();
    }
    const allocator = dbg_alloc.allocator();
    var client: std.http.Client = .{ .allocator = allocator };
    defer client.deinit();
    if (try locked(allocator, &client)) {
        var passwd: [1024]u8 = undefined;
        const read = try getPasswd(&passwd);
        try unlock(allocator, &client, passwd[0..read]);
    }
}

pub fn getPasswd(buffer: []u8) !usize {
    const stdin = std.io.getStdIn();
    const stdout = std.io.getStdOut();
    if (!(stdin.isTty() and stdout.isTty())) {
        return error.NotTerm;
    }
    try stdout.writeAll("Please enter your Bitwarden vault password: ");
    var termios: std.os.linux.termios = undefined;
    if (std.os.linux.tcgetattr(stdin.handle, &termios) != 0) {
        return error.TermAttrGet;
    }
    const old_echo = termios.lflag.ECHO;
    const old_echonl = termios.lflag.ECHONL;
    termios.lflag.ECHO = false;
    termios.lflag.ECHONL = true;
    if (std.os.linux.tcsetattr(stdin.handle, .FLUSH, &termios) != 0) {
        return error.TermAttrSet;
    }
    defer {
        termios.lflag.ECHO = old_echo;
        termios.lflag.ECHONL = old_echonl;
        _ = std.os.linux.tcsetattr(stdin.handle, .FLUSH, &termios);
    }
    const read = try stdin.read(buffer);
    if (read == buffer.len) {
        return error.PasswdTooLarge;
    }
    return read - 1;
}

const server_header_buffer_size = 1024;

pub fn locked(allocator: std.mem.Allocator, client: *std.http.Client) !bool {
    const status_uri = try std.Uri.parse("http://localhost:8087/status");
    var server_header_buffer: [server_header_buffer_size]u8 = undefined;
    var request = try client.open(.GET, status_uri, .{ .server_header_buffer = &server_header_buffer });
    defer request.deinit();
    try request.send();
    try request.wait();
    if (request.response.status != .ok) {
        return error.BadHttpStatus;
    }
    const response_size = 1024;
    var response: [response_size]u8 = undefined;
    const read = try request.read(&response);
    if (read >= response_size) {
        return error.HttpResponseTooLarge;
    }
    var parsed_response = try std.json.parseFromSlice(std.json.Value, allocator, response[0..read], .{});
    defer parsed_response.deinit();
    const status = parsed_response.value.object.get("data").?.object.get("template").?.object.get("status").?.string;
    return std.mem.eql(u8, status, "locked");
}

pub fn unlock(allocator: std.mem.Allocator, client: *std.http.Client, passwd: []const u8) !void {
    var object = std.json.ObjectMap.init(allocator);
    defer object.deinit();
    try object.put("password", .{ .string = passwd });
    var payload = std.ArrayList(u8).init(allocator);
    defer payload.deinit();
    try std.json.stringify(std.json.Value{ .object = object }, .{}, payload.writer());
    const status = try unlockFetch(payload.items, client);
    if (status != .ok) {
        return error.UnlockFailed;
    }
}

fn unlockFetch(payload: []const u8, client: *std.http.Client) !std.http.Status {
    var server_header_buffer: [server_header_buffer_size]u8 = undefined;
    const headers: std.http.Client.Request.Headers = .{ .content_type = .{ .override = "application/json" } };
    const fetch_options: std.http.Client.FetchOptions = .{ .server_header_buffer = &server_header_buffer, .method = .POST, .location = .{ .url = "http://localhost:8087/unlock" }, .payload = payload, .headers = headers };
    return (try client.fetch(fetch_options)).status;
}

// fn unlockRequest(payload: []const u8, client: *std.http.Client) !std.http.Status {
//     const unlock_uri = try std.Uri.parse("http://localhost:8087/unlock");
//     var server_header_buffer: [server_header_buffer_size]u8 = undefined;
//     var request = try client.open(.POST, unlock_uri, .{ .server_header_buffer = &server_header_buffer });
//     defer request.deinit();
//     try request.send();
//     try request.wait();
//     if (request.response.status != .ok) {
//         return error.BadHttpStatus;
//     }
//     const response_size = 1024;
//     var response: [response_size]u8 = undefined;
//     const read = try request.read(&response);
//     if (read >= response_size) {
//         return error.HttpResponseTooLarge;
//     }
//     var parsed_response = try std.json.parseFromSlice(std.json.Value, allocator, response[0..read], .{});
//     defer parsed_response.deinit();
//     const status = parsed_response.value.object.get("data").?.object.get("template").?.object.get("status").?.string;
//     return std.mem.eql(u8, status, "locked");
// }
