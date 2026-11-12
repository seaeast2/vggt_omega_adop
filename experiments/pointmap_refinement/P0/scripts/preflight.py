"""Run on the host. Record CUDA checks and gated-checkpoint access without secrets."""
import argparse
from datetime import datetime
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
from zoneinfo import ZoneInfo


def command(args):
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=30)
        return {"command": args, "returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except OSError as e:
        return {"command": args, "error": str(e)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    args = parser.parse_args()
    stage = args.stage
    import torch
    from huggingface_hub import get_token, hf_hub_url
    from huggingface_hub.utils import get_session
    from vggt_omega.models import VGGTOmega

    packages = ["torch", "torchvision", "numpy", "Pillow", "einops", "safetensors", "opencv-python", "huggingface_hub", "vggt-omega"]
    env = {
        "execution_context": "host outside sandbox (require_escalated)",
        "timestamp": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": {k: importlib.metadata.version(k) for k in packages},
        "nvidia_smi": command(["nvidia-smi"]), "nvcc": command(["nvcc", "--version"]),
        "os_release": Path("/etc/os-release").read_text(),
        "source_commit": command(["git", "-C", "thirdparty/vggt-omega", "rev-parse", "HEAD"]),
        "source_status": command(["git", "-C", "thirdparty/vggt-omega", "status", "--porcelain"]),
        "project_commit": command(["git", "rev-parse", "HEAD"]),
        "project_status": command(["git", "status", "--short"]),
        "torch_cuda_version": torch.version.cuda, "cuda_available": torch.cuda.is_available(),
        "model_import": VGGTOmega.__name__,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
    }
    if not torch.cuda.is_available():
        raise RuntimeError("Host CUDA is unavailable")
    torch.manual_seed(0)
    env.update(gpu=torch.cuda.get_device_name(0), capability=list(torch.cuda.get_device_capability(0)),
               total_vram_bytes=torch.cuda.get_device_properties(0).total_memory,
               torch_arch_list=torch.cuda.get_arch_list(), bf16_supported=torch.cuda.is_bf16_supported())
    checks = {}
    for dtype in [torch.float32, torch.bfloat16]:
        x = torch.eye(64, device="cuda", dtype=dtype)
        checks[str(dtype)] = bool(torch.equal(x @ x, x))
    q = torch.randn(1, 2, 32, 64, device="cuda", dtype=torch.bfloat16)
    attention = torch.nn.functional.scaled_dot_product_attention(q, q, q)
    checks["sdpa_finite"] = bool(torch.isfinite(attention).all())
    torch.cuda.synchronize()
    env["cuda_checks"] = checks
    (stage / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
    assert all(checks.values()), checks
    config = json.loads((stage / "config_resolved.json").read_text())
    token = get_token()
    url = hf_hub_url(config["checkpoint_repo"], config["checkpoint_filename"])
    response = get_session().head(url, headers={"Authorization": "Bearer " + token} if token else {}, follow_redirects=True, timeout=30)
    access = {"repo": config["checkpoint_repo"], "filename": config["checkpoint_filename"],
              "http_status": response.status_code, "error_code": response.headers.get("X-Error-Code"),
              "credential_present": bool(token), "accessible": response.status_code == 200}
    (stage / "evaluation/checkpoint_access.json").write_text(json.dumps(access, indent=2) + "\n")
    print(json.dumps({"cuda_checks": checks, "checkpoint_access": access}, indent=2))
    return 0 if access["accessible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
