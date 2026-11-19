#!/usr/bin/env python3
"""Crop per-scene thumbnails out of ManiScope's docs/images/formal48-overview.png.

The overview is a 6-column grid grouped by dimension bands. Tile order within a
band follows suite/scenes_v2.yaml (same order as data/tasks.json), so we detect
the coloured band rows, then cut fixed-pitch tiles below each band.

Read-only with respect to ManiScope; output goes to assets/img/scenes/<task>.png.

Usage:
    python3 scripts/crop_overview_tiles.py [--maniscope /path/to/ManiScope]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(HERE)

COL_PITCH = 372     # px between tile columns
TILE_X0 = 6         # left edge of first tile
TILE_W = 361
ROW_PITCH = 312     # px between tile rows inside a band block
LABEL_H = 62        # label text + coloured tier strip above each tile image
TILE_H = 249


def detect_bands(arr):
    mx = arr.max(2)
    mn = arr.min(2)
    band = ((mx - mn) > 60).mean(1) > 0.8
    runs, start = [], None
    for y, on in enumerate(band):
        if on and start is None:
            start = y
        if not on and start is not None:
            runs.append((start, y))
            start = None
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maniscope", default=os.environ.get("MANISCOPE_ROOT", os.path.join(WEB, "..", "ManiScope")))
    ap.add_argument("--tasks", default=os.path.join(WEB, "data", "tasks.json"))
    ap.add_argument("--out", default=os.path.join(WEB, "assets", "img", "scenes"))
    a = ap.parse_args()

    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        sys.exit("Pillow and numpy are required: pip install pillow numpy")

    src = os.path.join(a.maniscope, "docs", "images", "formal48-overview.png")
    if not os.path.exists(src):
        sys.exit(f"missing {src}")
    tasks = json.load(open(a.tasks, encoding="utf-8"))
    groups = tasks["dimensions"]

    im = Image.open(src).convert("RGB")
    arr = np.array(im).astype(int)
    bands = detect_bands(arr)
    if len(bands) != len(groups):
        sys.exit(f"found {len(bands)} bands but {len(groups)} dimensions; layout changed?")

    os.makedirs(a.out, exist_ok=True)
    n = 0
    for (band_start, band_end), dim in zip(bands, groups):
        for idx, scene in enumerate(dim["scenes"]):
            r, c = divmod(idx, 6)
            x0 = TILE_X0 + c * COL_PITCH
            y0 = band_end + r * ROW_PITCH + LABEL_H
            tile = im.crop((x0, y0, x0 + TILE_W, y0 + TILE_H))
            tile.save(os.path.join(a.out, f"{scene['name']}.png"), optimize=True)
            n += 1
    print(f"wrote {n} thumbnails to {a.out}")


if __name__ == "__main__":
    main()
