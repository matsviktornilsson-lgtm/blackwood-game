"""Probe CUDA in the configured ComfyUI or TRELLIS Python without starting a server."""

import json
import sys

import torch

from gpu_runtime import GPU_NAME
from send_to_game import PipelineError


def cuda_4090():
    if not torch.cuda.is_available():
        raise PipelineError("CUDA_REQUIRED: torch.cuda.is_available() is False.")
    for index in range(torch.cuda.device_count()):
        if torch.cuda.get_device_name(index) == GPU_NAME:
            return torch.device(f"cuda:{index}")
    raise PipelineError(f"CUDA_REQUIRED: Torch did not find {GPU_NAME}.")


if __name__ == "__main__":
    device = cuda_4090()
    if "--compute" in sys.argv:
        torch.ones(8, device=device).sum().item()
    print(json.dumps({"device": f"CUDA: {torch.cuda.get_device_name(device)}", "cuda_is_available": True}))
