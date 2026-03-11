"""
Upscale Studio — Setup Script
Downloads FFmpeg and Real-ESRGAN ncnn-vulkan binaries.
Run via: python setup_env.py  (or through setup.bat)
"""

import os
import shutil
import urllib.request
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "bin")

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_DIR = os.path.join(BIN_DIR, "ffmpeg")

REALESRGAN_URL = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/"
    "v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"
)
REALESRGAN_DIR = os.path.join(BIN_DIR, "realesrgan")


def download_with_progress(url, dest_path):
    """Download a file with a simple progress indicator."""
    print(f"  Downloading: {url}")
    print(f"  Saving to:   {dest_path}")

    req = urllib.request.Request(url, headers={"User-Agent": "UpscaleStudio/1.0"})
    resp = urllib.request.urlopen(req, timeout=120)
    total = int(resp.headers.get("Content-Length", 0))

    downloaded = 0
    block = 1024 * 256  # 256 KB chunks
    with open(dest_path, "wb") as f:
        while True:
            chunk = resp.read(block)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = int(downloaded / total * 100)
                bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
                dl_mb = downloaded // (1024 * 1024)
                total_mb = total // (1024 * 1024)
                print(f"\r  [{bar}] {pct}%  ({dl_mb}MB / {total_mb}MB)", end="", flush=True)
    print()  # newline


def setup_ffmpeg():
    """Download and extract FFmpeg if not already present."""
    ffmpeg_exe = os.path.join(FFMPEG_DIR, "ffmpeg.exe")

    # Check if already downloaded
    if os.path.isfile(ffmpeg_exe):
        print("[OK] FFmpeg already installed.")
        return

    # Check system PATH
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        print("[OK] FFmpeg found in system PATH — skipping download.")
        os.makedirs(FFMPEG_DIR, exist_ok=True)
        # Create symlinks / copies so the app can find them
        sys_ffmpeg = shutil.which("ffmpeg")
        sys_ffprobe = shutil.which("ffprobe")
        shutil.copy2(sys_ffmpeg, os.path.join(FFMPEG_DIR, "ffmpeg.exe"))
        shutil.copy2(sys_ffprobe, os.path.join(FFMPEG_DIR, "ffprobe.exe"))
        return

    print("\n[1/2] Setting up FFmpeg...")
    os.makedirs(BIN_DIR, exist_ok=True)
    zip_path = os.path.join(BIN_DIR, "ffmpeg.zip")

    download_with_progress(FFMPEG_URL, zip_path)

    print("  Extracting FFmpeg...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(BIN_DIR)

    # The zip extracts to a versioned folder like "ffmpeg-7.0-essentials_build/"
    # Find it and move the bin contents
    os.makedirs(FFMPEG_DIR, exist_ok=True)
    for entry in os.listdir(BIN_DIR):
        candidate = os.path.join(BIN_DIR, entry)
        if os.path.isdir(candidate) and entry.startswith("ffmpeg-") and entry.endswith("_build"):
            bin_subdir = os.path.join(candidate, "bin")
            if os.path.isdir(bin_subdir):
                for fname in os.listdir(bin_subdir):
                    src = os.path.join(bin_subdir, fname)
                    dst = os.path.join(FFMPEG_DIR, fname)
                    shutil.move(src, dst)
            shutil.rmtree(candidate, ignore_errors=True)
            break

    # Clean up zip
    os.remove(zip_path)

    if os.path.isfile(ffmpeg_exe):
        print("  [OK] FFmpeg ready.")
    else:
        print("  [ERROR] FFmpeg extraction failed. Please download manually from:")
        print("          https://www.gyan.dev/ffmpeg/builds/")
        print(f"          Place ffmpeg.exe and ffprobe.exe in: {FFMPEG_DIR}")


def setup_realesrgan():
    """Download and extract Real-ESRGAN ncnn-vulkan if not already present."""
    exe_path = os.path.join(REALESRGAN_DIR, "realesrgan-ncnn-vulkan.exe")

    if os.path.isfile(exe_path):
        print("[OK] Real-ESRGAN already installed.")
        return

    print("\n[2/2] Setting up Real-ESRGAN ncnn-vulkan...")
    os.makedirs(BIN_DIR, exist_ok=True)
    zip_path = os.path.join(BIN_DIR, "realesrgan.zip")

    download_with_progress(REALESRGAN_URL, zip_path)

    print("  Extracting Real-ESRGAN...")
    os.makedirs(REALESRGAN_DIR, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Check if zip has a top-level directory or flat files
        top_dirs = set()
        for name in zf.namelist():
            parts = name.split("/")
            if len(parts) > 1:
                top_dirs.add(parts[0])

        zf.extractall(BIN_DIR)

    # If there's a single top-level dir, move its contents into realesrgan/
    if len(top_dirs) == 1:
        extracted_dir = os.path.join(BIN_DIR, top_dirs.pop())
        if os.path.isdir(extracted_dir):
            for item in os.listdir(extracted_dir):
                src = os.path.join(extracted_dir, item)
                dst = os.path.join(REALESRGAN_DIR, item)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.move(src, dst)
                else:
                    shutil.move(src, dst)
            shutil.rmtree(extracted_dir, ignore_errors=True)
    else:
        # Flat zip — move known files directly into realesrgan/
        known_files = ["realesrgan-ncnn-vulkan.exe", "vcomp140.dll", "vcomp140d.dll"]
        known_dirs = ["models"]
        for fname in known_files:
            src = os.path.join(BIN_DIR, fname)
            if os.path.isfile(src):
                shutil.move(src, os.path.join(REALESRGAN_DIR, fname))
        for dname in known_dirs:
            src = os.path.join(BIN_DIR, dname)
            if os.path.isdir(src):
                dst = os.path.join(REALESRGAN_DIR, dname)
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.move(src, dst)

    # Clean up zip
    os.remove(zip_path)

    if os.path.isfile(exe_path):
        print("  [OK] Real-ESRGAN ready.")
    else:
        print("  [ERROR] Real-ESRGAN extraction failed. Please download manually from:")
        print("          https://github.com/xinntao/Real-ESRGAN/releases")
        print(f"          Place files in: {REALESRGAN_DIR}")


def verify():
    """Quick verification that binaries are accessible."""
    print("\n── Verification ─────────────────────────")
    ok = True

    ffmpeg_exe = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
    if os.path.isfile(ffmpeg_exe):
        import subprocess

        result = subprocess.run([ffmpeg_exe, "-version"], capture_output=True, text=True)
        version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
        print(f"  FFmpeg:       {version_line}")
    else:
        print("  FFmpeg:       NOT FOUND")
        ok = False

    esrgan_exe = os.path.join(REALESRGAN_DIR, "realesrgan-ncnn-vulkan.exe")
    if os.path.isfile(esrgan_exe):
        print(f"  Real-ESRGAN:  {esrgan_exe} [OK]")
    else:
        print("  Real-ESRGAN:  NOT FOUND")
        ok = False

    models_dir = os.path.join(REALESRGAN_DIR, "models")
    if os.path.isdir(models_dir):
        models = [f for f in os.listdir(models_dir) if f.endswith(".bin") or f.endswith(".param")]
        print(f"  Models:       {len(models)} model files found")
    else:
        print("  Models:       NOT FOUND")
        ok = False

    if ok:
        print("\n  All good! Run start.bat to launch Upscale Studio.\n")
    else:
        print("\n  Some components are missing. Check the errors above.\n")

    return ok


if __name__ == "__main__":
    print("=" * 50)
    print("  Upscale Studio — Environment Setup")
    print("=" * 50)

    setup_ffmpeg()
    setup_realesrgan()
    verify()
