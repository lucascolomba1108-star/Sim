"""Generates the 52 card face textures + card back (PNG, transparent rounded corners).
Run once with regular Python + Pillow:  python3 make_cards.py
Textures are already committed, so you only need this to change the card design."""
import math
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "textures")
SS = 2                      # supersampling
W, H = 630 * SS, 880 * SS   # 63 x 88 mm poker card, 10 px/mm
R = 36 * SS                 # corner radius
RANK_FONT = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
SUIT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FACE_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SUITS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
RED, BLACK = (200, 22, 32, 255), (18, 18, 22, 255)

L, C, Rr = 0.30, 0.50, 0.70
PIPS = {
    "2": [(C, .20), (C, .80)],
    "3": [(C, .20), (C, .50), (C, .80)],
    "4": [(L, .20), (Rr, .20), (L, .80), (Rr, .80)],
}
PIPS["5"] = PIPS["4"] + [(C, .50)]
PIPS["6"] = PIPS["4"] + [(L, .50), (Rr, .50)]
PIPS["7"] = PIPS["6"] + [(C, .35)]
PIPS["8"] = PIPS["6"] + [(C, .35), (C, .65)]
PIPS["9"] = PIPS["4"] + [(L, .40), (Rr, .40), (L, .60), (Rr, .60), (C, .50)]
PIPS["10"] = PIPS["4"] + [(L, .40), (Rr, .40), (L, .60), (Rr, .60), (C, .30), (C, .70)]


def font(path, size):
    return ImageFont.truetype(path, size)


def base(fill):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], R, fill=fill)
    return img, d


def glyph(img, text, fnt, color, cx, cy, flip=False):
    """Draws text centred at (cx, cy); optionally rotated 180 deg."""
    bbox = fnt.getbbox(text)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tile = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((4 - bbox[0], 4 - bbox[1]), text, font=fnt, fill=color)
    if flip:
        tile = tile.rotate(180)
    img.alpha_composite(tile, (int(cx - tile.width / 2), int(cy - tile.height / 2)))


def face(rank, suit):
    img, d = base((252, 251, 247, 255))
    col = RED if suit in "HD" else BLACK
    s = SUITS[suit]
    # corner indices (top-left and rotated bottom-right)
    rf = font(RANK_FONT, (70 if rank == "10" else 82) * SS)
    sf = font(SUIT_FONT, 62 * SS)
    for flip in (False, True):
        cx, ry, sy = 62 * SS, 68 * SS, 140 * SS
        if flip:
            glyph(img, rank, rf, col, W - cx, H - ry, True)
            glyph(img, s, sf, col, W - cx, H - sy, True)
        else:
            glyph(img, rank, rf, col, cx, ry)
            glyph(img, s, sf, col, cx, sy)
    if rank == "A":
        glyph(img, s, font(SUIT_FONT, 330 * SS), col, W / 2, H / 2)
    elif rank in PIPS:
        pf = font(SUIT_FONT, 120 * SS)
        for (px, py) in PIPS[rank]:
            glyph(img, s, pf, col, px * W, py * H, flip=py > 0.5)
    else:
        court(img, rank, suit, col)
    return img


GOLD = (201, 158, 58, 255)
GOLD_LIGHT = (232, 196, 106, 255)


def crown(d, cx, cy, w, kind, col):
    """Crown (K), tiara (Q) or plumed star (J), centred on (cx, cy)."""
    h = w * 0.55
    top, base = cy - h / 2, cy + h / 2
    if kind == "J":
        pts = []
        for i in range(8):
            r = w * (0.5 if i % 2 == 0 else 0.2)
            a = math.pi / 2 + i * math.pi / 4
            pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
        d.polygon(pts, fill=GOLD, outline=col, width=3 * SS)
        d.ellipse([cx - w * 0.09, cy - w * 0.09, cx + w * 0.09, cy + w * 0.09], fill=col)
        return
    tips = 5 if kind == "K" else 3
    pts = [(cx - w / 2, base)]
    for i in range(tips):
        x = cx - w / 2 + w * i / (tips - 1)
        tall = (i == tips // 2) and kind == "K"
        pts.append((x, top - (h * 0.18 if tall else 0)))
        if i < tips - 1:
            pts.append((x + w / (tips - 1) / 2, top + h * (0.5 if kind == "K" else 0.62)))
    pts.append((cx + w / 2, base))
    d.polygon(pts, fill=GOLD, outline=col, width=3 * SS)
    band = h * 0.22
    d.rectangle([cx - w / 2, base - band, cx + w / 2, base], fill=GOLD_LIGHT, outline=col, width=3 * SS)
    for i in range(tips):
        x = cx - w / 2 + w * i / (tips - 1)
        tall = (i == tips // 2) and kind == "K"
        y = top - (h * 0.18 if tall else 0)
        r = w * 0.055
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)
    for i in range(3):    # jewels on the band
        x = cx - w * 0.25 + w * 0.25 * i
        r = band * 0.28
        d.ellipse([x - r, base - band / 2 - r, x + r, base - band / 2 + r], fill=col)


def court(img, rank, suit, col):
    """Double-headed court card: ornate frame, crown/plume, letter, mirrored halves."""
    mx, my = 118 * SS, 132 * SS
    fw, fh = W - 2 * mx, H - 2 * my
    panel = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle([0, 0, fw - 1, fh - 1], 16 * SS, fill=(250, 243, 226, 255))
    half = Image.new("RGBA", (fw, fh // 2), (0, 0, 0, 0))
    hd = ImageDraw.Draw(half)
    for i in range(14):    # soft gold rays behind the emblem
        a = -math.pi * i / 13
        x1 = fw / 2 + math.cos(a) * fw
        y1 = fh * 0.2 + math.sin(a) * fw
        hd.line([(fw / 2, fh * 0.2), (x1, y1)], fill=(236, 214, 160, 255), width=10 * SS)
    crown(hd, fw / 2, fh * 0.13, fw * 0.42, rank, col)
    glyph(half, rank, font(FACE_FONT, 150 * SS), col, fw / 2, fh * 0.3)
    sf = font(SUIT_FONT, 54 * SS)
    glyph(half, SUITS[suit], sf, col, fw * 0.2, fh * 0.3)
    glyph(half, SUITS[suit], sf, col, fw * 0.8, fh * 0.3)
    panel.alpha_composite(half, (0, 0))
    panel.alpha_composite(half.rotate(180), (0, fh - half.height))
    pd = ImageDraw.Draw(panel)
    pd.line([(fw * 0.08, fh / 2), (fw * 0.92, fh / 2)], fill=GOLD, width=3 * SS)
    r = 14 * SS
    pd.polygon([(fw / 2, fh / 2 - r), (fw / 2 + r, fh / 2), (fw / 2, fh / 2 + r), (fw / 2 - r, fh / 2)], fill=col)
    mask = Image.new("L", (fw, fh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, fw - 1, fh - 1], 16 * SS, fill=255)
    img.paste(panel, (mx, my), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([mx, my, mx + fw, my + fh], 16 * SS, outline=col, width=5 * SS)
    d.rounded_rectangle([mx + 9 * SS, my + 9 * SS, mx + fw - 9 * SS, my + fh - 9 * SS], 12 * SS,
                        outline=GOLD, width=2 * SS)


def back():
    img, d = base((252, 251, 247, 255))
    m = 26 * SS
    d.rounded_rectangle([m, m, W - m, H - m], R - m // 2, fill=(150, 22, 30, 255))
    inner = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    di = ImageDraw.Draw(inner)
    step = 34 * SS
    for i in range(-H, W + H, step):
        di.line([(i, 0), (i + H, H)], fill=(255, 210, 210, 70), width=4 * SS)
        di.line([(i, 0), (i - H, H)], fill=(255, 210, 210, 70), width=4 * SS)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([m + 10 * SS, m + 10 * SS, W - m - 10 * SS, H - m - 10 * SS], R - m // 2, fill=255)
    img.paste(inner, (0, 0), Image.composite(inner.getchannel("A"), mask, mask).point(lambda v: v))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([m + 10 * SS, m + 10 * SS, W - m - 10 * SS, H - m - 10 * SS], R - m // 2,
                        outline=(232, 196, 106, 255), width=5 * SS)
    cx, cy, r = W / 2, H / 2, 90 * SS
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(120, 14, 22, 255), outline=(232, 196, 106, 255), width=5 * SS)
    glyph(img, "21", font(RANK_FONT, 100 * SS), (232, 196, 106, 255), cx, cy)
    return img


def save(img, name):
    img.resize((W // SS, H // SS), Image.LANCZOS).save(os.path.join(OUT, name + ".png"))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for s in SUITS:
        for r in RANKS:
            save(face(r, s), r + s)
    save(back(), "back")
    print("wrote", len(os.listdir(OUT)), "textures to", OUT)
