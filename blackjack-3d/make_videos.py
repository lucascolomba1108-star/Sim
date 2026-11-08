"""Builds the three finished videos of a hand from the 3D renders.

  hand01_1_episode.mp4   context intro -> deal -> "HIT or STAND?" -> end card with two reel slots
  hand01_2_hit.mp4       recap -> what happens if you HIT -> the math
  hand01_3_stand.mp4     recap -> what happens if you STAND -> the math

Usage:  python3 make_videos.py 1 [--render render] [--out videos] [--only episode,hit,stand]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import composite as C  # noqa: E402
import hands as H  # noqa: E402

W, HT, FPS = 1080, 1920, H.FPS
COL = dict(hit="#3EDC8A", stand="#FF5A5F", push="#9DB4FF", gold="#F5D27A", white="#FFFFFF")
SLOT_CORNER = dict(x=36, y=262, w=180, h=320)
INTRO_ZOOM = 1.08                      # intro still is rendered 8% wider: ends on crane frame 0
HOLD_ZOOM = (1.0, 1.10)                # slow push-in on the hold plate (110% overscan)
OUT_ZOOM = (1.0, 1.06)


# ----------------------------------------------------------------------------- helpers
def ease_in_out(t):
    t = min(1.0, max(0.0, t))
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ramp(n, f0, f1, z0, z1):
    return [z0 + (z1 - z0) * ease_in_out((f - f0) / max(1, f1 - f0)) for f in range(n)]


RANK_NAME = {"A": "an Ace", "J": "a Jack", "Q": "a Queen", "K": "a King", "8": "an 8"}


def card_name(code):
    r = H.rank(code)
    return RANK_NAME.get(r, f"a {r}")


def badge_style(label, final=None):
    s = dict(label=label)
    if label in ("21", "BLACKJACK"):
        s.update(bg="#F5C542", fg="#0B0C0E", border="#FFE7A0", glow="rgba(245,197,66,0.9)")
    if label == "BUST":
        s.update(bg="#E5484D", fg="#FFFFFF", border="#FF9A9D", glow="rgba(229,72,77,0.8)", shake=True)
    if final == "win":
        s.update(bg="#1F9D5C", fg="#FFFFFF", border="#7DF0B3", glow="rgba(62,220,138,0.8)")
    if final == "push":
        s.update(bg="#3A4A7A", fg="#FFFFFF", border="#9DB4FF")
    return s


def row_anchor(boxes, i=0):
    x0, y0, x1, y1 = boxes[i]
    return x0 - 0.016, (y0 + y1) / 2


def mid_y(anchors, z):
    v = (anchors["dealer_box"][0][3] + anchors["player_box"][0][1]) / 2
    return HT / 2 + (v - 0.5) * HT * z


# ----------------------------------------------------------------------------- overlay plans
def tag(text, y, t0, t1, size=30, icon=True):
    return dict(type="tag", text=text, x=W / 2, y=y, t0=t0, t1=t1, size=size, icon=icon)


def title(lines, y, t0, t1, **kw):
    return dict(type="title", lines=lines, y=y, t0=t0, t1=t1, **kw)


def seg(t, size, c=COL["white"], w=900, **kw):
    return dict(t=t, size=size, c=c, w=w, **kw)


def body(t, size=42, c="rgba(255,255,255,0.92)", w=600):
    return dict(t=t, size=size, c=c, w=w, fam="body", ls=0)


def corner_slot(t0, t1):
    return dict(type="slot", label="PREVIOUSLY", lsize=22, color=COL["gold"], r=22, lw=3,
                t0=t0, t1=t1, fin=14, fout=12, **SLOT_CORNER)


def episode_plan(no, hand, anchors):
    d = H.describe(hand)
    n = H.EP_TOTAL
    i0, c0 = H.EP_INTRO, H.EP_INTRO + H.EP_CRANE          # 75, 135
    end0 = c0 + H.EP_HOLD                                 # 330
    zoom = [1.0] * n
    zh = ramp(n, c0, n - 1, *HOLD_ZOOM)
    for f in range(c0, n):
        zoom[f] = zh[f]
    has_prev = no > 1
    cx = 640 if has_prev else W / 2
    soft = "SOFT" in d["player"]
    you = f"You have {d['player_short']}" + (f" ({H.rank(hand['player'][0])}+{H.rank(hand['player'][1])})." if soft else ".")
    E = [
        dict(type="scrim", top=700, full=0.28, t0=0, t1=74, fin=0, fout=14),
        dict(type="scrim", top=620, t0=c0, t1=end0, fin=16, fout=10),
        tag("INTERACTIVE BLACKJACK", 720, 3, 72),
        title([[seg("YOU MAKE", 116)], [seg("THE CALL.", 116, COL["gold"])]], 860, 9, 72, lh=120),
        title([[body("One hand. Two choices. Your call.", 42)]], 1090, 18, 72, rise=24),
        tag(f"HAND {no}", 1190, 24, 72, size=28, icon=False),
        tag(f"HAND {no}", 300, 82, c0 + 10, size=28, icon=False),
        dict(type="badge", who="DEALER", u=row_anchor(anchors["dealer_box"])[0], v=row_anchor(anchors["dealer_box"])[1],
             states=[dict(f=c0 + 6, **badge_style(d["up"]))], t0=c0 + 6, t1=end0, fin=10),
        dict(type="badge", who="YOU", u=row_anchor(anchors["player_box"])[0], v=row_anchor(anchors["player_box"])[1],
             states=[dict(f=c0 + 12, **badge_style(d["player"]))], t0=c0 + 12, t1=end0, fin=10),
        dict(type="caption", x=cx, y=340, t0=c0 + 18, t1=c0 + 90,
             lines=[dict(t=you, size=46, w=800), dict(t=f"Dealer shows {d['up'] if d['up'] != 'A' else 'an Ace'}.", size=46, w=800)]),
        title([[seg("HIT", 132, COL["hit"]), seg("or", 60, w=700, dy=9), seg("STAND?", 132, COL["stand"])]],
              350, c0 + 93, end0, pop=True, pulse=True, rise=0, gap=24),
        title([[body("What's your move?", 46, w=700)]], 482, c0 + 103, end0, rise=20),
        # end card: the two decision reels side by side
        title([[seg("YOUR MOVE", 112)]], 330, end0 + 6, n, rise=30),
        title([[body("Pick a reel to see what happens", 42)]], 436, end0 + 12, n, rise=20),
        dict(type="slot", label="HIT", lsize=36, color=COL["hit"], x=130, y=560, w=380, h=676, t0=end0 + 14, t1=n, fin=14),
        dict(type="slot", label="STAND", lsize=36, color=COL["stand"], x=570, y=560, w=380, h=676, t0=end0 + 20, t1=n, fin=14),
        title([[body(f"Hand {no}  ·  {d['player_short']} vs dealer {d['up']}", 36, "rgba(255,255,255,0.8)")]],
              1306, end0 + 26, n, rise=16),
    ]
    for e in E:
        if e["type"] == "caption":
            e["x"], e["maxw"] = cx, (780 if has_prev else 960)
    if has_prev:
        E.append(corner_slot(6, c0 + 82))
    return dict(frames=n, zoom=zoom, elements=E)


def outcome_plan(no, hand, anchors, action):
    d = H.describe(hand)
    tl = H.outcome_timeline(hand, action)
    b, n, ls = tl["branch"], tl["total"], tl["lesson_start"]
    zoom = ramp(n, 0, n - 1, *OUT_ZOOM)
    acol = COL["hit"] if action == "HIT" else COL["stand"]
    cx = 640
    E = [
        dict(type="scrim", full=0.55, t0=0, t1=70, fin=0, fout=16),
        dict(type="scrim", top=560, t0=70, t1=ls, fin=14, fout=10),
        tag("INTERACTIVE BLACKJACK", 700, 2, 70),
        title([[seg("YOU CHOSE", 70, w=800)]], 820, 6, 70, rise=30),
        title([[seg(action, 196, acol, glow=acol)]], 968, 10, 70, pop=True, rise=0),
        title([[body(f"Hand {no}  ·  You had {d['player_short']} vs dealer {d['up']}", 42)]], 1118, 18, 70, rise=20),
        corner_slot(6, ls),
    ]
    # running totals for the two badges
    player, dealer = list(hand["player"]), [hand["up"]]
    p_states = [dict(f=84, **badge_style(d["player"]))]
    d_states = [dict(f=80, **badge_style(d["up"]))]
    caps = []
    for ev in tl["events"]:
        k, land = ev["kind"], ev.get("land")
        if k == "player_draw":
            player.append(ev["card"])
            lab = H.total_label(player)
            p_states.append(dict(f=land, **badge_style(lab)))
            t = H.total(player)[0]
            line = f"You draw {card_name(ev['card'])}: {t}." if t <= 21 else f"You draw {card_name(ev['card'])}: {t}. Bust!"
            caps.append((land + 2, line))
        elif k in ("dealer_reveal", "dealer_draw"):
            dealer.append(ev["card"])
            lab = H.total_label(dealer)
            d_states.append(dict(f=land, **badge_style(lab)))
            t = H.total(dealer)[0]
            verb = "flips" if k == "dealer_reveal" else "draws"
            if H.total(player)[0] > 21:            # hand already over: the reveal is just for show
                line = f"Dealer flips {card_name(ev['card'])}: had {t}."
            elif t > 21:
                line = f"Dealer {verb} {card_name(ev['card'])}: {t}. Dealer busts!"
            elif t < 17:
                line = f"Dealer {verb} {card_name(ev['card'])}: {t}. Must hit."
            else:
                line = f"Dealer {verb} {card_name(ev['card'])}: {t}. Stands."
            caps.append((land + 2, line))
        elif k == "settle":
            res, s0 = ev["result"], ev["start"]
            pt, dt = H.total(player)[0], H.total(dealer)[0]
            if res == "win":
                p_states.append(dict(f=s0, **badge_style(H.total_label(player), "win")))
                sub = "Dealer busts!" if dt > 21 else f"{pt} beats {dt}"
                ban = dict(text="YOU WIN", color=COL["hit"], sub=sub)
            elif res == "push":
                p_states.append(dict(f=s0, **badge_style(H.total_label(player), "push")))
                d_states.append(dict(f=s0, **badge_style(H.total_label(dealer), "push")))
                ban = dict(text="PUSH", color=COL["push"], sub="Tie. Your bet comes back.")
            elif res == "bust":
                ban = dict(text="BUST", color=COL["stand"], sub="Over 21. The house takes it.")
            else:
                ban = dict(text="YOU LOSE", color=COL["stand"], sub=f"{dt} beats {pt}")
            caps.append((s0 - 1, None))
            yb = mid_y(anchors, zoom[s0])
            E.append(dict(type="banner", y=yb, t0=s0, t1=ls - 4, fin=0, fout=12, size=150, **ban))
            E.append(dict(type="flash", color=ban["color"], y=yb, t0=s0, t1=s0 + 18, fin=0, fout=0, alpha=0.3))
            if res == "win":
                E.append(dict(type="particles", y=yb, t0=s0, t1=s0 + 70, fin=0, fout=0, n=80, seed=no * 7 + 3))
    # captions: each one stays until the next one
    for i, (f0, line) in enumerate(caps):
        if line is None:
            continue
        f1 = caps[i + 1][0] - 2 if i + 1 < len(caps) else ls
        E.append(dict(type="caption", x=cx, maxw=780, y=340, t0=f0, t1=f1, fin=8, fout=8,
                      lines=[dict(t=line, size=44, w=800)]))
    du, dv = row_anchor(anchors["dealer_box"])
    pu, pv = row_anchor(anchors["player_box"])
    E.append(dict(type="badge", who="DEALER", u=du, v=dv, states=d_states, t0=80, t1=ls, fin=10))
    E.append(dict(type="badge", who="YOU", u=pu, v=pv, states=p_states, t0=84, t1=ls, fin=10))
    # the lesson
    best = d["best"]
    ok = action == best
    res = b["result"]
    verb = "hit" if action == "HIT" else "stood"
    if ok:
        verdict = {"win": f"You {verb}: right call, and it paid off.",
                   "push": f"You {verb}: right call. A push this time."}.get(res, f"You {verb}: right call. Unlucky cards.")
    else:
        verdict = {"win": f"You {verb}: wrong call... but lucky!",
                   "push": f"You {verb}: wrong call, saved by a push."}.get(res, f"You {verb}: wrong call.")
    bcol = COL["hit"] if best == "HIT" else COL["stand"]
    E += [
        title([[seg("THE MATH SAYS", 36, COL["gold"], w=800, ls=7, fam="body")]], 560, ls + 4, n, rise=20),
        title([[seg(best, 180, bcol, glow=bcol)]], 700, ls + 8, n, pop=True, rise=0),
        title([[body(f"on {d['player_short']} vs dealer {d['up']}", 46, w=700)]], 838, ls + 14, n, rise=16),
        dict(type="lesson", ok=ok, text=verdict, y=970, t0=ls + 22, t1=n, fin=12),
        title([[body("Basic strategy  ·  dealer stands on all 17s", 30, "rgba(255,255,255,0.62)", w=500)]], 1062, ls + 28, n, rise=10),
        tag(f"FOLLOW FOR HAND {no + 1}", 1220, ls + 36, n, size=30),
    ]
    blur = (ls, n)
    return dict(frames=n, zoom=zoom, elements=E, blur=blur)


# ----------------------------------------------------------------------------- frames
class Renders:
    def __init__(self, root, no):
        self.root = root
        self.shared = os.path.join(root, "shared")
        self.hand = os.path.join(root, f"hand{no:02d}")
        self.meta = json.load(open(os.path.join(self.hand, "meta.json")))
        self.smeta = json.load(open(os.path.join(self.shared, "meta.json")))
        self._hold = None

    def scale(self, arr):
        return arr.shape[1] / 1188.0

    def hold_full(self):
        if self._hold is None:
            bg = C.load(os.path.join(self.shared, "hold_bg.png"))
            rect = self.meta["hold"]["rect"]
            crop = C.load(os.path.join(self.hand, "hold.png"))
            self._hold = C.paste(bg, crop, rect, self.scale(bg))
        return self._hold

    def crane(self, f):
        bg = C.load(os.path.join(self.shared, "crane_bg", f"{f:04d}.png"))
        rect = self.meta["crane"]["rects"].get(str(f))
        if rect:
            crop = C.load(os.path.join(self.hand, "crane", f"{f:04d}.png"))
            bg = C.paste(bg, crop, rect, bg.shape[1] / 1080.0 * 1080 / 1188)
        return bg


def to_img(arr):
    return Image.fromarray(np.clip(arr + 0.5, 0, 255).astype(np.uint8))


def zoomed(img, z):
    sw, sh = img.size
    cw, ch = sw / z, sh / z
    x0, y0 = (sw - cw) / 2, (sh - ch) / 2
    return img.resize((W, HT), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


def soften(img, k):
    """End-card look: blur + dim, k in 0..1."""
    if k <= 0:
        return img
    out = img.filter(ImageFilter.GaussianBlur(22 * k))
    return Image.blend(out, Image.new("RGB", out.size, (0, 0, 0)), 0.5 * k)


class Encoder:
    def __init__(self, path):
        self.p = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{HT}",
             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
             "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
             "-movflags", "+faststart", path], stdin=subprocess.PIPE)

    def write(self, img):
        self.p.stdin.write(img.tobytes())

    def close(self):
        self.p.stdin.close()
        if self.p.wait() != 0:
            raise RuntimeError("ffmpeg failed")


def render_overlay(plan, tmp):
    pj = os.path.join(tmp, "plan.json")
    json.dump(plan, open(pj, "w"))
    od = os.path.join(tmp, "ov")
    subprocess.run(["node", os.path.join(HERE, "overlay", "render_overlay.js"), pj, od], check=True)
    return od


def compose_episode(R, plan, out):
    n = plan["frames"]
    c0 = H.EP_INTRO + H.EP_CRANE
    end0 = c0 + H.EP_HOLD
    with tempfile.TemporaryDirectory() as tmp:
        od = render_overlay(plan, tmp)
        enc = Encoder(out)
        intro = Image.open(os.path.join(R.shared, "intro.png")).convert("RGB")
        hold = to_img(R.hold_full())
        for f in range(n):
            if f < H.EP_INTRO:
                z = 1 + (INTRO_ZOOM - 1) * ease_in_out(f / (H.EP_INTRO - 1))
                bg = zoomed(intro, z)
            elif f < c0:
                bg = to_img(R.crane(f - H.EP_INTRO))
                if bg.size != (W, HT):
                    bg = bg.resize((W, HT), Image.LANCZOS)
            else:
                bg = soften(zoomed(hold, plan["zoom"][f]), ease_in_out((f - end0) / 14) if f >= end0 else 0)
            ov = Image.open(os.path.join(od, f"{f:04d}.png"))
            frame = bg.convert("RGBA")
            frame.alpha_composite(ov)
            enc.write(frame.convert("RGB"))
        enc.close()


def compose_outcome(R, plan, action, out):
    n = plan["frames"]
    info = R.meta[action.lower()]
    src, rects = info["src"], info["rects"]
    ls = plan["blur"][0]
    with tempfile.TemporaryDirectory() as tmp:
        od = render_overlay(plan, tmp)
        enc = Encoder(out)
        running = R.hold_full()
        sc = R.scale(running)
        for f in range(n):
            if src[f] == f and str(f) in rects and rects[str(f)]:
                crop = C.load(os.path.join(R.hand, action.lower(), f"{f:04d}.png"))
                running = C.paste(running, crop, rects[str(f)], sc)
            bg = soften(zoomed(to_img(running), plan["zoom"][f]), ease_in_out((f - ls) / 14) if f >= ls else 0)
            ov = Image.open(os.path.join(od, f"{f:04d}.png"))
            frame = bg.convert("RGBA")
            frame.alpha_composite(ov)
            enc.write(frame.convert("RGB"))
        enc.close()


def write_guide(videos):
    """GUIDE.md next to the videos: what each file is, where the slots are, captions."""
    sec = lambda f: f"{f / FPS:.1f}s"
    sc = SLOT_CORNER
    ep_corner_end = H.EP_INTRO + H.EP_CRANE + 82 + 12
    ep_end0 = H.EP_INTRO + H.EP_CRANE + H.EP_HOLD + 14
    lines = [
        "# Interactive Blackjack: videos", "",
        "Every hand has three Reels (1080x1920, 30 fps, no audio: add music in Edits) and a "
        "cover image for each (`*_cover.jpg`, upload it as the Reel cover).", "",
        "## Posting order (per hand)",
        "1. Post `handNN_2_hit.mp4` and `handNN_3_stand.mp4` (the two decision reels).",
        "2. In Edits, open `handNN_1_episode.mp4` and drop those two reels into the end-card slots "
        "(HIT on the left, STAND on the right). From hand 2 on, put the previous reels in the "
        "PREVIOUSLY corner slot.",
        "3. Post the episode. If your account can link reels, link it to both decision reels.", "",
        "## Slot positions (pixels on the 1080x1920 frame)",
        f"- PREVIOUSLY (corner): x {sc['x']}-{sc['x'] + sc['w']}, y {sc['y']}-{sc['y'] + sc['h']} "
        f"({sc['w']}x{sc['h']}, 9:16). Episode: 0.2s-{sec(ep_corner_end)}. "
        "HIT/STAND reels: from 0.2s until the lesson card (time listed per hand below).",
        f"- HIT (end card, left): x 130-510, y 560-1236 (380x676, 9:16). From {sec(ep_end0)} to the end (15.0s).",
        f"- STAND (end card, right): x 570-950, y 560-1236 (380x676). From {sec(ep_end0 + 6)} to the end.",
        "- Poll sticker (optional): during \"HIT or STAND?\" (7.6s-11.0s) the middle of the table, "
        "y ~760-1000, is left free for it.", "",
        "## Hands", "",
    ]
    for no, hand in enumerate(H.HANDS, 1):
        names = [f"hand{no:02d}_{s}.mp4" for s in ("1_episode", "2_hit", "3_stand")]
        if not any(os.path.exists(os.path.join(videos, n)) for n in names):
            continue
        d = H.describe(hand)
        hit, stand = H.outcome_timeline(hand, "HIT"), H.outcome_timeline(hand, "STAND")
        res = lambda tl: {"win": "WIN", "lose": "LOSE", "bust": "BUST", "push": "PUSH"}[tl["branch"]["result"]]
        cards = lambda cs: " ".join(cs)
        lines += [
            f"### Hand {no}: {d['player_short']} vs dealer {d['up']} (basic strategy: {d['best']})",
            f"- Cards: you {cards(hand['player'])} | dealer {hand['up']} + hole {hand['hole']}",
            f"- `{names[0]}` ({sec(H.EP_TOTAL)})",
            f"- `{names[1]}` ({sec(hit['total'])}): HIT -> you {H.total_label(hit['branch']['player'])}, "
            f"dealer {H.total_label(hit['branch']['dealer'])}: **{res(hit)}**. Corner slot until {sec(hit['lesson_start'])}.",
            f"- `{names[2]}` ({sec(stand['total'])}): STAND -> you {H.total_label(stand['branch']['player'])}, "
            f"dealer {H.total_label(stand['branch']['dealer'])}: **{res(stand)}**. Corner slot until {sec(stand['lesson_start'])}.",
            "- Captions:",
            f"  - Episode: `Hand #{no}: {d['player_short']} vs dealer {d['up']}. HIT or STAND? Pick your reel 👇 "
            f"#blackjack #cardgames #casino #interactive`",
            f"  - HIT: `Hand #{no}: you chose HIT. Did it pay off? 🃏 #blackjack #cardgames #casino`",
            f"  - STAND: `Hand #{no}: you chose STAND. Did it pay off? 🃏 #blackjack #cardgames #casino`",
            "",
        ]
    open(os.path.join(videos, "GUIDE.md"), "w").write("\n".join(lines))


def cover_plans(no, hand, anchors):
    """Single-frame overlay plans for the three covers. Key text sits inside the 3:4
    profile-grid crop (y 240-1680). The decision covers do not spoil the result."""
    d = H.describe(hand)
    on = dict(t0=-100, t1=100, fin=0, fout=0)
    du, dv = row_anchor(anchors["dealer_box"])
    pu, pv = row_anchor(anchors["player_box"])
    badges = [dict(type="badge", who="DEALER", u=du, v=dv, states=[dict(f=-100, **badge_style(d["up"]))], **on),
              dict(type="badge", who="YOU", u=pu, v=pv, states=[dict(f=-100, **badge_style(d["player"]))], **on)]
    ep = [dict(type="scrim", top=700, full=0.22, band=[700, 1050], bandAlpha=0.5, **on),
          dict(tag("INTERACTIVE BLACKJACK", 340, 0, 0), **on),
          dict(title([[seg(f"HAND {no}", 124, COL["gold"])]], 812, 0, 0), **on),
          dict(title([[seg("HIT", 100, COL["hit"]), seg("or", 48, w=700, dy=7), seg("STAND?", 100, COL["stand"])]], 938, 0, 0, gap=20), **on)
          ] + badges
    plans = {"episode": dict(frames=1, zoom=[1.0], elements=ep)}
    for action in ("HIT", "STAND"):
        acol = COL["hit"] if action == "HIT" else COL["stand"]
        plans[action.lower()] = dict(frames=1, zoom=[1.0], elements=[
            dict(type="scrim", full=0.5, **on),
            dict(tag("INTERACTIVE BLACKJACK", 640, 0, 0), **on),
            dict(title([[seg(f"HAND {no}", 92, COL["gold"])]], 770, 0, 0), **on),
            dict(title([[seg("YOU CHOSE", 70, w=800)]], 880, 0, 0), **on),
            dict(title([[seg(action, 200, acol, glow=acol)]], 1030, 0, 0), **on),
            dict(title([[body(f"{d['player_short']} vs dealer {d['up']}. Did it pay off?", 44, w=700)]], 1186, 0, 0), **on),
        ])
    return plans


def make_covers(R, no, hand, anchors, out_dir):
    bg = zoomed(to_img(R.hold_full()), 1.0)
    for name, plan in cover_plans(no, hand, anchors).items():
        with tempfile.TemporaryDirectory() as tmp:
            od = render_overlay(plan, tmp)
            frame = bg.convert("RGBA")
            frame.alpha_composite(Image.open(os.path.join(od, "0000.png")))
            idx = {"episode": 1, "hit": 2, "stand": 3}[name]
            frame.convert("RGB").save(os.path.join(out_dir, f"hand{no:02d}_{idx}_{name}_cover.jpg"), quality=95)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hand", type=int)
    ap.add_argument("--render", default=os.path.join(HERE, "render"))
    ap.add_argument("--out", default=os.path.join(HERE, "videos"))
    ap.add_argument("--only", default="episode,hit,stand")
    a = ap.parse_args()
    no = a.hand
    hand = H.HANDS[no - 1]
    R = Renders(a.render, no)
    anchors = R.meta["anchors"]
    os.makedirs(a.out, exist_ok=True)
    only = a.only.split(",")
    if "episode" in only:
        out = os.path.join(a.out, f"hand{no:02d}_1_episode.mp4")
        compose_episode(R, episode_plan(no, hand, anchors), out)
        print("wrote", out, flush=True)
    for i, action in ((2, "HIT"), (3, "STAND")):
        if action.lower() in only:
            out = os.path.join(a.out, f"hand{no:02d}_{i}_{action.lower()}.mp4")
            compose_outcome(R, outcome_plan(no, hand, anchors, action), action, out)
            print("wrote", out, flush=True)
    make_covers(R, no, hand, anchors, a.out)
    write_guide(a.out)


if __name__ == "__main__":
    main()
