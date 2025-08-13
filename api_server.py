import asyncio
import uuid
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

from agents.task_executor import TaskExecutorAgent
from agents.task_updater import TaskUpdaterAgent
from agents.report_generator import ReportGeneratorAgent
from main import ManusCloneWorkflow


class RunRequest(BaseModel):
    input: str
    max_results: int = 10
    verbose: bool = True


class JobState(BaseModel):
    id: str
    status: str
    created_at: str
    updated_at: str
    input: str
    max_results: int
    verbose: bool
    progress: float = 0.0
    logs: list[str] = []
    results: Optional[dict] = None
    error: Optional[str] = None


app = FastAPI(title="Manus Clone API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs: Dict[str, JobState] = {}


@app.get("/")
async def root_index():
    return FileResponse("frontend/index.html")


async def _run_workflow_background(job_id: str):
    job = jobs[job_id]
    job.logs.append("Job created")
    job.status = "running"
    job.updated_at = datetime.utcnow().isoformat()
    jobs[job_id] = job

    try:
        workflow = ManusCloneWorkflow()
        job.logs.append("Workflow initialized")
        jobs[job_id] = job

        results = await workflow.execute_workflow(
            job.input, max_results=job.max_results, verbose=job.verbose
        )

        job.results = results
        job.status = "completed"
        job.progress = 100.0
        job.logs.append("Workflow completed")
        job.updated_at = datetime.utcnow().isoformat()
        jobs[job_id] = job
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.logs.append(f"Error: {e}")
        job.updated_at = datetime.utcnow().isoformat()
        jobs[job_id] = job


@app.post("/api/run")
async def api_run(req: RunRequest):
    if not req.input or not req.input.strip():
        raise HTTPException(status_code=400, detail="input is required")

    job_id = uuid.uuid4().hex[:12]
    now = datetime.utcnow().isoformat()
    jobs[job_id] = JobState(
        id=job_id,
        status="queued",
        created_at=now,
        updated_at=now,
        input=req.input.strip(),
        max_results=max(req.max_results, 1),
        verbose=req.verbose,
        logs=["Job queued", f"Input: {req.input.strip()}"]
    )

    asyncio.create_task(_run_workflow_background(job_id))
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def api_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/api/report/{job_id}")
async def api_report(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.results or not job.results.get("final_report"):
        return PlainTextResponse("Report not available", status_code=404)
    return PlainTextResponse(job.results.get("final_report"), media_type="text/plain; charset=utf-8")


@app.get("/api/logs/{job_id}")
async def api_logs(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"logs": job.logs, "status": job.status, "progress": job.progress}


@app.get("/api/results/{job_id}")
async def api_results(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.results:
        raise HTTPException(status_code=404, detail="results not available")
    return job.results


# Health check
@app.get("/api/health")
async def api_health():
    return {"status": "ok"}


