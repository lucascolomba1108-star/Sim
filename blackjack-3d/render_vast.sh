#!/usr/bin/env bash
# Renders the three blackjack clips on a Linux GPU machine (vast.ai, RunPod, ...).
# Downloads Blender if needed, renders with OptiX/CUDA and writes render/*.mp4.
#
#   bash render_vast.sh                                   # final quality, all clips
#   bash render_vast.sh --clip question --res 50 --samples 48   # quick test
#
# Any extra arguments are passed to blackjack3d.py (see the top of that file).
set -euo pipefail
cd "$(dirname "$0")"

BLENDER_VERSION="${BLENDER_VERSION:-5.2.3}"
BLENDER_DIR="$PWD/.blender"

need_pkgs=()
command -v ffmpeg >/dev/null || need_pkgs+=(ffmpeg)
command -v xz >/dev/null || need_pkgs+=(xz-utils)
command -v curl >/dev/null || need_pkgs+=(curl)
if [ ${#need_pkgs[@]} -gt 0 ] || ! ldconfig -p 2>/dev/null | grep -q libXi.so; then
  echo ">> installing system packages"
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq "${need_pkgs[@]}" libxrender1 libxi6 libxkbcommon0 libsm6 \
      libgl1 libegl1 libxxf86vm1 libxfixes3 >/dev/null
fi

BLENDER="$(ls "$BLENDER_DIR"/*/blender 2>/dev/null | head -1 || true)"
if [ -z "$BLENDER" ]; then
  major="${BLENDER_VERSION%.*}"
  url="https://download.blender.org/release/Blender${major}/blender-${BLENDER_VERSION}-linux-x64.tar.xz"
  if ! curl -fsIL "$url" >/dev/null; then
    echo ">> Blender $BLENDER_VERSION not found, looking for the newest release"
    for major in 5.3 5.2 5.1 5.0 4.5; do
      f="$(curl -fsSL "https://download.blender.org/release/Blender${major}/" 2>/dev/null |
           grep -o "blender-${major}\.[0-9]*-linux-x64\.tar\.xz" | sort -uV | tail -1 || true)"
      if [ -n "$f" ]; then url="https://download.blender.org/release/Blender${major}/$f"; break; fi
    done
  fi
  echo ">> downloading $url"
  mkdir -p "$BLENDER_DIR"
  curl -fL# "$url" | tar -xJ -C "$BLENDER_DIR"
  BLENDER="$(ls "$BLENDER_DIR"/*/blender | head -1)"
fi
echo ">> using $BLENDER"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "!! nvidia-smi not found"

"$BLENDER" -b --factory-startup -P blackjack3d.py -- "$@"

echo
echo ">> done. Videos:"
ls -lh render/*.mp4 2>/dev/null || echo "   (no mp4: frames are in render/<clip>/)"
