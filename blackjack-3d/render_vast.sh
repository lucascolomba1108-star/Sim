#!/usr/bin/env bash
# Renders the whole series on a Linux GPU machine (vast.ai, RunPod, ...).
# Downloads Blender if needed, renders with OptiX/CUDA and writes videos/*.mp4.
#
#   bash render_vast.sh                       # all hands, final quality (128 samples)
#   bash render_vast.sh --from 3 --to 5       # some hands
#   bash render_vast.sh --samples 48          # faster
#
# Extra arguments go to series.py. Re-running skips frames/videos that already exist.
set -euo pipefail
cd "$(dirname "$0")"

BLENDER_VERSION="${BLENDER_VERSION:-5.2.3}"
BLENDER_DIR="$PWD/.blender"

need_pkgs=()
command -v ffmpeg >/dev/null || need_pkgs+=(ffmpeg)
command -v xz >/dev/null || need_pkgs+=(xz-utils)
command -v curl >/dev/null || need_pkgs+=(curl)
command -v node >/dev/null || need_pkgs+=(nodejs npm)
if [ ${#need_pkgs[@]} -gt 0 ] || ! ldconfig -p 2>/dev/null | grep -q libXi.so; then
  echo ">> installing system packages"
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq "${need_pkgs[@]}" libxrender1 libxi6 libxkbcommon0 libsm6 \
      libgl1 libegl1 libxxf86vm1 libxfixes3 fonts-dejavu-core >/dev/null
fi
python3 -c "import numpy, PIL" 2>/dev/null || python3 -m pip install -q numpy pillow
# overlay renderer: Playwright + Chromium, and the Inter font family
if ! node -e "require('playwright')" 2>/dev/null; then
  npm install --silent playwright@1.48.2 && npx playwright install --with-deps chromium
fi
if ! fc-list | grep -qi "Inter Display"; then
  echo ">> installing the Inter font"
  mkdir -p ~/.fonts && curl -fsSL -o /tmp/inter.zip https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip \
    && python3 -c "import zipfile;z=zipfile.ZipFile('/tmp/inter.zip');[z.extract(n,'/tmp/inter') for n in z.namelist() if n.endswith('.ttf') or n.endswith('.otf')]" \
    && find /tmp/inter -name "*.otf" -exec cp {} ~/.fonts/ \; && fc-cache -f >/dev/null
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

python3 series.py --blender "$BLENDER" --samples 128 --render render_gpu --videos videos_gpu "$@"

echo
echo ">> done. Videos:"
ls -lh videos_gpu/*.mp4 2>/dev/null || echo "   (none yet)"
