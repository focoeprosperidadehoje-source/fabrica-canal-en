#!/usr/bin/env python3
"""
gerar_videos_base_en.py — GitHub Actions: creates slideshow videos for videos_base/ of live EN

Downloads Our Lady images from Drive, applies blur-fill 1280x720 with the saint CENTERED,
and encodes silent ~10min videos (40 images × 15s) with Ken Burns + golden particles.

Environment variables:
  GOOGLE_CREDENTIALS_EN  — service account JSON
  NUM_VIDEOS             — how many videos to create (default: 8)
  DRIVE_FOLDER_ID        — image folder (default: empty, skips Drive download)
  VIDEO_PREFIX           — output filename prefix (default: ourlady)
  OUTPUT_DIR             — output directory (default: videos_base_en)
"""

import os
import sys
import json
import math
import random
import datetime
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ─── Config ────────────────────────────────────────────────────────────
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID") or ""
VIDEO_PREFIX    = os.environ.get("VIDEO_PREFIX") or "ourlady"
NUM_VIDEOS      = int(os.environ.get("NUM_VIDEOS") or "8")
IMG_POR_VIDEO   = 40        # images per video → 40 × 15s = 600s = 10min
SEG_POR_IMAGEM  = 15
TARGET_W        = 1280      # 720p
TARGET_H        = 720
DIR_SAIDA       = Path(os.environ.get("OUTPUT_DIR") or "videos_base_en")


# ─── Golden particle overlay ────────────────────────────────────────────

def _gerar_overlay_particulas(saida: Path, duracao_s: int = 20, fps: int = 30) -> Path | None:
    if saida.exists():
        return saida

    n_frames = duracao_s * fps
    n = 400
    rng = np.random.default_rng(42)

    px   = rng.uniform(0, TARGET_W, n).astype(np.float32)
    py   = rng.uniform(0, TARGET_H, n).astype(np.float32)
    vx   = rng.uniform(-0.4, 0.4, n).astype(np.float32)
    vy   = (rng.uniform(35, 55, n) / fps).astype(np.float32)
    age  = rng.uniform(0, 80, n).astype(np.float32)
    life = rng.uniform(60, 130, n).astype(np.float32)

    CORES = np.array([
        [255, 215,   0],
        [255, 200,   0],
        [255, 230, 110],
        [255, 180,   0],
        [255, 245, 160],
    ], dtype=np.float32)
    cor_idx = rng.integers(0, len(CORES), n)

    tmp = saida.with_suffix(".ptmp.mp4")
    cmd_ff = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{TARGET_W}x{TARGET_H}", "-pix_fmt", "rgb24", "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "25",
        "-pix_fmt", "yuv420p", "-an",
        str(tmp),
    ]
    proc = subprocess.Popen(cmd_ff, stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(n_frames):
            frame = np.zeros((TARGET_H, TARGET_W, 3), dtype=np.uint8)
            py -= vy
            px += vx
            age += 1.0

            mortas = (age >= life) | (py < -10)
            if mortas.any():
                m = int(mortas.sum())
                px[mortas]  = rng.uniform(0, TARGET_W, m).astype(np.float32)
                py[mortas]  = (TARGET_H + rng.uniform(0, 40, m)).astype(np.float32)
                age[mortas] = 0.0
                life[mortas] = rng.uniform(60, 130, m).astype(np.float32)
                vy[mortas]  = (rng.uniform(35, 55, m) / fps).astype(np.float32)
                vx[mortas]  = rng.uniform(-0.4, 0.4, m).astype(np.float32)
                cor_idx[mortas] = rng.integers(0, len(CORES), m)

            px %= TARGET_W
            t    = np.clip(age / life, 0.0, 1.0)
            fade = (np.sin(np.pi * t) * 0.90).astype(np.float32)
            xi   = np.clip(px.astype(np.int32), 0, TARGET_W - 1)
            yi   = np.clip(py.astype(np.int32), 0, TARGET_H - 1)
            cores = (CORES[cor_idx] * fade[:, np.newaxis]).astype(np.uint8)

            for dy, dx in [(0,0),(0,1),(0,-1),(1,0),(-1,0),(1,1),(-1,-1),(1,-1),(-1,1)]:
                att = np.float32(1.0 if (dx == 0 and dy == 0) else 0.6)
                yy = np.clip(yi + dy, 0, TARGET_H - 1)
                xx = np.clip(xi + dx, 0, TARGET_W - 1)
                np.maximum.at(frame, (yy, xx),
                              (cores.astype(np.float32) * att).clip(0, 255).astype(np.uint8))

            proc.stdin.write(frame.tobytes())

        proc.stdin.close()
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError("FFmpeg particles failed")
        tmp.rename(saida)
        print(f"  ✅ particle overlay: {saida.name} ({n_frames} frames)")
        return saida
    except Exception as e:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.kill()
        tmp.unlink(missing_ok=True)
        print(f"  [WARN] Particles failed: {e} — videos without golden effect.")
        return None


# ─── Drive ─────────────────────────────────────────────────────────────

def get_drive():
    raw  = os.environ.get("GOOGLE_CREDENTIALS_EN", "")
    if not raw:
        creds_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        if creds_file:
            with open(creds_file) as f:
                raw = f.read()
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds)


def listar_imagens(drive, folder_id: str) -> list[dict]:
    items, token = [], None
    while True:
        resp = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false and (mimeType contains 'image/')",
            fields="nextPageToken, files(id, name)",
            pageToken=token,
            pageSize=500,
        ).execute()
        items.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token:
            break
    print(f"  Images in Drive folder: {len(items)}")
    return items


def baixar_imagem(drive, file_id: str, dest: Path):
    content = drive.files().get_media(fileId=file_id).execute()
    dest.write_bytes(content)


# ─── Image processing ───────────────────────────────────────────────────

def blur_fill(src: Path, dest: Path, w: int = TARGET_W, h: int = TARGET_H):
    img = Image.open(src).convert("RGB")
    iw, ih = img.size

    scale_bg = max(w / iw, h / ih)
    bg_w = round(iw * scale_bg)
    bg_h = round(ih * scale_bg)
    bg   = img.resize((bg_w, bg_h), Image.LANCZOS)
    left = (bg_w - w) // 2
    top  = (bg_h - h) // 2
    bg   = bg.crop((left, top, left + w, top + h))
    bg   = bg.filter(ImageFilter.GaussianBlur(radius=28))

    scale_fg = min(w / iw, h / ih)
    fg_w = round(iw * scale_fg)
    fg_h = round(ih * scale_fg)
    fg   = img.resize((fg_w, fg_h), Image.LANCZOS)
    x    = (w - fg_w) // 2
    y    = (h - fg_h) // 2
    bg.paste(fg, (x, y))

    dest.parent.mkdir(parents=True, exist_ok=True)
    bg.save(str(dest), "JPEG", quality=88)


# ─── Slideshow with Ken Burns ────────────────────────────────────────────

def criar_slideshow(imagens: list[Path], saida: Path, overlay: Path | None = None):
    if saida.exists():
        print(f"  {saida.name} already exists — skipping.")
        return

    fps = 30
    frames_por_img = SEG_POR_IMAGEM * fps
    total_imgs = len(imagens)

    tmp_base  = saida.with_suffix(".base.mp4")
    tmp_final = saida.with_suffix(".tmp.mp4")

    cmd_pipe = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{TARGET_W}x{TARGET_H}", "-pix_fmt", "rgb24", "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-g", "60", "-keyint_min", "30",
        "-pix_fmt", "yuv420p", "-an",
        str(tmp_base),
    ]
    print(f"  Ken Burns: {total_imgs} imgs × {SEG_POR_IMAGEM}s → {TARGET_W}x{TARGET_H}...", flush=True)
    proc = subprocess.Popen(cmd_pipe, stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for idx, img_path in enumerate(imagens):
            img = Image.open(img_path).convert("RGB")
            iw, ih = img.size
            direction = random.choice(["in", "out"])
            for f in range(frames_por_img):
                t = f / max(frames_por_img - 1, 1)
                zoom = (1.0 + 0.04 * t) if direction == "in" else (1.04 - 0.04 * t)
                crop_w = round(iw / zoom)
                crop_h = round(ih / zoom)
                x = (iw - crop_w) // 2
                y = (ih - crop_h) // 2
                frame = img.crop((x, y, x + crop_w, y + crop_h)).resize(
                    (TARGET_W, TARGET_H), Image.BILINEAR
                )
                proc.stdin.write(frame.tobytes())
            if (idx + 1) % 10 == 0:
                print(f"    {idx + 1}/{total_imgs} images processed", flush=True)
        proc.stdin.close()
        proc.wait(timeout=600)
        if proc.returncode != 0:
            raise RuntimeError("FFmpeg Ken Burns failed")
    except Exception:
        try: proc.stdin.close()
        except Exception: pass
        proc.kill()
        tmp_base.unlink(missing_ok=True)
        raise

    if overlay and overlay.exists():
        vf = (
            f"[0:v]scale={TARGET_W}:{TARGET_H},fps={fps}[base];"
            f"[1:v]scale={TARGET_W}:{TARGET_H},fps={fps}[p];"
            "[base][p]blend=all_mode=screen:all_opacity=0.25[v]"
        )
        cmd_blend = [
            "ffmpeg", "-y",
            "-i", str(tmp_base),
            "-stream_loop", "-1", "-i", str(overlay),
            "-filter_complex", vf,
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-g", "60", "-keyint_min", "30",
            "-pix_fmt", "yuv420p", "-an",
            "-shortest",
            str(tmp_final),
        ]
        print("  Blending particles...", flush=True)
        result = subprocess.run(cmd_blend, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"  [WARN] Blend failed — using base without particles: {result.stderr[-200:]}")
            tmp_final.unlink(missing_ok=True)
            tmp_base.rename(saida)
        else:
            tmp_base.unlink(missing_ok=True)
            tmp_final.rename(saida)
    else:
        tmp_base.rename(saida)

    mb = saida.stat().st_size // (1024 * 1024)
    print(f"  ✅ {saida.name} ready ({mb} MB)")


# ─── Main ───────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"gerar_videos_base_en.py — {VIDEO_PREFIX.upper()} — {NUM_VIDEOS} videos")
    print(f"Drive folder: {DRIVE_FOLDER_ID or '(none)'}")
    print("=" * 60)

    DIR_SAIDA.mkdir(parents=True, exist_ok=True)

    overlay_path = DIR_SAIDA / f"_particulas_loop_{TARGET_W}x{TARGET_H}.mp4"
    overlay = _gerar_overlay_particulas(overlay_path)

    if not DRIVE_FOLDER_ID:
        print("[WARN] DRIVE_FOLDER_ID not set — cannot download images from Drive.")
        print("Place images manually in a local folder or set DRIVE_FOLDER_ID.")
        sys.exit(1)

    drive = get_drive()
    todas = listar_imagens(drive, DRIVE_FOLDER_ID)

    if not todas:
        print("[ERROR] No images found in Drive folder.")
        sys.exit(1)

    random.shuffle(todas)
    total_videos = min(NUM_VIDEOS, math.ceil(len(todas) / IMG_POR_VIDEO))
    print(f"Creating {total_videos} videos (max {IMG_POR_VIDEO} images each)...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        criados = 0

        for v in range(total_videos):
            batch = todas[v * IMG_POR_VIDEO : (v + 1) * IMG_POR_VIDEO]
            if len(batch) < 10:
                print(f"  Batch {v+1}: {len(batch)} images — minimum 10, skipping.")
                break

            print(f"\n── Video {v+1}/{total_videos} ({len(batch)} images) ──")

            imgs_proc = []
            for i, f in enumerate(batch):
                ext  = Path(f["name"]).suffix.lower() or ".jpg"
                raw  = tmp / f"raw_{v:02d}_{i:03d}{ext}"
                proc = tmp / f"proc_{v:02d}_{i:03d}.jpg"
                try:
                    baixar_imagem(drive, f["id"], raw)
                    blur_fill(raw, proc)
                    imgs_proc.append(proc)
                except Exception as e:
                    print(f"  [WARN] {f['name']}: {e}")

            if len(imgs_proc) < 10:
                print("  Fewer than 10 images processed — batch skipped.")
                continue

            ts    = datetime.datetime.utcnow().strftime("%Y%m%d")
            saida = DIR_SAIDA / f"{VIDEO_PREFIX}_{ts}_{v+1:02d}.mp4"
            try:
                criar_slideshow(imgs_proc, saida, overlay=overlay)
                criados += 1
            except Exception as e:
                print(f"  [ERROR] video {v+1}: {e}")

    print(f"\n{'='*60}")
    print(f"Done: {criados}/{total_videos} videos in {DIR_SAIDA}/")
    if criados == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
