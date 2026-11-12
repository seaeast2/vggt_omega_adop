"""Extract fixed RGB originals and exercise the pinned official preprocessor."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", type=Path, required=True)
    p.add_argument("--archive", type=Path, required=True)
    args = p.parse_args()
    from PIL import Image
    import numpy as np
    from vggt_omega.utils.load_fn import load_and_preprocess_images
    config = json.loads(Path("experiments/pointmap_refinement/P0/configs/p0.json").read_text())
    dest = args.stage / "artifacts/data"
    rows = []
    with tarfile.open(args.archive, "r:gz") as tar:
        rgb_file = tar.extractfile("rgbd_dataset_freiburg1_desk/rgb.txt")
        lines = [s.split() for s in rgb_file.read().decode().splitlines() if s.strip() and not s.startswith("#")]
        for idx in config["rgb_indices_zero_based"]:
            timestamp, name = lines[idx]
            data = tar.extractfile("rgbd_dataset_freiburg1_desk/" + name).read()
            path = dest / Path(name).name
            with path.open("xb") as f:
                f.write(data)
            size = list(Image.open(io.BytesIO(data)).size)
            rows.append({"index": idx, "timestamp": timestamp, "source_member": name,
                         "path": str(path), "sha256": sha(path), "original_wh": size})
    result = {"dataset_url": config["dataset_url"], "archive": str(args.archive),
              "archive_sha256": sha(args.archive), "checksum_scope": "observed local hash; not a publisher checksum",
              "frames": rows, "purpose": "P0 smoke input only; no geometry accuracy claim", "gt_used": False}
    (dest / "frames.json").write_text(json.dumps(result, indent=2) + "\n")
    checks = []
    for mode in config["preprocess_modes"]:
        for n in config["frame_counts"]:
            images = load_and_preprocess_images([r["path"] for r in rows[:n]], mode=mode, image_resolution=512)
            a = images.numpy()
            assert np.isfinite(a).all() and 0 <= a.min() <= a.max() <= 1
            path = dest / f"rgb_{mode}_n{n:02d}.npy"
            np.save(path, a)
            checks.append({"mode": mode, "n": n, "shape": list(a.shape), "sha256": sha(path),
                           "original_wh": rows[0]["original_wh"], "crop": "none (640x480 aspect ratio within supported bounds)",
                           "padding": "none (all frames have equal size)", "resize": "official BICUBIC; output shape recorded"})
    (args.stage / "evaluation/preprocessing.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
