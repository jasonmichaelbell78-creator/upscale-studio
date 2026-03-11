# Performance Pipeline Redesign: PyTorch CUDA + Temporal Interpolation

**Date:** 2026-03-10
**Status:** Approved
**Branch:** improvements

## Problem

A 45-minute video at 24fps (~64,800 frames) takes ~100 hours to upscale at 2x using the current Real-ESRGAN ncnn-vulkan pipeline. Each frame is processed individually via subprocess calls, with no frame deduplication, no interpolation, and no pipeline parallelism.

## Goal

Reduce upscale time from ~100 hours to ~3-4 hours for a 45-minute video at 2x, a 25-30x speedup.

## Design Decisions

- **Smart compromise on quality:** AI-upscale frames that matter, interpolate/copy the rest
- **Single NVIDIA GPU target:** No multi-GPU complexity
- **Conservative deduplication:** Only skip truly duplicate/near-identical frames (pHash >95%)
- **Motion-aware fallback:** Auto-detect fast motion scenes and AI-upscale those instead of interpolating
- **Pipeline parallelism:** Extract/upscale/encode run concurrently across chunks
- **Graceful degradation:** Falls back to current ncnn-vulkan pipeline if no CUDA GPU available

---

## Architecture Overview

The current pipeline (extract -> subprocess to ncnn-vulkan -> encode) is replaced with an in-process Python pipeline using three models:

1. **Real-ESRGAN (PyTorch CUDA, FP16)** - AI upscaling of selected frames
2. **RIFE (PyTorch CUDA)** - temporal interpolation for skipped frames
3. **Perceptual hasher** - frame deduplication (lightweight, CPU)

### Processing Flow Per Chunk

```
Extract frames (FFmpeg)
    -> pHash dedup (CPU) - identify unique frames
    -> Scene/motion analysis (CPU) - classify frames
    -> AI upscale keyframes (Real-ESRGAN, GPU)
    -> Copy upscaled result for duplicates
    -> Interpolate remaining frames (RIFE, GPU)
    -> Encode segment (FFmpeg)
```

All three chunk stages (extract / process / encode) run concurrently across different chunks.

Frames stay in GPU memory between Real-ESRGAN and RIFE. No PNG round-trips for the upscaling step.

---

## Frame Classification

Each extracted frame is classified into one of three categories:

### 1. Duplicate
- pHash similarity >95% to previous frame
- Action: Copy the upscaled version of the matched frame
- Cost: ~0ms GPU time

### 2. Keyframe (must be AI-upscaled)
- First frame of each scene change
- Frames where optical flow exceeds the motion threshold
- Every Nth frame (N=4) regardless, to anchor interpolation quality
- Action: Real-ESRGAN FP16 upscale
- Cost: ~1.2s per frame

### 3. Interpolatable
- Sits between two keyframes with low-to-moderate motion
- Action: RIFE generates from neighboring upscaled keyframes
- Cost: ~5-10ms per frame

### Detection Methods

**Scene change detection:** Mean absolute difference between consecutive frames. A spike above a threshold = scene change. Fast, CPU-only, numpy.

**Optical flow / motion detection:** Reuses RIFE's flow network. Since the model is already loaded, motion magnitude comes nearly for free.

---

## PyTorch Pipeline & Memory Management

### Model Loading
- Real-ESRGAN and RIFE models load once at startup, stay resident on GPU
- FP16 for both models (halves VRAM, doubles throughput)
- Existing tile_size setting still applies for large frames exceeding VRAM

### Processing Flow (In-Process)
- FFmpeg extracts frames as PNG to disk
- Frames loaded into GPU tensors in batches
- Real-ESRGAN processes keyframe batches (batch size auto-tuned to VRAM)
- Upscaled keyframes stay in GPU memory
- RIFE interpolates between neighboring upscaled keyframes on GPU
- Final frames written to disk for FFmpeg encoding

### VRAM Management
- Estimate VRAM per frame at target resolution
- Auto-detect available VRAM via `torch.cuda.get_device_properties()`
- Batch size = available VRAM / per-frame cost, with safety margin
- Fall back to tile-based processing if single frame exceeds VRAM (4K+ outputs)

### Graceful Degradation
- No CUDA GPU detected -> fall back to current ncnn-vulkan pipeline
- Insufficient VRAM for batching -> batch size of 1 with tiling
- PyTorch not installed -> fall back to ncnn-vulkan

The ncnn-vulkan path stays as a fallback, not removed.

---

## Pipeline Parallelism

### Three-Stage Concurrent Pipeline

```
Time ->
Chunk 1:  [Extract] [Upscale+Interp] [Encode]
Chunk 2:           [Extract] [Upscale+Interp] [Encode]
Chunk 3:                    [Extract] [Upscale+Interp] [Encode]
```

### Implementation
- Python `threading` with a 3-slot pipeline
- Bounded queue between stages (max 1 chunk buffered per stage)
- Extract (CPU+disk) and Encode (CPU+disk) overlap with Upscale+Interpolate (GPU)
- GPU is never idle waiting for FFmpeg

### Disk Management
- At most 3 chunks of extracted frames on disk at once (vs 1 today)
- Peak disk: ~3x current chunk temp usage
- Each chunk's temp files cleaned up as soon as encoding completes
- Disk space estimation updated for 3 in-flight chunks

### Cancellation
- Same `job.cancelled` flag approach
- Each stage checks flag before starting next chunk
- GPU operations interrupted via PyTorch mechanisms

---

## Dependencies & Installation

### New Python Packages
- `torch` + `torchvision` (CUDA build)
- `basicsr` - Real-ESRGAN underlying framework
- `realesrgan` - Python API for Real-ESRGAN models
- `opencv-python` - frame loading into tensors
- `imagehash` - perceptual hashing for dedup

### RIFE
- PyTorch RIFE implementation (in-process, shares GPU memory)
- Model weights downloaded on first run (extends `setup_env.py`)

### Installation Changes
- `setup_env.py` extended to download RIFE model weights
- `requirements.txt` updated with new packages
- CUDA toolkit not needed separately (PyTorch bundles its own)
- Existing ncnn-vulkan binaries kept for fallback

### Compatibility
- Minimum: NVIDIA GPU with 4GB+ VRAM, CUDA compute capability 3.5+
- Recommended: 8GB+ VRAM for 2x, 12GB+ for 4x
- CPU-only fallback: ncnn-vulkan path (no regression)

---

## Configuration & UI Changes

### New User-Facing Settings
- **Processing mode:**
  - "Auto" (default) - smart pipeline: N=4 keyframes, motion-aware fallback
  - "Quality" - every frame AI-upscaled via PyTorch (still faster than ncnn due to batching/FP16)
  - "Fast" - N=8 keyframes, higher interpolation ratio
- **Keyframe interval (N):** advanced setting, default 4, range 2-8

### Existing Settings
- Tile size stays, becomes automatic by default (VRAM-aware)
- Model selection stays (realesrgan-x4plus, animevideov3, etc.)
- Scale (2x/4x) and codec (H.264/H.265) unchanged

### Progress Reporting Updates
- Show frame classification: `X keyframes | Y interpolated | Z duplicates`
- Show current stage per chunk: extracting / upscaling / interpolating / encoding
- More accurate time estimates (based on actual keyframe count after classification)

### No Other UI Changes
Same upload flow, same output format, same API shape.

---

## Performance Estimates

For a 45-minute video at 24fps (~64,800 frames) at 2x:

| Optimization | Frames Upscaled | Time/Frame | Total |
|---|---|---|---|
| Current (ncnn-vulkan) | 64,800 | ~5.5s | ~100 hrs |
| PyTorch CUDA FP16 | 64,800 | ~1.2s | ~22 hrs |
| + Temporal interpolation (N=4) | ~16,200 | ~1.2s | ~5.4 hrs |
| + Frame deduplication | ~12,000 | ~1.2s | ~4 hrs |
| + Pipeline parallelism | ~12,000 | ~1.2s | **~3-3.5 hrs** |
