const std = @import("std");

test "Percent Encode Set" {
    try percentEncodeStr("me!&/!()", std.io.getStdOut().writer().any());
}

fn percentEncodeStr(str: []const u8, writer: std.io.AnyWriter) !void {
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
