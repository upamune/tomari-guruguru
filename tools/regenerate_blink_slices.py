from __future__ import annotations

import argparse
import math
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path


CANVAS = 1200
PAIRS = {
    "D": "A",
    "E": "B",
    "F": "C",
}


@dataclass(frozen=True)
class BBox:
    min_x: int
    min_y: int
    max_x: int
    max_y: int

    @property
    def width(self) -> int:
        return self.max_x - self.min_x + 1

    @property
    def height(self) -> int:
        return self.max_y - self.min_y + 1

    @property
    def center_x(self) -> float:
        return (self.min_x + self.max_x) / 2

    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) / 2


@dataclass(frozen=True)
class Component:
    area: int
    bbox: BBox

    @property
    def center_x(self) -> float:
        return self.bbox.center_x

    @property
    def center_y(self) -> float:
        return self.bbox.center_y


def run_bytes(cmd: list[str], *, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        cmd,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def decode_rgba(path: Path) -> bytearray:
    return bytearray(
        run_bytes(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(path),
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgba",
                "-",
            ]
        )
    )


def encode_webp(path: Path, data: bytearray) -> None:
    run_bytes(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "-s",
            f"{CANVAS}x{CANVAS}",
            "-i",
            "-",
            "-c:v",
            "libwebp",
            "-lossless",
            "1",
            "-y",
            str(path),
        ],
        input_bytes=bytes(data),
    )


def pixel_offset(x: int, y: int) -> int:
    return (y * CANVAS + x) * 4


def alpha_bbox(data: bytearray) -> BBox:
    min_x = CANVAS
    min_y = CANVAS
    max_x = -1
    max_y = -1
    for y in range(CANVAS):
        row = y * CANVAS * 4
        for x in range(CANVAS):
            if data[row + x * 4 + 3] > 8:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x < min_x:
        raise ValueError("image has no visible pixels")
    return BBox(min_x, min_y, max_x, max_y)


def is_dark_pixel(data: bytearray, x: int, y: int) -> bool:
    idx = pixel_offset(x, y)
    if data[idx + 3] < 160:
        return False
    r, g, b = data[idx], data[idx + 1], data[idx + 2]
    return max(r, g, b) < 70 and (r + g + b) // 3 < 55


def dark_components(data: bytearray, bounds: BBox) -> list[Component]:
    dark_pixels: set[int] = set()
    for y in range(bounds.min_y, bounds.max_y + 1):
        for x in range(bounds.min_x, bounds.max_x + 1):
            if is_dark_pixel(data, x, y):
                dark_pixels.add(y * CANVAS + x)

    components: list[Component] = []
    while dark_pixels:
        first = dark_pixels.pop()
        stack = [first]
        area = 0
        min_x = CANVAS
        min_y = CANVAS
        max_x = -1
        max_y = -1

        while stack:
            pos = stack.pop()
            y, x = divmod(pos, CANVAS)
            area += 1
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)

            for ny in (y - 1, y, y + 1):
                if ny < bounds.min_y or ny > bounds.max_y:
                    continue
                for nx in (x - 1, x, x + 1):
                    if nx < bounds.min_x or nx > bounds.max_x or (nx == x and ny == y):
                        continue
                    npos = ny * CANVAS + nx
                    if npos in dark_pixels:
                        dark_pixels.remove(npos)
                        stack.append(npos)

        components.append(Component(area, BBox(min_x, min_y, max_x, max_y)))
    return components


def find_eye_components(data: bytearray) -> list[Component]:
    subject = alpha_bbox(data)
    search = BBox(
        round(subject.min_x + subject.width * 0.18),
        round(subject.min_y + subject.height * 0.30),
        round(subject.min_x + subject.width * 0.82),
        round(subject.min_y + subject.height * 0.75),
    )
    expected_y = subject.min_y + subject.height * 0.42
    candidates: list[Component] = []
    for comp in dark_components(data, search):
        w = comp.bbox.width
        h = comp.bbox.height
        density = comp.area / (w * h)
        if not (80 <= comp.area <= 18000):
            continue
        if not (18 <= w <= subject.width * 0.22):
            continue
        if not (5 <= h <= subject.height * 0.24):
            continue
        is_dense_eye = density >= 0.45
        is_low_gaze_eye = (
            250 <= comp.area <= 1200
            and 35 <= w <= 100
            and 12 <= h <= 45
            and comp.center_y >= search.min_y + search.height * 0.52
        )
        if not (is_dense_eye or is_low_gaze_eye):
            continue
        if comp.center_y < search.min_y + search.height * 0.06:
            continue
        candidates.append(comp)

    if not candidates:
        raise RuntimeError("could not find any eye candidates")

    subject_center = subject.center_x

    def score(comp: Component) -> float:
        return comp.area - abs(comp.center_y - expected_y) * 4

    left_candidates = [c for c in candidates if c.center_x < subject_center]
    right_candidates = [c for c in candidates if c.center_x > subject_center]
    if left_candidates and right_candidates:
        return sorted(
            [max(left_candidates, key=score), max(right_candidates, key=score)],
            key=lambda c: c.center_x,
        )

    return sorted([max(candidates, key=score)], key=lambda c: c.center_x)


def sample_fill_color(data: bytearray, eye: Component) -> tuple[int, int, int, int]:
    box = eye.bbox
    pad_x = max(18, round(box.width * 0.5))
    pad_y = max(18, round(box.height * 0.45))
    min_x = max(0, box.min_x - pad_x)
    max_x = min(CANVAS - 1, box.max_x + pad_x)
    min_y = max(0, box.min_y - pad_y)
    max_y = min(CANVAS - 1, box.max_y + pad_y)
    rs: list[int] = []
    gs: list[int] = []
    bs: list[int] = []

    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            idx = pixel_offset(x, y)
            a = data[idx + 3]
            if a < 180:
                continue
            r, g, b = data[idx], data[idx + 1], data[idx + 2]
            if max(r, g, b) < 90:
                continue
            rs.append(r)
            gs.append(g)
            bs.append(b)

    if not rs:
        return (245, 223, 198, 255)
    return (
        round(statistics.median(rs)),
        round(statistics.median(gs)),
        round(statistics.median(bs)),
        255,
    )


def blend_pixel(
    data: bytearray,
    x: int,
    y: int,
    color: tuple[int, int, int, int],
    amount: float,
) -> None:
    idx = pixel_offset(x, y)
    inv = 1 - amount
    data[idx] = round(data[idx] * inv + color[0] * amount)
    data[idx + 1] = round(data[idx + 1] * inv + color[1] * amount)
    data[idx + 2] = round(data[idx + 2] * inv + color[2] * amount)
    data[idx + 3] = max(data[idx + 3], color[3])


def erase_open_eye(data: bytearray, eye: Component) -> None:
    box = eye.bbox
    color = sample_fill_color(data, eye)
    density = eye.area / (box.width * box.height)
    is_low_gaze_eye = box.height <= 45 and density < 0.45
    radius_x = max(24, round(box.width * 0.75))
    radius_y = max(44, round(box.height * 1.9)) if is_low_gaze_eye else max(22, round(box.height * 0.62))
    center_x = box.center_x
    center_y = box.center_y - box.height * 0.75 if is_low_gaze_eye else box.center_y

    for y in range(max(0, round(center_y - radius_y)), min(CANVAS, round(center_y + radius_y) + 1)):
        for x in range(max(0, round(center_x - radius_x)), min(CANVAS, round(center_x + radius_x) + 1)):
            nx = (x - center_x) / radius_x
            ny = (y - center_y) / radius_y
            distance = nx * nx + ny * ny
            if distance <= 0.72:
                blend_pixel(data, x, y, color, 1.0)
            elif distance <= 1.0:
                blend_pixel(data, x, y, color, (1.0 - distance) / 0.28)


def draw_disc(data: bytearray, cx: float, cy: float, radius: float, color: tuple[int, int, int, int]) -> None:
    min_x = max(0, math.floor(cx - radius - 1))
    max_x = min(CANVAS - 1, math.ceil(cx + radius + 1))
    min_y = max(0, math.floor(cy - radius - 1))
    max_y = min(CANVAS - 1, math.ceil(cy + radius + 1))
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            distance = math.hypot(x - cx, y - cy)
            if distance <= radius:
                blend_pixel(data, x, y, color, 1.0)
            elif distance <= radius + 1:
                blend_pixel(data, x, y, color, radius + 1 - distance)


def draw_closed_eye(data: bytearray, eye: Component) -> None:
    box = eye.bbox
    density = eye.area / (box.width * box.height)
    is_low_gaze_eye = box.height <= 45 and density < 0.45
    width = max(42, box.width * 1.22)
    half = width / 2
    baseline_y = box.min_y - box.height * 0.45 if is_low_gaze_eye else box.min_y + box.height * 0.60
    arch = max(7, box.height * 0.16)
    thickness = max(7, min(13, box.height * 0.14))
    color = (7, 7, 7, 255)

    steps = max(24, round(width * 0.8))
    for i in range(steps + 1):
        t = -1 + 2 * i / steps
        x = eye.center_x + t * half
        y = baseline_y + arch * (t * t)
        draw_disc(data, x, y, thickness / 2, color)


def regenerate_frame(source_path: Path, output_path: Path) -> None:
    data = decode_rgba(source_path)
    eyes = find_eye_components(data)
    for eye in eyes:
        erase_open_eye(data, eye)
    for eye in eyes:
        draw_closed_eye(data, eye)
    encode_webp(output_path, data)


def regenerate_character(slices_dir: Path) -> None:
    for closed_sheet, open_sheet in PAIRS.items():
        print(f"{slices_dir.parent.name} {open_sheet}->{closed_sheet}")
        for r in range(5):
            for c in range(5):
                source_path = slices_dir / open_sheet / f"r{r}c{c}.webp"
                output_path = slices_dir / closed_sheet / f"r{r}c{c}.webp"
                regenerate_frame(source_path, output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate closed-eye slices from matching open-eye slices."
    )
    parser.add_argument(
        "characters",
        nargs="+",
        type=Path,
        help="Character directories under public/characters, or their slices directories.",
    )
    args = parser.parse_args()

    for character_dir in args.characters:
        slices_dir = character_dir
        if slices_dir.name != "slices":
            slices_dir = character_dir / "slices"
        regenerate_character(slices_dir)


if __name__ == "__main__":
    main()
