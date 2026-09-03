#!/usr/bin/env python3
"""Prove the icon generator's three guards can fail.

Every check in this repository ships with a mutation showing it can go red.
The generator's guards did not: they were exercised by hand once, before
merge, and the README said so in the present tense as though something re-ran
them. Nothing did. This is that something.

Each case below breaks one guard — in memory, or in a copy of the icon set
written to a temporary directory — and requires the guard to raise. No file in
the working tree is touched. A fresh copy of the generator is loaded per
mutation, so a break never leaks into the next case. If a guard stops working,
this fails on the next run instead of on the day somebody happens to look.
"""

import importlib.util
import os
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    """A fresh copy of the generator, so mutations never leak between cases."""
    spec = importlib.util.spec_from_file_location(
        "generate_icons", os.path.join(HERE, "generate-icons.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_raises(label, fn):
    try:
        fn()
    except SystemExit as exc:
        print(f"  ok  {label:52s} {exc}")
        return
    raise SystemExit(f"self-test FAILED: {label} was not caught")


def expect_passes(label, fn):
    try:
        fn()
    except SystemExit as exc:
        raise SystemExit(f"self-test FAILED: {label} should have passed: {exc}")
    print(f"  ok  {label}")


def chunk(kind, body):
    return (struct.pack(">I", len(body)) + kind + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))


def png_with(extra_kind, extra_body, path):
    """A minimal PNG carrying one extra chunk type."""
    parts = [b"\x89PNG\r\n\x1a\n",
             chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))]
    if extra_kind:
        parts.append(chunk(extra_kind, extra_body))
    parts += [chunk(b"IDAT", zlib.compress(b"\x00\x00")), chunk(b"IEND", b"")]
    open(path, "wb").write(b"".join(parts))
    return path


def main():
    print("icon-generator self-test")
    work = tempfile.mkdtemp(prefix="icon-selftest.")

    # 1. The boundary. The comparison shipped inverted once, which put the
    #    48 px frame on the single-ring mark against every document that
    #    describes it, and nothing failed.
    gen = load()
    gen.mark_for = lambda size: "full" if size > gen.FULL_MARK_FROM else "single"
    expect_raises("an inverted boundary comparison", gen.check_boundary)

    gen = load()
    expect_passes("the real boundary passes", gen.check_boundary)

    # 2. The chunk allowlist. A denylist passed `pHYs`, which one `dpi=`
    #    argument is enough to write.
    gen = load()
    clean = png_with(None, b"", os.path.join(work, "clean.png"))
    expect_passes("a raster with only IHDR, IDAT, IEND",
                  lambda: gen.verify_png(clean, "clean.png"))

    for kind in (b"pHYs", b"tEXt", b"iCCP", b"tIME"):
        planted = png_with(kind, b"\x00" * 9, os.path.join(work, "planted.png"))
        expect_raises(f"a raster carrying {kind.decode()}",
                      lambda p=planted, k=kind: gen.verify_png(p, "planted.png"))

    # 3. The icon frame count. Pillow drops a requested size larger than the
    #    image it is saving from, and says nothing.
    gen = load()
    one = os.path.join(work, "one.ico")
    gen.draw(16).save(one, sizes=[(16, 16), (32, 32), (48, 48)])
    expect_raises("an icon saved from its smallest frame",
                  lambda: gen.verify_ico(one, "one.ico"))

    three = os.path.join(work, "three.ico")
    large, *smaller = [gen.draw(s) for s in (48, 32, 16)]
    large.save(three, sizes=[(48, 48), (32, 32), (16, 16)], append_images=smaller)
    expect_passes("an icon saved from its largest frame",
                  lambda: gen.verify_ico(three, "three.ico"))

    # 4. The committed set, not just fresh renders. A chunk planted into a
    #    committed icon changes no pixel, so a comparison alone passed it — and
    #    `--check` exited 0 with "all 7 icons match". That is metadata reaching
    #    a published asset past a green pipeline.
    gen = load()
    committed = os.path.join(work, "committed")
    names = gen.render(committed)
    expect_passes("a clean committed set", lambda: gen.check_against(committed))

    target = os.path.join(committed, "favicon-32x32.png")
    raw = open(target, "rb").read()
    at = raw.index(b"IDAT") - 4
    planted = (raw[:at]
               + chunk(b"tEXt", b"Software\x00an optimiser was here")
               + raw[at:])
    open(target, "wb").write(planted)
    expect_raises("a chunk planted into a committed icon, pixels untouched",
                  lambda: gen.check_against(committed))

    print("self-test passed: every guard fails when the thing it guards breaks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
