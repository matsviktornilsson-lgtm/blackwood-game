"""Publish a verified Blackwood model and its evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}", re.ASCII)
MAX_FILE_BYTES = 400 * 1024 * 1024
CPU_ONLY = "CPU (ingen GPU-variant)"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class PipelineError(Exception):
    pass


def identifier(value: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value) or re.fullmatch(r"con|prn|aux|nul|(?:com|lpt)[0-9]", value):
        raise PipelineError(f"INVALID_ID: {value!r}")
    return value


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise PipelineError(f"INVALID_JSON_OBJECT: {path}")
    return value


def write_json(path: Path, value: dict, *, exclusive=False) -> None:
    with path.open("x" if exclusive else "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def atomic_json(path: Path, value: dict) -> None:
    with tempfile.TemporaryDirectory(prefix=".blackwood-", dir=path.parent) as directory:
        staged = Path(directory) / path.name
        write_json(staged, value)
        staged.replace(path)


def check_glb(path: Path, *, baked=False) -> dict:
    with path.open("rb") as handle:
        header = handle.read(20)
        if len(header) != 20:
            raise PipelineError(f"INVALID_GLB: {path}")
        magic, version, declared, json_size, chunk = struct.unpack("<4sIIII", header)
        if (magic, version, declared, chunk) != (b"glTF", 2, path.stat().st_size, 0x4E4F534A):
            raise PipelineError(f"INVALID_GLB_HEADER: {path}")
        if not json_size or json_size % 4 or json_size > min(declared - 20, 32 * 1024 * 1024):
            raise PipelineError(f"INVALID_GLB_JSON_CHUNK: {path}")
        doc = json.loads(handle.read(json_size))
        binary_size = 0
        if handle.tell() < declared:
            chunk_header = handle.read(8)
            if len(chunk_header) != 8:
                raise PipelineError(f"INVALID_GLB_BINARY_CHUNK: {path}")
            binary_size, chunk = struct.unpack("<II", chunk_header)
            if chunk != 0x004E4942 or binary_size % 4 or handle.tell() + binary_size != declared:
                raise PipelineError(f"INVALID_GLB_BINARY_CHUNK: {path}")
    if doc.get("asset", {}).get("version") != "2.0" or not doc.get("meshes"):
        raise PipelineError(f"INVALID_GLB_MESH: {path}")
    buffers = doc.get("buffers", [])
    if len(buffers) != 1 or not 0 <= binary_size - buffers[0].get("byteLength", -1) <= 3:
        raise PipelineError(f"INVALID_GLB_BUFFER: {path}")
    if any("uri" in item for key in ("images", "buffers") for item in doc.get(key, [])):
        raise PipelineError(f"GLB_EXTERNAL_RESOURCE: {path}")
    accessors = doc.get("accessors", [])
    views = doc.get("bufferViews", [])
    for view in views:
        offset, length = view.get("byteOffset", 0), view["byteLength"]
        if view["buffer"] != 0 or offset < 0 or length <= 0 or offset + length > buffers[0]["byteLength"]:
            raise PipelineError(f"INVALID_GLB_BUFFER_VIEW: {path}")
    for mesh in doc["meshes"]:
        for primitive in mesh["primitives"]:
            index = primitive.get("attributes", {}).get("POSITION", -1)
            if not 0 <= index < len(accessors) or accessors[index].get("count", 0) < 3:
                raise PipelineError(f"INVALID_GLB_POSITION: {path}")
    if baked and any({"occlusionTexture", "normalTexture"} & material.keys() for material in doc.get("materials", [])):
        raise PipelineError(f"BAKED_MATERIAL: AO or normal texture in {path}")
    return doc


def check_png(path: Path) -> None:
    with path.open("rb") as handle:
        if handle.read(len(PNG_MAGIC)) != PNG_MAGIC:
            raise PipelineError(f"INVALID_PNG: {path}")
        seen = set()
        while header := handle.read(8):
            if len(header) != 8:
                break
            length, chunk = struct.unpack(">I4s", header)
            if length > min(path.stat().st_size - handle.tell() - 4, MAX_FILE_BYTES):
                break
            data, crc = handle.read(length), handle.read(4)
            if len(crc) != 4 or zlib.crc32(chunk + data) != int.from_bytes(crc, "big"):
                break
            if not seen and (chunk != b"IHDR" or length != 13 or not all(struct.unpack(">II", data[:8]))):
                break
            if chunk == b"IEND" and not length and b"IDAT" in seen and not handle.read(1):
                return
            seen.add(chunk)
    raise PipelineError(f"INVALID_PNG: {path}")


def artifact(path: Path, role: str) -> dict:
    return {"file": path.name, "role": role, "sha256": sha256(path), "bytes": path.stat().st_size}


def require_artifact(report: dict, candidate: dict) -> None:
    matches = [entry for entry in report.get("artifacts", []) if entry.get("file") == candidate["file"]]
    if len(matches) != 1 or matches[0].get("role") != candidate["role"]:
        raise PipelineError(f"ARTIFACT_ROLE: {candidate['file']} requires one {candidate['role']} entry in the report.")
    if matches[0].get("sha256") != candidate["sha256"]:
        raise PipelineError(f"ARTIFACT_HASH: {candidate['file']} does not match the report.")


def verify_files(directory: Path, entries: list[dict]) -> None:
    for entry in entries:
        path = directory / entry["file"]
        if not path.is_file() or path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            raise PipelineError(f"HANDOFF_HASH: {path}")


def update_latest(model_dir: Path, manifest: dict, model: str, publication: str) -> None:
    # The pointer always names a verified publication. Serialise updates so a retry
    # of an earlier run cannot move it backwards.
    import msvcrt

    pointer = model_dir / "latest.json"
    with (model_dir / ".latest.lock").open("a+b") as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        if pointer.exists() and read_json(pointer).get("created_utc", "") >= manifest["created_utc"]:
            return
        atomic_json(pointer, {key: manifest[key] for key in ("run", "stage", "created_utc")} |
                    {"publication": publication, "glb": [model]})


def model_metrics(report):
    diagnostics = report.get("diagnostics", report)
    return {
        "triangles": diagnostics.get("game_triangles", diagnostics.get("triangles")),
        "height_m": diagnostics.get("height_m"),
        "silhouette_iou": diagnostics.get("silhouette_iou") or report.get("silhouette_iou"),
        "projection_iou": diagnostics.get("alignment", {}).get("iou", diagnostics.get("projection_iou")),
        "device": report.get("device", diagnostics.get("device")),
    }


def publish(root, name, stage, report_path, model, previews, run=None, note="", dry_run=False, *, publication=None):
    identifier(name)
    if not (root / "web/package.json").is_file():
        raise PipelineError(f"REPO_INVALID: {root}")
    if stage not in {"game", "baked", "projected", "rigged"} or model.suffix.lower() != ".glb" or "raw" in re.split(r"[_. -]+", model.stem.lower()):
        raise PipelineError(f"ARTIFACT_ROLE: expected a playable GLB, got {model}")
    if report_path.suffix.lower() != ".json" or not previews or any(p.suffix.lower() != ".png" for p in previews):
        raise PipelineError("ARTIFACT_TYPE: provide a JSON report and at least one explicit PNG preview.")
    sources = [model, report_path, *previews]
    names = [path.name.casefold() for path in sources]
    if len(set(names)) != len(names) or "manifest.json" in names:
        raise PipelineError("HANDOFF_FILENAME: duplicate or reserved filename.")
    for path in sources:
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_FILE_BYTES:
            raise PipelineError(f"ARTIFACT_SIZE_OR_MISSING: {path}")
    report = read_json(report_path)
    run_id = identifier(run or report.get("run", ""))
    if report.get("run") != run_id:
        raise PipelineError("HANDOFF_RUN: run does not match the report.")
    document = check_glb(model, baked=stage in {"baked", "projected"})
    if stage == "rigged" and not document.get("skins"):
        raise PipelineError(f"RIG_REQUIRED: {model}")
    for preview in previews:
        check_png(preview)
    roles = {entry.get("role") for entry in report.get("artifacts", [])}
    role = "baked" if stage == "projected" and "projected" not in roles else stage
    candidate = artifact(model, role)
    require_artifact(report, candidate)
    entries = [candidate, artifact(report_path, "report"), *[artifact(path, "preview") for path in previews]]
    if "previews" in report and sorted(report["previews"], key=lambda item: item["file"]) != sorted(
            entries[2:], key=lambda item: item["file"]):
        raise PipelineError("HANDOFF_PREVIEWS: preview files do not match the report.")
    model_dir = root / "3d/incoming" / name
    target = model_dir / identifier(publication or run_id)
    result = {"candidate": str(target / model.name), "lab_path": (target / model.name).relative_to(root).as_posix(),
              "device": CPU_ONLY,
              "manifest": str(target / "manifest.json")}
    if dry_run:
        return result
    if model_dir.resolve() != model_dir or target.resolve() != target:
        raise PipelineError("HANDOFF_PATH: publication path resolves outside its declared location.")
    model_dir.mkdir(parents=True, exist_ok=True)
    identity = {"name": name, "stage": stage, "run": run_id, "note": note, "files": entries}
    metadata = {
        "seed": report.get("seed"),
        "batch": report.get("batch"),
        "source": {key: report.get(key) for key in
                   ("concept_sha256", "raw_sha256", "source_sha256", "projection_image_sha256")},
        **model_metrics(report),
    }
    if role == "game" and metadata["source"]["raw_sha256"] is None:
        metadata["source"]["raw_sha256"] = report.get("source_sha256")
    if not target.exists():
        with tempfile.TemporaryDirectory(prefix=".blackwood-", dir=model_dir) as directory:
            staged = Path(directory) / "candidate"
            staged.mkdir()
            for source in sources:
                shutil.copy2(source, staged / source.name)
            verify_files(staged, entries)
            require_artifact(read_json(staged / report_path.name), candidate)
            write_json(staged / "manifest.json", identity | metadata | {
                "created_utc": datetime.now(timezone.utc).isoformat(),
            })
            try:
                staged.rename(target)  # On Windows rename fails when the destination exists.
            except FileExistsError:
                pass
    manifest = read_json(target / "manifest.json")
    if any(manifest.get(key) != value for key, value in identity.items()):
        raise PipelineError(f"HANDOFF_CONFLICT: {target}")
    verify_files(target, entries)
    update_latest(model_dir, manifest, model.name, target.name)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="One GAME/baked GLB followed by explicit PNG previews.")
    parser.add_argument("--name", required=True)
    parser.add_argument("--stage", choices=("game", "projected", "rigged", "baked"), default="baked")
    parser.add_argument("--meta", type=Path, required=True, help="JSON report with run and candidate role/SHA-256.")
    parser.add_argument("--run")
    parser.add_argument("--note", default="")
    parser.add_argument("--game-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = publish(args.game_root.resolve(), args.name, args.stage, args.meta, args.files[0],
                         args.files[1:], args.run, args.note, args.dry_run)
        print(json.dumps(result))
    except (PipelineError, OSError, ValueError, KeyError, TypeError) as error:
        print(ascii(str(error)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
