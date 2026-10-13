"""
FastAPI Server for DCN Packet Size Optimization Simulator
Serves the web UI and provides API endpoints for running simulations,
inspecting results, and executing packet_sim.py.
"""
import os
import subprocess
import json
import math
import random
from typing import Optional, List
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="DCN Packet Size Optimization Simulator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "results")


class SimulationRequest(BaseModel):
    bandwidth_bps: float = 10e6
    prop_delay_s: float = 0.010
    ber: float = 0.0
    header_bytes: int = 40
    ack_bytes: int = 40
    timeout_margin_s: float = 0.005
    max_retries: int = 100
    payload_bytes: int = 1024
    total_bytes: int = 500_000
    seed: Optional[int] = 42


class SweepRequest(BaseModel):
    bandwidth_bps: float = 10e6
    prop_delay_s: float = 0.010
    ber_values: List[float] = [0.0, 1e-6, 1e-5, 5e-5, 1e-4]
    sizes: List[int] = [64, 128, 256, 512, 1024, 1500, 2048, 4096, 8192]
    header_bytes: int = 40
    ack_bytes: int = 40
    timeout_margin_s: float = 0.005
    max_retries: int = 100
    total_bytes: int = 500_000
    trials: int = 5


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "DCN Packet Sim"}


@app.post("/api/run-python")
def run_python_script():
    """Runs the original packet_sim.py script synchronously and returns output."""
    script_path = os.path.join(BASE_DIR, "packet_sim.py")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="packet_sim.py not found")

    try:
        res = subprocess.run(
            ["python", script_path],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        return {
            "success": res.returncode == 0,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "returncode": res.returncode
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/results/summary")
def get_summary():
    """Returns the parsed summary.csv from the results directory."""
    csv_path = os.path.join(RESULTS_DIR, "summary.csv")
    if not os.path.exists(csv_path):
        return {"error": "summary.csv not generated yet", "data": []}
    try:
        df = pd.read_csv(csv_path)
        # Clean NaNs to None for valid JSON
        data = df.replace({float("nan"): None}).to_dict(orient="records")
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/results/images")
def list_images():
    """Lists generated visualization images."""
    if not os.path.exists(RESULTS_DIR):
        return {"images": []}
    files = [f for f in os.listdir(RESULTS_DIR) if f.endswith(".png")]
    return {"images": sorted(files)}


@app.get("/api/results/images/{filename}")
def get_image(filename: str):
    """Serves a generated visualization image."""
    img_path = os.path.join(RESULTS_DIR, filename)
    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(img_path)


@app.post("/api/simulate")
def simulate(req: SimulationRequest):
    """Runs a single simulation and returns detailed metrics + packet logs (first 500 packets)."""
    import packet_sim
    cfg = packet_sim.LinkConfig(
        bandwidth_bps=req.bandwidth_bps,
        prop_delay_s=req.prop_delay_s,
        ber=req.ber,
        header_bytes=req.header_bytes,
        ack_bytes=req.ack_bytes,
        timeout_margin_s=req.timeout_margin_s,
        max_retries=req.max_retries
    )
    rng = random.Random(req.seed or 42)
    log = []
    metrics = packet_sim.simulate_transfer(
        total_bytes=req.total_bytes,
        payload_bytes=req.payload_bytes,
        cfg=cfg,
        rng=rng,
        log=log,
        tag={"ber": req.ber, "size": req.payload_bytes}
    )
    # Return metrics and first 500 packet log entries to keep response light
    return {
        "metrics": metrics,
        "packet_sample": log[:500],
        "total_packets": metrics["packets"]
    }


# Serve static web files
app.mount("/results", StaticFiles(directory=RESULTS_DIR, check_dir=False), name="results")
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
