# Copilot Instructions - Upscale Studio

**Repository:** upscale-studio
**Last Updated:** March 2026

## Project Overview

Upscale Studio is a local browser-based web application for upscaling video files
using Real-ESRGAN ncnn-vulkan. Built with Python (FastAPI) backend and vanilla
JS frontend, designed for Windows with NVIDIA GPU.

## Critical: Build & Run Commands

### Prerequisites

- **Python:** 3.10+
- **Windows 11** with NVIDIA GPU
- **FFmpeg** and **Real-ESRGAN ncnn-vulkan** (auto-downloaded by setup)

### Installation

```bash
# Run setup (creates venv, installs deps, downloads binaries)
setup.bat
```

### Running

```bash
# Start the server (opens browser automatically)
start.bat
# Or manually:
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Dependencies

```
fastapi==0.115.6
uvicorn[standard]==0.32.1
python-multipart==0.0.18
```

## Project Structure

### Key Directories

- `app/` - Python backend (FastAPI)
  - `main.py` - API endpoints and static file serving
  - `pipeline.py` - Core video processing pipeline
- `static/` - Frontend (vanilla HTML/CSS/JS)
  - `index.html` - Single-page UI
  - `app.js` - Frontend logic
  - `style.css` - Dark theme styles
- `bin/` - Downloaded binaries (FFmpeg, Real-ESRGAN)
- `workspace/` - Temporary video processing data

### Critical Files

- `app/pipeline.py` - Chunked video processing pipeline (most complex file)
- `app/main.py` - FastAPI routes
- `setup_env.py` - Binary download and setup script
- `requirements.txt` - Python dependencies

## Architecture & Patterns

### Pipeline Architecture

Chunked processing for movie-length videos:
1. Extract 1000 frames per chunk (FFmpeg, frame-accurate seeking)
2. Upscale frames (Real-ESRGAN ncnn-vulkan)
3. Encode chunk to video segment (FFmpeg)
4. Delete processed PNGs
5. Repeat for all chunks
6. Concatenate segments + mux all audio/subtitle tracks

### Security

- `ALLOWED_MODELS` whitelist for Real-ESRGAN model selection
- `ALLOWED_VIDEO_EXTENSIONS` whitelist for file validation
- `os.path.realpath()` prefix validation for path traversal prevention
- `subprocess` calls use `shell=False` with argument lists

### Key Design Decisions

- Sync FastAPI endpoints (CPU/GPU-bound work via subprocess)
- Background thread for pipeline processing
- 1-second polling for progress updates
- Local file path selection to avoid copying multi-GB movie files
- Cumulative frame counter for frame-accurate chunk boundaries

## Common Issues & Fixes

1. **Port conflict**: Kill existing Python processes before restarting
2. **Stale cache**: Delete `app/__pycache__` if routes don't register
3. **VRAM issues**: Use smaller tile sizes (256, 128) for large frames
4. **Disk space**: Chunked processing limits peak usage to ~20-30GB

## Validation Steps

Before submitting a PR:

1. **Start**: `start.bat` - Server starts without errors
2. **Upload**: Drag-and-drop or file path - Video info displays correctly
3. **Preview**: Preview frame generates with correct resolution
4. **Process**: Short test video upscales without errors
5. **Download**: Output file downloads correctly
