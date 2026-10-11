# Builds a PDF that draws many small soft sprites the way Skia's PDF backend
# appears to write an image drawn with a clamped shader: every sprite is a
# tiling pattern whose tile is the whole page (the image, plus four
# 1-pixel-wide strips stretched from its edges to the edges of the page), and
# the page fills a rectangle the size of the sprite with it.
#
# usage: make_repro.py OUT.pdf [SPRITES]     (needs pikepdf)
import math, random, sys, zlib
import pikepdf
from pikepdf import Array, Dictionary, Name

out = sys.argv[1]
count = int(sys.argv[2]) if len(sys.argv) > 2 else 131
W, H, S = 1298, 1836, 100
random.seed(1)
pdf = pikepdf.new()

def image(width, height, alpha):
    """A white image with `alpha` (one byte per pixel, row by row) as its soft mask."""
    mask = pdf.make_stream(zlib.compress(alpha), Type=Name.XObject, Subtype=Name.Image, Width=width, Height=height,
                           ColorSpace=Name.DeviceGray, BitsPerComponent=8, Filter=Name.FlateDecode)
    return pdf.make_stream(zlib.compress(b"\xff" * (width * height * 3)), Type=Name.XObject, Subtype=Name.Image,
                           Width=width, Height=height, ColorSpace=Name.DeviceRGB, BitsPerComponent=8,
                           Filter=Name.FlateDecode, SMask=mask)

# A soft round speck: opaque in the middle and transparent at every edge, so
# the four edge strips are transparent as well.
c = (S - 1) / 2
alpha = bytes(int(255 * max(0.0, 1 - math.hypot(x - c, y - c) / c) ** 2) for y in range(S) for x in range(S))
row = lambda r: alpha[r * S:(r + 1) * S]
col = lambda k: bytes(alpha[r * S + k] for r in range(S))
xobjects = pdf.make_indirect(Dictionary(
    Sprite=image(S, S, alpha), Left=image(1, S, col(0)), Right=image(1, S, col(S - 1)),
    Top=image(S, 1, row(0)), Bottom=image(S, 1, row(S - 1))))
gstate = pdf.make_indirect(Dictionary(Type=Name.ExtGState, BM=Name.Normal, ca=1))
resources = pdf.make_indirect(Dictionary(XObject=xobjects, ExtGState=Dictionary(G=gstate)))

patterns = Dictionary()
# The page works top-down, as Skia does; so do the patterns, through their matrix.
content = [f"1 0 0 -1 0 {H} cm", f"0.06 0.06 0.1 rg 0 0 {W} {H} re f"]
for n in range(count):
    x, y = random.uniform(0, W - S), random.uniform(0, H - S)
    # An image fills the unit square, upside down in a top-down space: hence the negative heights.
    tile = "\n".join([
        f"q {S} 0 0 {-S} {x:.5f} {y + S:.5f} cm /G gs /Sprite Do Q",
        f"q {x:.5f} 0 0 {-S} 0 {y + S:.5f} cm /G gs /Left Do Q",
        f"q {W - x - S:.5f} 0 0 {-S} {x + S:.5f} {y + S:.5f} cm /G gs /Right Do Q",
        f"q {S} 0 0 {-y:.5f} {x:.5f} {y:.5f} cm /G gs /Top Do Q",
        f"q {S} 0 0 {-(H - y - S):.5f} {x:.5f} {H} cm /G gs /Bottom Do Q",
    ])
    patterns[f"/P{n}"] = pdf.make_stream(
        tile.encode(), Type=Name.Pattern, PatternType=1, PaintType=1, TilingType=1, BBox=Array([0, 0, W, H]),
        XStep=W, YStep=H, Matrix=Array([1, 0, 0, -1, 0, H]), Resources=resources)
    content.append(f"q 1 0 0 1 {x:.5f} {y:.5f} cm /Pattern cs /P{n} scn /G gs 0 0 {S} {S} re f Q")

page = pdf.add_blank_page(page_size=(W, H))
page.Resources = Dictionary(Pattern=patterns, ExtGState=Dictionary(G=gstate))
page.Contents = pdf.make_stream("\n".join(content).encode())
pdf.save(out, object_stream_mode=pikepdf.ObjectStreamMode.disable, compress_streams=True)
