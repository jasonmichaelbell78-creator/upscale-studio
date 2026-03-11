import json
import math
import os
import shutil
import subprocess
import threading
import time
import uuid

CHUNK_SIZE = 1000  # frames per processing chunk

ALLOWED_MODELS = {"realesrgan-x4plus", "realesr-animevideov3", "realesrgan-x4plus-anime"}
ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".ts",
    ".mpg",
    ".mpeg",
    ".m2ts",
    ".vob",
}


class Job:
    def __init__(self, job_id, input_path, original_filename, video_info):
        self.job_id = job_id
        self.input_path = input_path
        self.original_filename = original_filename
        self.video_info = video_info
        self.status = "uploaded"
        self.phase = "Ready"
        self.current_frame = 0
        self.total_frames = 0
        self.current_chunk = 0
        self.total_chunks = 0
        self.start_time = None
        self.upscale_start_time = None
        self.upscale_frames_done = 0
        self.output_path = None
        self.process = None
        self.cancelled = False
        self.error = None


class PipelineManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.workspace = os.path.join(base_dir, "workspace")
        self.bin_dir = os.path.join(base_dir, "bin")

        ffmpeg_local = os.path.join(self.bin_dir, "ffmpeg", "ffmpeg.exe")
        ffprobe_local = os.path.join(self.bin_dir, "ffmpeg", "ffprobe.exe")
        self.ffmpeg = (
            ffmpeg_local
            if os.path.isfile(ffmpeg_local)
            else (shutil.which("ffmpeg") or ffmpeg_local)
        )
        self.ffprobe = (
            ffprobe_local
            if os.path.isfile(ffprobe_local)
            else (shutil.which("ffprobe") or ffprobe_local)
        )
        self.realesrgan = os.path.join(self.bin_dir, "realesrgan", "realesrgan-ncnn-vulkan.exe")

        self.jobs = {}
        os.makedirs(self.workspace, exist_ok=True)

    # ── Upload / Select ─────────────────────────────────────────

    def upload_video(self, file):
        ext = os.path.splitext(file.filename)[1].lower() or ".mp4"
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            accepted = ", ".join(sorted(ALLOWED_VIDEO_EXTENSIONS))
            raise ValueError(f"Unsupported file type: {ext}. Accepted: {accepted}")

        job_id = uuid.uuid4().hex[:8]
        job_dir = os.path.join(self.workspace, job_id)
        os.makedirs(job_dir, exist_ok=True)

        input_path = os.path.join(job_dir, f"input{ext}")
        with open(input_path, "wb") as dest:
            shutil.copyfileobj(file.file, dest)

        video_info = self._get_video_info(input_path)
        job = Job(job_id, input_path, file.filename, video_info)
        self.jobs[job_id] = job
        return {"job_id": job_id, "filename": file.filename, "video_info": video_info}

    def select_local_file(self, file_path):
        """Reference a local file without copying — ideal for large movies."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            accepted = ", ".join(sorted(ALLOWED_VIDEO_EXTENSIONS))
            raise ValueError(f"Unsupported file type: {ext}. Accepted: {accepted}")

        job_id = uuid.uuid4().hex[:8]
        job_dir = os.path.join(self.workspace, job_id)
        os.makedirs(job_dir, exist_ok=True)

        video_info = self._get_video_info(file_path)
        filename = os.path.basename(file_path)
        job = Job(job_id, file_path, filename, video_info)
        self.jobs[job_id] = job
        return {"job_id": job_id, "filename": filename, "video_info": video_info}

    # ── Video info ──────────────────────────────────────────────

    def _get_video_info(self, path):
        cmd = [
            self.ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")

        data = json.loads(result.stdout)
        video_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
            None,
        )
        if not video_stream:
            raise RuntimeError("No video stream found in the uploaded file")

        fps_str = video_stream.get("r_frame_rate", "30/1")
        parts = fps_str.split("/")
        if len(parts) == 2 and float(parts[1]) != 0:
            fps = float(parts[0]) / float(parts[1])
        else:
            fps = 30.0

        duration = float(data["format"].get("duration", 0))
        size_bytes = int(data["format"].get("size", 0))
        has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
        has_subtitles = any(s.get("codec_type") == "subtitle" for s in data.get("streams", []))

        nb_frames = video_stream.get("nb_frames")
        total_frames = int(nb_frames) if nb_frames and nb_frames != "N/A" else int(fps * duration)

        return {
            "width": int(video_stream["width"]),
            "height": int(video_stream["height"]),
            "fps": round(fps, 3),
            "duration": round(duration, 2),
            "size_bytes": size_bytes,
            "codec": video_stream.get("codec_name", "unknown"),
            "has_audio": has_audio,
            "has_subtitles": has_subtitles,
            "total_frames": total_frames,
        }

    # ── Disk space estimation ───────────────────────────────────

    def estimate_disk_usage(self, job_id, scale):
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")

        w, h = job.video_info["width"], job.video_info["height"]
        total_frames = job.video_info["total_frames"]

        input_frame_bytes = w * h * 1.5
        output_frame_bytes = (w * scale) * (h * scale) * 1.5
        chunk_temp = CHUNK_SIZE * (input_frame_bytes + output_frame_bytes)
        segment_total = total_frames * 100_000
        peak_usage = chunk_temp + segment_total

        secs_per_frame = 3.0 if scale == 2 else 7.0
        est_hours = (total_frames * secs_per_frame) / 3600

        disk_stat = shutil.disk_usage(self.workspace)

        return {
            "estimated_bytes": int(peak_usage),
            "estimated_gb": round(peak_usage / (1024**3), 1),
            "available_bytes": disk_stat.free,
            "available_gb": round(disk_stat.free / (1024**3), 1),
            "sufficient": disk_stat.free > peak_usage * 1.2,
            "chunk_size": CHUNK_SIZE,
            "total_chunks": math.ceil(total_frames / CHUNK_SIZE),
            "est_hours": round(est_hours, 1),
        }

    # ── Preview ─────────────────────────────────────────────────

    def generate_preview(self, job_id, scale, model, tile_size):
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")
        if model not in ALLOWED_MODELS:
            raise ValueError(f"Unsupported model: {model}")

        job_dir = os.path.join(self.workspace, job_id)
        preview_dir = os.path.join(job_dir, "preview")
        os.makedirs(preview_dir, exist_ok=True)

        timestamp = max(job.video_info["duration"] * 0.3, 0)

        original_path = os.path.join(preview_dir, "original.png")
        cmd = [
            self.ffmpeg,
            "-y",
            "-ss",
            str(timestamp),
            "-i",
            job.input_path,
            "-frames:v",
            "1",
            original_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to extract preview frame: {result.stderr}")

        upscaled_path = os.path.join(preview_dir, "upscaled.png")
        cmd = [
            self.realesrgan,
            "-i",
            original_path,
            "-o",
            upscaled_path,
            "-n",
            model,
            "-s",
            str(scale),
            "-f",
            "png",
        ]
        if tile_size > 0:
            cmd.extend(["-t", str(tile_size)])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Real-ESRGAN preview failed: {result.stderr}")

        w, h = job.video_info["width"], job.video_info["height"]
        return {
            "original_url": f"/api/files/{job_id}/preview/original.png",
            "upscaled_url": f"/api/files/{job_id}/preview/upscaled.png",
            "original_res": f"{w}x{h}",
            "upscaled_res": f"{w * scale}x{h * scale}",
        }

    # ── Chunked upscale pipeline ────────────────────────────────

    def start_upscale(self, job_id, scale, model, codec, tile_size):
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")
        if job.status in ("extracting", "upscaling", "encoding", "reassembling"):
            raise ValueError("Job is already running")
        if model not in ALLOWED_MODELS:
            raise ValueError(f"Unsupported model: {model}")

        job.status = "starting"
        job.cancelled = False
        job.error = None
        job.start_time = time.time()
        job.upscale_start_time = None
        job.upscale_frames_done = 0

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(job, scale, model, codec, tile_size),
            daemon=True,
        )
        thread.start()

    def _run_pipeline(self, job, scale, model, codec, tile_size):
        """Chunked pipeline: extract->upscale->encode per chunk, then concat.
        Uses frame-accurate seeking with cumulative frame tracking to prevent
        audio/video drift over long movies."""
        job_dir = os.path.join(self.workspace, job.job_id)
        segments_dir = os.path.join(job_dir, "segments")
        chunk_dir = os.path.join(job_dir, "chunk_tmp")

        try:
            os.makedirs(segments_dir, exist_ok=True)

            total_frames = job.video_info["total_frames"]
            fps = job.video_info["fps"]
            total_chunks = math.ceil(total_frames / CHUNK_SIZE)

            job.total_frames = total_frames
            job.total_chunks = total_chunks
            job.current_frame = 0
            job.current_chunk = 0

            segment_paths = []
            cumulative_frames = 0  # track actual extracted frames for accurate seeking

            for chunk_idx in range(total_chunks):
                if job.cancelled:
                    break

                job.current_chunk = chunk_idx + 1
                frames_in_chunk = min(CHUNK_SIZE, total_frames - cumulative_frames)
                if frames_in_chunk <= 0:
                    break

                # Frame-accurate seek position based on actual frames extracted so far
                start_time_sec = cumulative_frames / fps

                frames_subdir = os.path.join(chunk_dir, "input")
                upscaled_subdir = os.path.join(chunk_dir, "output")

                if os.path.exists(chunk_dir):
                    shutil.rmtree(chunk_dir, ignore_errors=True)
                os.makedirs(frames_subdir, exist_ok=True)
                os.makedirs(upscaled_subdir, exist_ok=True)

                # Step 1: Extract chunk frames (frame-accurate: -ss after -i)
                job.status = "extracting"
                job.phase = f"Extracting frames (chunk {chunk_idx + 1}/{total_chunks})..."
                self._extract_chunk(job, chunk_dir, frames_subdir, start_time_sec, frames_in_chunk)
                if job.cancelled:
                    break

                actual_extracted = self._count_pngs(frames_subdir)
                if actual_extracted == 0:
                    break

                # Step 2: Upscale chunk
                if job.upscale_start_time is None:
                    job.upscale_start_time = time.time()  # start ETA clock on first upscale
                job.status = "upscaling"
                job.phase = f"Upscaling (chunk {chunk_idx + 1}/{total_chunks})..."
                self._upscale_chunk(
                    job,
                    chunk_dir,
                    frames_subdir,
                    upscaled_subdir,
                    scale,
                    model,
                    tile_size,
                    cumulative_frames,
                    actual_extracted,
                )
                if job.cancelled:
                    break

                # Step 3: Encode upscaled frames to video segment
                job.status = "encoding"
                job.phase = f"Encoding segment {chunk_idx + 1}/{total_chunks}..."
                segment_path = os.path.join(segments_dir, f"seg_{chunk_idx:05d}.mp4")
                self._encode_segment(job, chunk_dir, upscaled_subdir, segment_path, fps, codec)
                if job.cancelled:
                    break
                segment_paths.append(segment_path)

                # Step 4: Delete PNGs, advance cumulative counter
                shutil.rmtree(chunk_dir, ignore_errors=True)
                cumulative_frames += actual_extracted
                job.current_frame = cumulative_frames
                job.upscale_frames_done = cumulative_frames

            if job.cancelled:
                return

            if not segment_paths:
                raise RuntimeError("No video segments were produced. The input may be corrupt.")

            # Final: Concatenate segments + mux original audio/subtitles
            job.status = "reassembling"
            job.phase = "Concatenating segments and adding audio..."
            output_path = os.path.join(job_dir, "output.mp4")
            self._concat_and_mux(job, segments_dir, segment_paths, output_path)
            if job.cancelled:
                return

            shutil.rmtree(segments_dir, ignore_errors=True)
            if os.path.exists(chunk_dir):
                shutil.rmtree(chunk_dir, ignore_errors=True)

            job.output_path = output_path
            job.status = "done"
            job.phase = "Complete!"

        except Exception as e:
            job.status = "error"
            job.error = str(e)
            job.phase = f"Error: {e}"

        finally:
            if job.cancelled or job.status == "error":
                time.sleep(1)  # let subprocesses release file handles on Windows
                for subdir in [chunk_dir, segments_dir]:
                    if os.path.exists(subdir):
                        shutil.rmtree(subdir, ignore_errors=True)

    # ── Pipeline helpers ────────────────────────────────────────

    @staticmethod
    def _count_pngs(directory):
        try:
            return sum(1 for f in os.listdir(directory) if f.endswith(".png"))
        except FileNotFoundError:
            return 0

    def _kill_and_wait(self, process):
        """Kill a subprocess and wait for handle cleanup (Windows-safe)."""
        try:
            process.kill()
            process.wait(timeout=10)
        except Exception:
            pass

    def _extract_chunk(self, job, chunk_dir, frames_dir, start_time, num_frames):
        """Extract frames with -ss after -i for frame-accurate seeking."""
        cmd = [
            self.ffmpeg,
            "-i",
            job.input_path,
            "-ss",
            f"{start_time:.6f}",  # after -i = frame-accurate (decode from keyframe)
            "-frames:v",
            str(num_frames),
            "-qscale:v",
            "1",
            "-qmin",
            "1",
            "-qmax",
            "1",
            "-fps_mode",
            "passthrough",
            os.path.join(frames_dir, "%08d.png"),
        ]

        log_path = os.path.join(chunk_dir, "ffmpeg_extract.log")
        with open(log_path, "w") as log_file:
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_file)
            job.process = process

            while process.poll() is None:
                if job.cancelled:
                    self._kill_and_wait(process)
                    return
                time.sleep(0.5)

        if process.returncode != 0 and not job.cancelled:
            error_text = self._read_log_tail(log_path)
            raise RuntimeError(f"FFmpeg frame extraction failed:\n{error_text}")

    def _upscale_chunk(
        self,
        job,
        chunk_dir,
        input_dir,
        output_dir,
        scale,
        model,
        tile_size,
        frame_offset,
        chunk_frame_count,
    ):
        cmd = [
            self.realesrgan,
            "-i",
            input_dir,
            "-o",
            output_dir,
            "-n",
            model,
            "-s",
            str(scale),
            "-f",
            "png",
        ]
        if tile_size > 0:
            cmd.extend(["-t", str(tile_size)])

        log_path = os.path.join(chunk_dir, "realesrgan.log")
        with open(log_path, "w") as log_file:
            process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            job.process = process

            while process.poll() is None:
                if job.cancelled:
                    self._kill_and_wait(process)
                    return
                completed = self._count_pngs(output_dir)
                job.current_frame = frame_offset + completed
                time.sleep(1)

        completed = self._count_pngs(output_dir)
        job.current_frame = frame_offset + completed

        if process.returncode != 0 and not job.cancelled:
            error_text = self._read_log_tail(log_path)
            raise RuntimeError(f"Real-ESRGAN upscaling failed:\n{error_text}")

    def _encode_segment(self, job, chunk_dir, frames_dir, output_path, fps, codec):
        cmd = [
            self.ffmpeg,
            "-y",
            "-framerate",
            str(fps),
            "-i",
            os.path.join(frames_dir, "%08d.png"),
        ]
        if codec == "libx265":
            cmd.extend(
                [
                    "-c:v",
                    "libx265",
                    "-crf",
                    "20",
                    "-preset",
                    "medium",
                    "-pix_fmt",
                    "yuv420p",
                    "-tag:v",
                    "hvc1",
                ]
            )
        else:
            cmd.extend(
                ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"]
            )
        cmd.append(output_path)

        log_path = os.path.join(chunk_dir, "ffmpeg_encode.log")
        with open(log_path, "w") as log_file:
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_file)
            job.process = process

            while process.poll() is None:
                if job.cancelled:
                    self._kill_and_wait(process)
                    return
                time.sleep(1)

        if process.returncode != 0 and not job.cancelled:
            error_text = self._read_log_tail(log_path)
            raise RuntimeError(f"FFmpeg segment encoding failed:\n{error_text}")

    def _concat_and_mux(self, job, segments_dir, segment_paths, output_path):
        concat_list = os.path.join(segments_dir, "concat.txt")
        with open(concat_list, "w") as f:
            for seg_path in segment_paths:
                safe_path = seg_path.replace("\\", "/")
                f.write(f"file '{safe_path}'\n")

        cmd = [
            self.ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list,
            "-i",
            job.input_path,
            "-map",
            "0:v:0",
        ]
        if job.video_info["has_audio"]:
            cmd.extend(["-map", "1:a?", "-c:a", "copy"])
        if job.video_info.get("has_subtitles"):
            cmd.extend(["-map", "1:s?", "-c:s", "mov_text"])
        cmd.extend(["-c:v", "copy"])
        cmd.append(output_path)

        log_path = os.path.join(segments_dir, "ffmpeg_concat.log")
        with open(log_path, "w") as log_file:
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_file)
            job.process = process

            while process.poll() is None:
                if job.cancelled:
                    self._kill_and_wait(process)
                    return
                time.sleep(1)

        if process.returncode != 0 and not job.cancelled:
            error_text = self._read_log_tail(log_path)
            raise RuntimeError(f"FFmpeg concatenation failed:\n{error_text}")

    @staticmethod
    def _read_log_tail(log_path, max_chars=2000):
        try:
            with open(log_path, errors="replace") as f:
                content = f.read()
                return content[-max_chars:] if len(content) > max_chars else content
        except Exception:
            return "(could not read log file)"

    # ── Status / control ────────────────────────────────────────

    def get_status(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")

        now = time.time()
        elapsed = now - job.start_time if job.start_time else 0
        upscale_elapsed = now - job.upscale_start_time if job.upscale_start_time else 0

        return {
            "job_id": job.job_id,
            "status": job.status,
            "phase": job.phase,
            "current_frame": job.current_frame,
            "total_frames": job.total_frames,
            "current_chunk": job.current_chunk,
            "total_chunks": job.total_chunks,
            "elapsed": round(elapsed, 1),
            "upscale_elapsed": round(upscale_elapsed, 1),
            "upscale_frames_done": job.upscale_frames_done,
            "start_time": job.start_time,
            "error": job.error,
            "output_ready": job.status == "done",
        }

    def cancel_job(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")

        job.cancelled = True
        job.status = "cancelled"
        job.phase = "Cancelled by user"

        # Kill subprocess; cleanup is handled by the pipeline thread's finally block
        if job.process and job.process.poll() is None:
            self._kill_and_wait(job.process)

    def get_output_path(self, job_id):
        job = self.jobs.get(job_id)
        if not job or not job.output_path:
            return None
        if os.path.isfile(job.output_path):
            return job.output_path
        return None
