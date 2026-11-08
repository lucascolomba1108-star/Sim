"""Generates the 52 card face textures + card back (PNG, transparent rounded corners).
Run once with regular Python + Pillow:  python3 make_cards.py
Textures are already committed, so you only need this to change the card design."""
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
    else:  # J Q K: framed panel with big letter
        m = 120 * SS
        d.rounded_rectangle([m, m + 20 * SS, W - m, H - m - 20 * SS], 18 * SS,
                            outline=col, width=5 * SS, fill=(248, 240, 220, 255))
        glyph(img, rank, font(FACE_FONT, 250 * SS), col, W / 2, H / 2 - 60 * SS)
        glyph(img, s, font(SUIT_FONT, 150 * SS), col, W / 2, H / 2 + 150 * SS)
    return img


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
