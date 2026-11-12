"""One fresh process per P0 inference trial; requires the official checkpoint."""
import argparse
import hashlib
import json
from pathlib import Path
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--frames", type=Path, required=True)
    p.add_argument("--mode", choices=["max_size", "balanced"], required=True)
    p.add_argument("--count", type=int, choices=[2, 3, 4], required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if not args.checkpoint.is_file():
        raise FileNotFoundError(args.checkpoint)
    args.output.mkdir(parents=True, exist_ok=False)
    import numpy as np
    import torch
    from vggt_omega.models import VGGTOmega
    from vggt_omega.utils.load_fn import load_and_preprocess_images
    from vggt_omega.utils.pose_enc import encoding_to_camera
    torch.manual_seed(0)
    torch.cuda.init()
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    start = time.perf_counter()
    metrics = {"status": "running", "mode": args.mode, "count": args.count,
               "seed": 0, "model_parameters": "float32; official internal autocast enabled",
               "checkpoint": str(args.checkpoint), "input_manifest": str(args.frames)}
    try:
        frames = json.loads(args.frames.read_text())["frames"][:args.count]
        model = VGGTOmega().eval()
        model.load_state_dict(torch.load(args.checkpoint, map_location="cpu", weights_only=True), strict=True)
        model = model.to("cuda")
        images = load_and_preprocess_images([r["path"] for r in frames], mode=args.mode, image_resolution=512).to("cuda")
        torch.cuda.synchronize()
        forward_start = time.perf_counter()
        with torch.inference_mode():
            pred = model(images)
            extr, intr = encoding_to_camera(pred["pose_enc"], pred["images"].shape[-2:])
        torch.cuda.synchronize()
        metrics["forward_and_camera_seconds"] = time.perf_counter() - forward_start
        metrics["load_and_inference_seconds"] = time.perf_counter() - start
        pred.update(extrinsics=extr, intrinsics=intr)
        arrays = {k: v.detach().float().cpu().numpy() for k, v in pred.items() if isinstance(v, torch.Tensor)}
        assert {"pose_enc", "images", "depth", "depth_conf", "extrinsics", "intrinsics"} <= arrays.keys()
        for name, array in arrays.items():
            assert np.isfinite(array).all(), name
        assert arrays["images"].shape[:2] == (1, args.count)
        assert (arrays["depth"] > 0).all()
        np.savez_compressed(args.output / "vggt_omega_raw.npz", **arrays)
        with np.load(args.output / "vggt_omega_raw.npz") as saved:
            assert set(saved.files) == set(arrays)
            for k in saved.files:
                assert np.array_equal(saved[k], arrays[k]), k
        metrics.update(status="completed", shapes={k: list(v.shape) for k, v in arrays.items()},
                       npz_sha256=hashlib.sha256((args.output / "vggt_omega_raw.npz").read_bytes()).hexdigest())
    except Exception as e:
        metrics.update(status="failed", error_type=type(e).__name__, error=str(e))
        raise
    finally:
        metrics.update(peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                       peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                       process_seconds=time.perf_counter() - start)
        (args.output / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
