import os
import webbrowser
import threading
import time

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from .pipeline import PipelineManager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pipeline = PipelineManager(BASE_DIR)

app = FastAPI(title="Upscale Studio")

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.on_event("startup")
async def startup_event():
    if os.environ.get("OPEN_BROWSER") == "1":
        def _open():
            time.sleep(1.5)
            webbrowser.open("http://localhost:8000")
        threading.Thread(target=_open, daemon=True).start()


@app.get("/")
async def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


@app.post("/api/upload")
def upload(file: UploadFile = File(...)):
    try:
        result = pipeline.upload_video(file)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/select-file")
def select_file(path: str = Form(...)):
    """Select a local file by path — avoids copying large movie files."""
    try:
        result = pipeline.select_local_file(path)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/preview")
def preview(
    job_id: str = Form(...),
    scale: int = Form(2),
    model: str = Form("realesrgan-x4plus"),
    tile_size: int = Form(0),
):
    try:
        result = pipeline.generate_preview(job_id, scale, model, tile_size)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/disk-space/{job_id}")
def disk_space(job_id: str, scale: int = 2):
    """Estimate disk space needed before starting upscale."""
    try:
        return pipeline.estimate_disk_usage(job_id, scale)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/upscale")
def upscale(
    job_id: str = Form(...),
    scale: int = Form(2),
    model: str = Form("realesrgan-x4plus"),
    codec: str = Form("libx264"),
    tile_size: int = Form(0),
):
    try:
        pipeline.start_upscale(job_id, scale, model, codec, tile_size)
        return {"status": "started", "job_id": job_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status/{job_id}")
def status(job_id: str):
    try:
        return pipeline.get_status(job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/cancel/{job_id}")
def cancel(job_id: str):
    try:
        pipeline.cancel_job(job_id)
        return {"status": "cancelled"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/download/{job_id}")
def download(job_id: str):
    path = pipeline.get_output_path(job_id)
    if not path:
        raise HTTPException(status_code=404, detail="Output file not found")
    job = pipeline.jobs.get(job_id)
    original_name = job.original_filename if job else "video"
    base = os.path.splitext(original_name)[0]
    return FileResponse(path, filename=f"{base}_upscaled.mp4", media_type="video/mp4")


@app.get("/api/files/{job_id}/{path:path}")
def serve_job_file(job_id: str, path: str):
    expected_prefix = os.path.realpath(os.path.join(pipeline.workspace, job_id))
    full_path = os.path.realpath(os.path.join(pipeline.workspace, job_id, path))
    if not full_path.startswith(expected_prefix + os.sep) and full_path != expected_prefix:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path)


if __name__ == "__main__":
    import uvicorn
    os.environ["OPEN_BROWSER"] = "1"
    uvicorn.run(app, host="127.0.0.1", port=8000)
