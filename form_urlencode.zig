const std = @import("std");

test formUrlEncode {
    var encoded = std.ArrayList(u8).init(std.testing.allocator);
    defer encoded.deinit();
    const params = [_]Tuple{ .{ .name = "hello", .value = "world" }, .{ .name = "&hello", .value = "=world!/" } };
    try formUrlEncode(&params, encoded.writer());
    try std.testing.expectEqualStrings("hello=world&%26hello=%3Dworld%21%2F", encoded.items);
}

pub const Tuple = struct {
    name: []const u8,
    value: []const u8,
};

/// This function encodes the given tuples, using the
/// application/x-www-form-urlencoded serialization method as documented in
/// <https://url.spec.whatwg.org/#urlencoded-serializing>.
/// For `writer` you can pass in any `std.io.Writer`.
pub fn formUrlEncode(tuples: []const Tuple, writer: anytype) @TypeOf(writer).Error!void {
    for (tuples, 0..) |tuple, i| {
        if (i > 0) {
            try writer.writeByte('&');
        }
        try percentEncode(tuple.name, writer);
        try writer.writeByte('=');
        try percentEncode(tuple.value, writer);
    }
}

test percentEncode {
    var encoded = std.ArrayList(u8).init(std.testing.allocator);
    defer encoded.deinit();
    try percentEncode("=world!/", encoded.writer());
    try std.testing.expectEqualStrings("%3Dworld%21%2F", encoded.items);
}

/// This function percent encodes a string similar to
/// <https://url.spec.whatwg.org/#string-percent-encode-after-encoding>
/// the encoding at the beginning, assuming the input is already UTF-8 encoded.
/// For `writer` you can pass in any `std.io.Writer`
pub fn percentEncode(str: []const u8, writer: anytype) @TypeOf(writer).Error!void {
    for (str) |c| {
        if (inPercentEncodeSet(c)) {
            try writer.print("%{X}", .{c});
        } else {
            try writer.writeByte(c);
        }
    }
}

fn inPercentEncodeSet(c: u8) bool {
    return switch (c) {
        0x00...0x29, 0x2B, 0x2C, 0x2F, 0x3A...0x40, 0x5B...0x5E, 0x60, 0x7B...0xFF => true,
        else => false,
    };
}
