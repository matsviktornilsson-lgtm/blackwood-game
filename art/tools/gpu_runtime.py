"""Blackwood's RTX 4090 requirement and per-job NVIDIA telemetry."""

import shutil
import subprocess
import threading
from pathlib import Path

from send_to_game import CPU_ONLY, PipelineError

GPU_NAME = "NVIDIA GeForce RTX 4090"


def nvidia_sample():
    exe = shutil.which("nvidia-smi.exe")
    if not exe:
        raise PipelineError("NVIDIA_SMI_MISSING: nvidia-smi.exe could not be located.")
    try:
        result = subprocess.run([str(Path(exe).resolve()), "--query-gpu=name,memory.used,utilization.gpu",
                                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=8, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise PipelineError("NVIDIA_SMI_FAILED: GPU telemetry is unavailable.") from error
    for line in result.stdout.splitlines():
        name, used, utilization = (part.strip() for part in line.split(","))
        if name == GPU_NAME:
            return {"name": name, "used_mib": int(used), "utilization_pct": int(utilization)}
    raise PipelineError(f"GPU_REQUIRED: nvidia-smi did not list {GPU_NAME}.")


def comfy_device(stats):
    argv = stats.get("system", {}).get("argv", [])
    if "--cpu" in argv:
        raise PipelineError("COMFY_CPU_MODE: ComfyUI was started with --cpu.")
    for entry in stats.get("devices", []):
        if entry.get("type") == "cuda" and GPU_NAME in entry.get("name", ""):
            return f"CUDA: {GPU_NAME}"
    raise PipelineError(f"COMFY_GPU_REQUIRED: /system_stats does not report CUDA on {GPU_NAME}.")


class VramMonitor:
    """Sample total used VRAM on the card, not per-process allocator statistics."""

    def __init__(self, sample=nvidia_sample, interval=0.6):
        self.sample = sample
        self.interval = interval
        self.samples = []
        self.error = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.poll, daemon=True)

    def __enter__(self):
        self.samples.append(self.sample())
        self.thread.start()
        return self

    def poll(self):
        while not self.stop.wait(self.interval):
            try:
                self.samples.append(self.sample())
            except (OSError, ValueError, subprocess.SubprocessError, PipelineError) as error:
                self.error = str(error)
                return

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join()

    def report(self):
        if self.error:
            raise PipelineError(f"VRAM_MONITOR_FAILED: {self.error}")
        peak = max(self.samples, key=lambda row: row["used_mib"])
        busy = max(self.samples, key=lambda row: row["utilization_pct"])
        return {"vram_peak_mib": peak["used_mib"], "vram_peak_scope": "sampled device total",
                "vram_samples": len(self.samples), "gpu_busy_sample": busy}
