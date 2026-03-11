# Upscale Studio

A local browser-based tool for upscaling video files using Real-ESRGAN AI.
Runs entirely on your machine — nothing is uploaded to the cloud.

## Requirements

- **Windows 10/11**
- **Python 3.9+** installed and in PATH
- **NVIDIA GPU** with up-to-date drivers (for Real-ESRGAN acceleration)

## Quick Start

### First-time setup (one-time)

1. Double-click **`setup.bat`**
2. Wait for it to finish — it will:
   - Create a Python virtual environment
   - Install required Python packages
   - Download FFmpeg (~80 MB)
   - Download Real-ESRGAN ncnn-vulkan (~30 MB)
3. You'll see "Setup complete!" when done

### Launch the app

1. Double-click **`start.bat`**
2. Your browser will open to **http://localhost:8000**
3. Drag and drop a video file to get started

## How to Use

1. **Upload** — Drag a video onto the upload zone (or click to browse)
2. **Review** — Check the video details and adjust settings:
   - **Scale**: 2x (default) or 4x
   - **Model**: Real-ESRGAN x4plus for live action, Anime Video v3 for animation
   - **Codec**: H.264 (most compatible) or H.265 (smaller files)
   - **Tile Size**: Leave on Auto unless you get VRAM errors (use 128 for low VRAM)
3. **Preview** — Click "Preview Frame" to upscale a single frame and check quality
4. **Upscale** — Click "Start Upscale" and wait for processing to complete
5. **Download** — Click "Download Video" when finished

## Troubleshooting

### "VRAM out of memory" or GPU errors
- Set **Tile Size** to 128 or 256 in the settings panel

### Processing is very slow
- This is normal for long or high-resolution videos
- 2x upscaling is significantly faster than 4x
- Estimated time is shown during processing

### FFmpeg or Real-ESRGAN not found
- Re-run **setup.bat** to re-download binaries
- Check that `bin/ffmpeg/ffmpeg.exe` and `bin/realesrgan/realesrgan-ncnn-vulkan.exe` exist

### Port 8000 already in use
- Close other applications using port 8000, or
- Edit `start.bat` and change `--port 8000` to another port number

## Project Structure

```
upscale-studio/
├── app/                  Python backend (FastAPI)
│   ├── main.py           API endpoints
│   └── pipeline.py       Video processing pipeline
├── static/               Frontend (HTML/CSS/JS)
├── bin/                  Downloaded binaries
│   ├── ffmpeg/           FFmpeg + FFprobe
│   └── realesrgan/       Real-ESRGAN ncnn-vulkan
├── workspace/            Processing temp files
├── setup.bat             First-time setup
├── start.bat             Launch the app
├── setup_env.py          Binary downloader
└── requirements.txt      Python dependencies
```

## Credits

- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) by Xintao Wang et al.
- [FFmpeg](https://ffmpeg.org/) for video processing
- [FastAPI](https://fastapi.tiangolo.com/) for the web server
