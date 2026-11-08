"""Hand definitions, blackjack rules and the shared timeline for every video.

Used by both the Blender renderer (blackjack3d.py) and the video composer
(make_videos.py), so the 3D animation and the on-screen graphics always agree.

Rules shown on the felt: dealer draws to 16 and stands on all 17s (S17).
Each hand has a fixed shoe order, so the HIT and STAND videos are the two
honest "what if" branches of the same deal: if the player hits, they take the
next card and the dealer continues from there; if the player stands, the dealer
draws the cards from the top of the shoe.
"""

FPS = 30

# ------------------------------------------------------------------ the hands
# player: two cards, up: dealer up card, hole: dealer face-down card,
# shoe: next cards in the shoe (player hit first, then dealer draws).
# Card codes: rank (A 2-10 J Q K) + suit (S H D C).
HANDS = [
    dict(player=["10S", "6H"], up="10C", hole="7S", shoe=["5D", "9C", "2H"]),
    dict(player=["AS", "7D"], up="9H", hole="KC", shoe=["3S", "8C", "6D"]),
    dict(player=["9C", "3D"], up="4S", hole="10H", shoe=["10C", "8D", "5S"]),
    dict(player=["8H", "7C"], up="7D", hole="JS", shoe=["4C", "9S", "2D"]),
    dict(player=["10D", "3C"], up="6C", hole="QH", shoe=["KS", "2H", "7C"]),
    dict(player=["10H", "2S"], up="2D", hole="9S", shoe=["9H", "8C", "4D"]),
    dict(player=["AC", "6S"], up="8S", hole="9D", shoe=["3H", "10C", "5H"]),
    dict(player=["QC", "6D"], up="9C", hole="7H", shoe=["6C", "10S", "3D"]),
    dict(player=["7D", "5C"], up="3H", hole="10C", shoe=["8H", "4S", "9D"]),
    dict(player=["10C", "4H"], up="5D", hole="10D", shoe=["JH", "3S", "8S"]),
    dict(player=["KD", "5S"], up="10H", hole="8C", shoe=["6D", "2C", "9H"]),
    dict(player=["AH", "8C"], up="6S", hole="10S", shoe=["2C", "5H", "7D"]),
    dict(player=["9H", "4D"], up="2C", hole="8S", shoe=["7S", "10D", "6H"]),
    dict(player=["JS", "6C"], up="AD", hole="6H", shoe=["4H", "5C", "10C"]),
    dict(player=["AD", "6C"], up="2H", hole="10C", shoe=["4S", "9C", "3H"]),
    dict(player=["5H", "7S"], up="6D", hole="5C", shoe=["9S", "KH", "4C"]),
    dict(player=["9D", "6S"], up="10S", hole="9C", shoe=["3C", "QD", "2S"]),
    dict(player=["QH", "2C"], up="5C", hole="10H", shoe=["10S", "7H", "8D"]),
    dict(player=["AS", "7H"], up="2S", hole="7D", shoe=["10H", "4C", "9H"]),
    dict(player=["8C", "5D"], up="9D", hole="QS", shoe=["8H", "6S", "2D"]),
]


# ------------------------------------------------------------------ rules
def rank(code):
    return code[:-1]


def value(code):
    r = rank(code)
    if r == "A":
        return 11
    if r in ("J", "Q", "K"):
        return 10
    return int(r)


def total(cards):
    """(best total, soft) with aces counted as 11 while that does not bust."""
    t = sum(value(c) for c in cards)
    aces = sum(1 for c in cards if rank(c) == "A")
    while t > 21 and aces:
        t -= 10
        aces -= 1
    return t, aces > 0


def total_label(cards):
    t, soft = total(cards)
    if t > 21:
        return "BUST"
    if t == 21 and len(cards) == 2:
        return "BLACKJACK"
    if soft and t < 21:
        return f"SOFT {t}"
    return str(t)


def up_label(code):
    return "A" if rank(code) == "A" else str(value(code))


def short_label(cards):
    """'16', 'soft 18' - for sentences."""
    t, soft = total(cards)
    return f"soft {t}" if soft and t < 21 else str(t)


def basic_strategy(cards, up):
    """Hit/stand basic strategy, multi-deck, dealer stands on soft 17."""
    t, soft = total(cards)
    u = value(up)
    if soft:
        if t >= 19:
            return "STAND"
        if t == 18:
            return "STAND" if u <= 8 else "HIT"
        return "HIT"
    if t >= 17:
        return "STAND"
    if t >= 13:
        return "STAND" if u <= 6 else "HIT"
    if t == 12:
        return "STAND" if 4 <= u <= 6 else "HIT"
    return "HIT"


def play(hand, action):
    """Plays one branch. The player takes at most one card (the viewer's single decision)."""
    shoe = list(hand["shoe"])
    player = list(hand["player"])
    dealer = [hand["up"], hand["hole"]]
    steps = []
    if action == "HIT":
        c = shoe.pop(0)
        player.append(c)
        steps.append(("player_draw", c))
    pt, _ = total(player)
    if pt > 21:
        steps.append(("settle", "bust"))
        steps.append(("dealer_reveal", hand["hole"]))
        result = "bust"
    else:
        steps.append(("dealer_reveal", hand["hole"]))
        while total(dealer)[0] < 17:
            c = shoe.pop(0)
            dealer.append(c)
            steps.append(("dealer_draw", c))
        dt = total(dealer)[0]
        result = "win" if dt > 21 or pt > dt else ("lose" if pt < dt else "push")
        steps.append(("settle", result))
    return dict(action=action, player=player, dealer=dealer, steps=steps, result=result)


# ------------------------------------------------------------------ table layout (metres)
CW, CH = 0.063, 0.088
P_ROW = (-0.045, -0.012)      # first player card
D_ROW = (-0.045, 0.188)       # dealer up card
STEP_X, STEP_Y = 0.032, 0.005
BET_POS = (0.0, -0.105)
PAYOUT_POS = (0.05, -0.11)
BET_RING_R = 0.05
YAW_JITTER = [-3.0, 2.0, 4.0, -2.0, 3.0, -1.0]


def player_slot(i):
    return (P_ROW[0] + i * STEP_X, P_ROW[1] + i * STEP_Y)


def dealer_slot(i):
    return (D_ROW[0] + i * STEP_X, D_ROW[1] + i * STEP_Y)


# ------------------------------------------------------------------ timelines (frames @ 30 fps)
DEAL, FLIP, CHIP = 14, 13, 24
EP_INTRO, EP_CRANE, EP_HOLD, EP_END = 75, 60, 225, 210     # hold and end card are stills: free to lengthen
EP_TOTAL = EP_INTRO + EP_CRANE + EP_HOLD + EP_END
CRANE_DEALS = [4, 14, 24, 34]          # P1, D1(up), P2, D2(hole) within the crane shot
OUT_CTX = 75                            # recap at the start of the HIT / STAND videos
OUT_LESSON = 120


def outcome_timeline(hand, action):
    b = play(hand, action)
    f = OUT_CTX + 8
    events = []
    pcount, dcount = len(hand["player"]), 2
    for step in b["steps"]:
        kind = step[0]
        if kind == "player_draw":
            events.append(dict(kind=kind, card=step[1], slot=pcount, start=f, land=f + DEAL))
            pcount += 1
            f += DEAL + 22
        elif kind == "dealer_reveal":
            events.append(dict(kind=kind, card=step[1], slot=1, start=f, land=f + FLIP))
            f += FLIP + 20
        elif kind == "dealer_draw":
            events.append(dict(kind=kind, card=step[1], slot=dcount, start=f, land=f + DEAL))
            dcount += 1
            f += DEAL + 20
        elif kind == "settle":
            moves = step[1] in ("win", "lose", "bust")
            events.append(dict(kind=kind, result=step[1], start=f,
                               chips_start=f + 14 if moves else None,
                               chips_end=f + 14 + CHIP if moves else None))
            f += (14 + CHIP + 16) if moves else 30
    lesson_start = f + 36
    return dict(branch=b, events=events, lesson_start=lesson_start,
                total=lesson_start + OUT_LESSON)


def describe(hand):
    """Short facts used by the on-screen text."""
    return dict(player=total_label(hand["player"]), player_short=short_label(hand["player"]),
                up=up_label(hand["up"]), best=basic_strategy(hand["player"], hand["up"]))


def check(hand):
    cards = hand["player"] + [hand["up"], hand["hole"]] + hand["shoe"]
    assert len(cards) == len(set(cards)), f"duplicate card in {hand}"
    for c in cards:
        assert rank(c) in ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"), c
        assert c[-1] in "SHDC", c


for _h in HANDS:
    check(_h)


if __name__ == "__main__":
    for i, h in enumerate(HANDS, 1):
        d = describe(h)
        line = f"#{i:02d} {'-'.join(h['player']):>8} ({d['player']:>8}) vs {h['up']:>3}  best={d['best']:<5}"
        for a in ("HIT", "STAND"):
            b = play(h, a)
            tl = outcome_timeline(h, a)
            line += (f" | {a}: P {total_label(b['player']):>7} D {total_label(b['dealer']):>5}"
                     f" -> {b['result']:<4} ({tl['total'] / FPS:4.1f}s)")
        print(line)
