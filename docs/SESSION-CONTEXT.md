# Session Context: Performance Pipeline Redesign

**Date:** 2026-03-10
**Branch:** improvements
**Status:** Design approved, ready for implementation planning

## What We Did

Brainstormed and designed a major performance overhaul for the video upscaling pipeline. The current Real-ESRGAN ncnn-vulkan approach takes ~100 hours for a 45-minute video at 2x. The new design targets ~3-4 hours (25-30x speedup).

## Design Summary

Replace ncnn-vulkan subprocess calls with an in-process PyTorch CUDA pipeline featuring:

1. **PyTorch CUDA Real-ESRGAN (FP16)** - batch processing, no subprocess overhead, ~3-5x faster per frame
2. **RIFE temporal interpolation** - AI-upscale every 4th frame, interpolate the rest, ~75% fewer frames to upscale
3. **Conservative frame deduplication** - pHash >95% similarity skips, ~20-40% additional savings
4. **Motion-aware fallback** - fast-motion scenes auto-detected via optical flow, those frames get full AI upscale instead of interpolation
5. **Pipeline parallelism** - extract/upscale/encode run concurrently across chunks

Ncnn-vulkan kept as fallback for non-CUDA systems.

## Key Decisions Made

- Smart compromise approach: AI-upscale what matters, interpolate/copy the rest
- Single GPU target (no multi-GPU complexity)
- Conservative dedup only (>95% pHash similarity)
- Auto-detect fast motion and fallback to AI upscale (no artifacts on action scenes)
- Three processing modes: Auto (default), Quality (all AI), Fast (aggressive interp)
- Keyframe interval N=4 default, configurable 2-8

## Files Created

- `docs/superpowers/specs/2026-03-10-performance-pipeline-design.md` - Full approved spec

## Next Steps

1. Run the **writing-plans** skill to create a detailed implementation plan from the spec
2. Execute the plan (likely multi-phase: dependencies -> PyTorch backend -> frame classification -> RIFE integration -> pipeline parallelism -> UI updates)

## Codebase Context

- **Main pipeline code:** `app/pipeline.py` (~650 lines) - will be significantly refactored
- **API endpoints:** `app/main.py` (~143 lines) - minor changes for new settings
- **Binary setup:** `setup_env.py` - extend for RIFE model weights
- **Current chunk size:** 1000 frames (in pipeline.py)
- **Current models:** realesrgan-x4plus, realesr-animevideov3, realesrgan-x4plus-anime
