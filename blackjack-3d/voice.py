"""Voice-over for the blackjack videos (ElevenLabs).

Writes a timed English script for every video of a hand, generates each line
with the ElevenLabs API, lays it on the frame where that moment happens, ducks
the card/chip sound effects under the voice and saves a voiced copy of each
video in videos_voice/ (the originals stay untouched, so both can be tested).

  python3 voice.py 1                       # hand 1: script + voice + videos
  python3 voice.py 1 2 3 --voice <voice_id>
  python3 voice.py 1 --script-only         # just print/write the script

Needs ELEVENLABS_API_KEY in the environment and network access to
api.elevenlabs.io. Optional: ELEVENLABS_VOICE_ID (defaults to "Adam", a deep
narrator voice). Generated lines are cached in voice_cache/, so re-runs and
other hands do not pay twice for the same sentence.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hands as H  # noqa: E402
import make_videos as M  # noqa: E402

FPS, SR = H.FPS, M.SR
DEFAULT_VOICE = "pNInz6obpgDQGcFmaJgB"      # "Adam" (ElevenLabs premade voice)
MODEL = "eleven_multilingual_v2"
SETTINGS = dict(stability=0.42, similarity_boost=0.8, style=0.35, use_speaker_boost=True)
CACHE = os.path.join(HERE, "voice_cache")

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
         10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen",
         17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty", 21: "twenty-one", 22: "twenty-two",
         23: "twenty-three", 24: "twenty-four", 25: "twenty-five", 26: "twenty-six"}
RANK = {"A": "ace", "J": "jack", "Q": "queen", "K": "king"}


def num(n):
    return WORDS.get(n, str(n))


def article(word):
    return ("an " if word[0] in "aeiou" else "a ") + word


def card_bare(code):
    r = H.rank(code)
    return (RANK[r] if r in RANK else num(int(r))).capitalize()


def spoken_total(cards):
    t, soft = H.total(cards)
    return ("soft " if soft and t < 21 else "") + num(t)


def up_spoken(code):
    return article("ace" if H.rank(code) == "A" else num(H.value(code)))


# ----------------------------------------------------------------------------- scripts
def episode_script(no, hand):
    c0 = H.EP_INTRO + H.EP_CRANE
    end0 = c0 + H.EP_HOLD
    intro = ("This is interactive blackjack. You make the call." if no == 1
             else f"Interactive blackjack. Hand {num(no)}. You make the call.")
    return [
        (4, intro),
        (c0 + 18, f"You've got {spoken_total(hand['player'])}. The dealer shows {up_spoken(hand['up'])}."),
        (c0 + 93, "Hit... or stand? Comment your move."),
        (end0 + 10, "Now pick your reel... and see what happens."),
    ]


def outcome_script(no, hand, action):
    """Lines in RENDER frames of the outcome timeline (mapped to display frames later)."""
    tl = H.outcome_timeline(hand, action)
    d = H.describe(hand)
    lines = [(8, f"You chose to {'hit' if action == 'HIT' else 'stand'}.")]
    player, dealer = list(hand["player"]), [hand["up"]]
    for ev in tl["events"]:
        k = ev["kind"]
        if k == "player_draw":
            player.append(ev["card"])
            t = H.total(player)[0]
            tail = f"{num(t).capitalize()}!" if t == 21 else (f"{num(t).capitalize()}. Bust!" if t > 21 else f"{num(t).capitalize()}.")
            lines.append((ev["land"] - 2, f"{card_bare(ev['card'])}... {tail}"))
        elif k in ("dealer_reveal", "dealer_draw"):
            dealer.append(ev["card"])
            t = H.total(dealer)[0]
            if H.total(player)[0] > 21:
                text = f"Dealer had {num(t)}."
            elif t > 21:
                text = f"{card_bare(ev['card'])}... dealer busts!"
            elif k == "dealer_reveal":
                text = f"Dealer, {num(t)}." + (" Must hit." if t < 17 else "")
            else:
                text = f"{card_bare(ev['card'])}... {num(t)}."
            lines.append((ev["land"] - 2, text))
        elif k == "settle":
            text = {"win": "You win!", "lose": "You lose.", "bust": "House wins.", "push": "Push."}[ev["result"]]
            lines.append((ev["start"] + 2, text))
    best = d["best"]
    lines.append((tl["lesson_start"] + 8,
                  f"The math says {best.lower()} on {spoken_total(hand['player'])} against {up_spoken(hand['up'])}."))
    return lines, tl


def all_scripts(no, hand):
    """{video: [(display_frame, text)]} for the episode, HIT and STAND videos."""
    out = {"episode": episode_script(no, hand)}
    for action in ("HIT", "STAND"):
        lines, tl = outcome_script(no, hand, action)
        src, disp, end_start = M.outcome_display(tl)
        mapped = [(disp(f), t) for f, t in lines]
        mapped.append((end_start + 10, "The full hand is on my profile."))
        out[action.lower()] = mapped
    return out


def write_script_md(no, hand, path):
    names = {"episode": f"hand{no:02d}_1_episode.mp4", "hit": f"hand{no:02d}_2_hit.mp4",
             "stand": f"hand{no:02d}_3_stand.mp4"}
    L = [f"# Hand {no}: voice-over script", "",
         "Each line starts at the time shown. Short, confident, a little playful. "
         "Leave a beat on the \"...\".", ""]
    for key, lines in all_scripts(no, hand).items():
        L += [f"## {names[key]}", ""]
        L += [f"- **{f / FPS:5.1f}s**  {t}" for f, t in lines]
        L.append("")
    open(path, "w").write("\n".join(L))


# ----------------------------------------------------------------------------- ElevenLabs
def tts(text, voice):
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.sha1(json.dumps([voice, MODEL, SETTINGS, text]).encode()).hexdigest()[:16]
    path = os.path.join(CACHE, key + ".mp3")
    if not os.path.exists(path):
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            raise SystemExit("ELEVENLABS_API_KEY is not set")
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
            data=json.dumps(dict(text=text, model_id=MODEL, voice_settings=SETTINGS)).encode(),
            headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
        with urllib.request.urlopen(req, timeout=120) as r:
            open(path, "wb").write(r.read())
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
    nz = np.where(np.abs(a).max(axis=1) > 0.01)[0]          # trim silence at both ends
    if len(nz):
        a = a[max(0, nz[0] - 400): nz[-1] + 2400]
    return a / max(1e-6, np.abs(a).max())


def voiced_mix(sfx_mix, lines, seconds, voice):
    """SFX mix + voice lines, SFX ducked under the voice. Returns float32 stereo."""
    n = int(seconds * SR)
    sfx = sfx_mix.buf[:n].copy()
    peak = np.abs(sfx).max()
    if peak > 0:
        sfx *= 0.5 / peak
    vo = np.zeros_like(sfx)
    cursor = 0
    for i, (frame, text) in enumerate(lines):
        a = tts(text, voice)
        start = max(int(frame / FPS * SR), cursor)          # never on top of the previous line
        nxt = int(lines[i + 1][0] / FPS * SR) if i + 1 < len(lines) else n
        room = max(1, nxt - start - int(0.1 * SR))
        if len(a) > room:                                    # a little faster if it does not fit
            factor = min(1.18, len(a) / room)
            idx = np.linspace(0, len(a) - 1, int(len(a) / factor)).astype(int)
            a = a[idx]
            if factor > 1.02:
                print(f"  line {i + 1} x{factor:.2f}: {text}", flush=True)
        if start - int(frame / FPS * SR) > 0:
            print(f"  line {i + 1} starts {(start - frame / FPS * SR) / SR:.2f}s late: {text}", flush=True)
        seg = a[:max(0, n - start)]
        vo[start:start + len(seg)] += seg * 0.9
        cursor = start + len(seg) + int(0.08 * SR)
    env = np.abs(vo).max(axis=1)
    k = int(0.12 * SR)
    env = np.convolve(env, np.ones(k) / k, mode="same")
    duck = 1.0 - 0.55 * np.clip(env / 0.08, 0, 1)
    out = sfx * duck[:, None] + vo
    return out * (0.89 / max(1e-6, np.abs(out).max()))


def write_video(src_video, out_video, audio):
    import wave
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        with wave.open(wav, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src_video, "-i", wav, "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_video],
                       check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hands", type=int, nargs="+")
    ap.add_argument("--voice", default=os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE))
    ap.add_argument("--videos", default=os.path.join(HERE, "videos"))
    ap.add_argument("--out", default=os.path.join(HERE, "videos_voice"))
    ap.add_argument("--script-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for no in a.hands:
        hand = H.HANDS[no - 1]
        write_script_md(no, hand, os.path.join(a.out, f"hand{no:02d}_VOICE.md"))
        if a.script_only:
            print(open(os.path.join(a.out, f"hand{no:02d}_VOICE.md")).read())
            continue
        scripts = all_scripts(no, hand)
        jobs = [("episode", f"hand{no:02d}_1_episode.mp4", M.episode_sound(no, hand), H.EP_TOTAL / FPS)]
        for i, action in ((2, "HIT"), (3, "STAND")):
            m, frames = M.outcome_sound(no, hand, action)
            jobs.append((action.lower(), f"hand{no:02d}_{i}_{action.lower()}.mp4", m, frames / FPS))
        for key, name, mix, seconds in jobs:
            src = os.path.join(a.videos, name)
            if not os.path.exists(src):
                print("missing", src)
                continue
            audio = voiced_mix(mix, scripts[key], seconds, a.voice)
            write_video(src, os.path.join(a.out, name), audio)
            print("wrote", os.path.join(a.out, name), flush=True)


if __name__ == "__main__":
    main()
