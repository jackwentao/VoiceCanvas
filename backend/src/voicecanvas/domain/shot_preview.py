"""预览图片的资源与尺寸边界。"""

import struct


def png_dimensions(png: bytes) -> tuple[int, int]:
    if (
        len(png) < 33
        or len(png) > 8_000_000
        or png[:8] != b"\x89PNG\r\n\x1a\n"
        or png[12:16] != b"IHDR"
    ):
        raise ValueError("渲染器未返回有效 PNG")
    return struct.unpack(">II", png[16:24])
