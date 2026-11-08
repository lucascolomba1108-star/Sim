"""Renders and composes hands one after another (unattended).

  python3 series.py --from 1 --to 20                        # uses `blender` from PATH
  python3 series.py --from 1 --to 20 --bpy-python /path/to/python-with-bpy
  python3 series.py --from 1 --to 20 --samples 128 --device OPTIX   # GPU box

Shared plates are rendered first if they are missing. Every step can be
interrupted and restarted: finished frames and finished videos are skipped.
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hands as H  # noqa: E402


def blender_cmd(a, extra):
    script = os.path.join(HERE, "blackjack3d.py")
    base = [a.bpy_python, script] if a.bpy_python else [a.blender, "-b", "--factory-startup", "-P", script]
    return base + ["--", "--device", a.device, "--res", str(a.res), "--samples", str(a.samples),
                   "--out", a.render] + extra


def run(cmd, log):
    with open(log, "a") as fh:
        fh.write("\n$ " + " ".join(cmd) + "\n")
        fh.flush()
        r = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        raise SystemExit(f"failed ({r.returncode}): {' '.join(cmd)}  -- see {log}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--to", dest="end", type=int, default=len(H.HANDS))
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--res", type=int, default=100)
    ap.add_argument("--device", default="AUTO")
    ap.add_argument("--blender", default="blender")
    ap.add_argument("--bpy-python", default="")
    ap.add_argument("--render", default=os.path.join(HERE, "render"))
    ap.add_argument("--videos", default=os.path.join(HERE, "videos"))
    ap.add_argument("--log", default=os.path.join(HERE, "render", "series.log"))
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.log), exist_ok=True)
    if not os.path.exists(os.path.join(a.render, "shared", "meta.json")):
        t = time.time()
        run(blender_cmd(a, ["--shots", "plates"]), a.log)
        print(f"plates done in {(time.time() - t) / 60:.0f} min", flush=True)
    for no in range(a.start, a.end + 1):
        names = [f"hand{no:02d}_{s}.mp4" for s in ("1_episode", "2_hit", "3_stand")]
        if all(os.path.exists(os.path.join(a.videos, n)) for n in names):
            print(f"hand {no}: already done", flush=True)
            continue
        t = time.time()
        try:
            run(blender_cmd(a, ["--hand", str(no)]), a.log)
            t3d = time.time() - t
            run([sys.executable, os.path.join(HERE, "make_videos.py"), str(no), "--render", a.render,
                 "--out", a.videos], a.log)
        except SystemExit as e:          # keep going with the next hand
            print(f"hand {no}: FAILED ({e})", flush=True)
            continue
        print(f"hand {no}: done (3D {t3d / 60:.0f} min, total {(time.time() - t) / 60:.0f} min)", flush=True)


if __name__ == "__main__":
    main()
