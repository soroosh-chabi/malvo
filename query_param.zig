const std = @import("std");

test "Percent Encode Set" {
    var writer = std.io.getStdOut().writer();
    const params = [_]Pair{ .{ .key = "hello", .value = "world" }, .{ .key = "&hello", .value = "=world!/" } };
    try formUrlEncode(&params, writer);
    try writer.writeByte('\n');
}

const Pair = struct {
    key: []const u8,
    value: []const u8,
};

fn formUrlEncode(params: []const Pair, writer: anytype) @TypeOf(writer).Error!void {
    for (params, 0..) |param, i| {
        if (i > 0) {
            try writer.writeByte('&');
        }
        try percentEncodeStr(param.key, writer);
        try writer.writeByte('=');
        try percentEncodeStr(param.value, writer);
    }
}

fn percentEncodeStr(str: []const u8, writer: anytype) @TypeOf(writer).Error!void {
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
