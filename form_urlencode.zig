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
        try std.Uri.Component.percentEncode(writer, tuple.name, notInPercentEncodeSet);
        try writer.writeByte('=');
        try std.Uri.Component.percentEncode(writer, tuple.value, notInPercentEncodeSet);
    }
}

test notInPercentEncodeSet {
    var encoded = std.ArrayList(u8).init(std.testing.allocator);
    defer encoded.deinit();
    try std.Uri.Component.percentEncode(encoded.writer(), "=world!/", notInPercentEncodeSet);
    try std.testing.expectEqualStrings("%3Dworld%21%2F", encoded.items);
}

pub fn notInPercentEncodeSet(c: u8) bool {
    return switch (c) {
        0x00...0x29, 0x2B, 0x2C, 0x2F, 0x3A...0x40, 0x5B...0x5E, 0x60, 0x7B...0xFF => false,
        else => true,
    };
}
