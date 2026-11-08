# Project notes for Claude

## Who this is for
The owner makes interactive Instagram Reels (posted via the Edits app) for an
international audience: a 3D blackjack series where viewers decide HIT or STAND.
Write user-facing replies in Portuguese (pt-BR); everything on screen in the
videos is in English.

## Quality bar (the owner's explicit instruction: keep this in memory)
- Quality matters more than speed. Nothing "meia boca": be meticulous and detailed.
- Look at real rendered frames before shipping anything; review contact sheets at
  full resolution for overlaps, cut-off text, safe zones and continuity.
- Keep key content inside the Reels safe area of a 1080x1920 frame: top ~230 px
  (header), bottom ~400 px (caption) and the right column x>960, y>1100 (buttons).
- Don't ask the owner questions when they say to keep going; make sensible calls
  and keep producing.

## Series format (blackjack-3d/)
Per hand N, three videos in `blackjack-3d/videos/`:
1. `handNN_1_episode.mp4`: context intro ("interactive blackjack, you decide"),
   deal with crane move, "HIT or STAND?", end card with two side-by-side slots
   (HIT | STAND) where the owner places the decision reels. From hand 2 on, a
   "PREVIOUSLY" slot in the top-left corner for the earlier reels.
2. `handNN_2_hit.mp4` / 3. `handNN_3_stand.mp4`: recap first (so someone arriving
   from the Reels feed isn't lost), the outcome, then the basic-strategy lesson.

Pipeline: `hands.py` (hands + rules + timeline) -> `blackjack3d.py` (Cycles
renders: shared plates once, then per-hand crops) -> `make_videos.py` (composite,
overlay graphics from `overlay/`, ffmpeg). `series.py` runs hands back to back.
`render_vast.sh` is the GPU-box entry point.
