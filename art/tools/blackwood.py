"""Native Windows entry point for the Blackwood model pipeline."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from urllib.error import URLError
from urllib.parse import quote, urlsplit

from comfy import Comfy, collect_outputs, input_choices, validate_graph
from gpu_runtime import CPU_ONLY, VramMonitor, comfy_device, nvidia_sample
from send_to_game import (
    PipelineError, REPO_ROOT, artifact, check_glb, check_png, identifier, publish,
    model_metrics, read_json, require_artifact, sha256, write_json,
)

TOOLS = Path(__file__).resolve().parent
EXAMPLE = TOOLS / "blackwood.config.example.json"
LOCAL = TOOLS / "blackwood.config.local.json"
RIG = REPO_ROOT / "art/creatures/rig_generated_wolf.py"
WEB = REPO_ROOT / "web"
VITE = WEB / "node_modules/vite/bin/vite.js"
CONCEPT_PRESETS = ("concept", "concept-schnell", "concept-photo")
REPORTED_ACTIONS = frozenset({*CONCEPT_PRESETS, "3d", "game", "project", "rig", "compress", "handoff"})


def required_path(value, code, *, executable=False, relative=False, directory=False):
    if not value:
        raise PipelineError(f"{code}: configuration value is empty.")
    path = Path(value)
    if relative and not path.is_absolute():
        path = REPO_ROOT / path
    exists = path.is_dir() if directory else path.is_file()
    if not path.is_absolute() or not exists or executable and path.suffix.lower() != ".exe":
        raise PipelineError(f"{code}: {path}")
    return path.resolve()


def setting(config, key, code=None, **kwargs):
    return required_path(config.get(key), code or key.upper() + "_MISSING", **kwargs)


def command(executable, arguments, cwd, log):
    if not executable.is_absolute() or executable.suffix.lower() != ".exe":
        raise PipelineError(f"WINDOWS_EXECUTABLE_REQUIRED: {executable}")
    with log.open("xb") as output:
        process = subprocess.run([str(executable), *map(str, arguments)], cwd=cwd, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT,
                                 env=os.environ | {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    data = log.read_bytes()
    try:
        output_text = data.decode("utf-8")
    except UnicodeDecodeError:
        output_text = data.decode("cp1252", errors="replace")
        log.write_text(output_text, encoding="utf-8")
    if process.returncode:
        for line in reversed(output_text.splitlines()):
            for code in ("UV_QUALITY:", "PROJECTION_COVERAGE:"):
                if code in line and line.startswith(("send_to_game.PipelineError:", "ValueError:")):
                    raise PipelineError(f"{line[line.index(code):]}. Log: {log}")
        for code in ("BLENDER_GPU_REQUIRED", "CUDA_REQUIRED"):
            if code + ":" in output_text:
                raise PipelineError(f"{code}: {executable.name} could not use the required RTX 4090. Log: {log}")
        raise PipelineError(f"PROCESS_EXIT: {executable.name} exited {process.returncode}. Log: {log}")


def workflow(config, kind):
    path = required_path(config.get("workflows", {}).get(kind), "WORKFLOW_MISSING", relative=True)
    graph = read_json(path)
    if not graph or "nodes" in graph:
        raise PipelineError(f"WORKFLOW_API_FORMAT: {path}")
    binding = read_json(setting(config, "workflow_bindings", "BINDINGS_MISSING", relative=True)).get(kind)
    if not isinstance(binding, dict) or binding.get("workflow_sha256") != sha256(path):
        raise PipelineError(f"WORKFLOW_PIN: {path} needs reviewed bindings and matching SHA-256.")
    preset = binding.get("preset")
    if not preset:
        raise PipelineError(f"WORKFLOW_PRESET: {path.name} needs its reviewed production parameters.")
    for node_id, key, expected in preset:
        if graph[node_id]["inputs"].get(key) != expected:
            raise PipelineError(f"WORKFLOW_PRESET: {path.name} {node_id}.{key} expected {expected!r}.")
    return graph, binding


def bind(graph, binding, key, value):
    node_id, input_name = binding[key]
    inputs = graph[node_id]["inputs"]
    if input_name not in inputs:
        raise PipelineError(f"WORKFLOW_BINDING: {key} -> {node_id}.{input_name}")
    inputs[input_name] = value


def game_tools(config):
    return (
        setting(config, "blender", executable=True),
        setting(config, "game_adapter", relative=True),
    )


def projection_tools(config):
    return setting(config, "blender", executable=True), setting(config, "projection_adapter", relative=True)


def torch_gpu(exe):
    result = subprocess.run([str(exe), "-B", "-X", "utf8", str(TOOLS / "probe_torch_gpu.py")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
    if result.returncode:
        raise PipelineError("TORCH_CUDA_REQUIRED: " + (result.stderr.splitlines() or ["CUDA probe failed"])[-1])
    return json.loads(result.stdout.splitlines()[-1])


def blender_gpu(exe):
    argv = blender_args(TOOLS / "probe_blender_gpu.py")
    result = subprocess.run([str(exe), *map(str, argv)], cwd=REPO_ROOT, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=40)
    marker = "BLACKWOOD_GPU_REPORT="
    for line in result.stdout.splitlines():
        if line.startswith(marker) and not result.returncode:
            return json.loads(line[len(marker):])
    raise PipelineError("BLENDER_GPU_REQUIRED: background Cycles probe could not select the RTX 4090.")


def doctor(config, offline):
    results = {}
    registry = None
    results["versions_recorded"] = config.get("versions", {})
    if offline:
        results["comfy"] = {"state": "offline check"}
    else:
        try:
            client = Comfy(config.get("comfy_url", ""))
            system_stats = client.request("/system_stats")
            stats = system_stats["system"]
            registry = client.request("/object_info")
            results["comfy"] = {"state": "responding", "versions": {
                key: stats.get(key) for key in ("comfyui_version", "required_frontend_version", "python_version", "pytorch_version")
            }, "relevant_nodes": sorted(key for key in registry if any(s in key.lower() for s in ("flux", "trellis", "geometrypack")))}
            loaders = {"CheckpointLoaderSimple": "ckpt_name", "UNETLoader": "unet_name",
                       "CLIPLoader": "clip_name", "DualCLIPLoader": "clip_name1", "VAELoader": "vae_name",
                       "LoraLoader": "lora_name",
                       "CLIPVisionLoader": "clip_name", "LoadBackgroundRemovalModel": "bg_removal_name"}
            results["comfy"]["model_choices"] = {
                key: options for key, input_name in loaders.items()
                if (options := input_choices(registry.get(key, {}).get("input", {}).get("required", {}).get(input_name)))
                is not None
            }
        except (PipelineError, OSError, KeyError, ValueError) as error:
            results["comfy"] = {"state": "COMFY_UNAVAILABLE", "detail": str(error)}

    def probe(key, action):
        try:
            evidence = action()
            results[key] = {"state": "configured; execution untested"}
            if isinstance(evidence, dict):
                results[key] = {"state": "verified", **evidence}
        except (PipelineError, OSError, KeyError, ValueError, TypeError, subprocess.SubprocessError) as error:
            results[key] = {"state": "blocked", "detail": str(error)}

    for key in ("python", "comfy_python", "node", "blender"):
        probe(key, lambda: setting(config, key, executable=True))
        if results[key]["state"] != "blocked":
            results[key]["path"] = config[key]
    probe("comfy_root", lambda: setting(config, "comfy_root", directory=True))
    probe("game_adapter", lambda: setting(config, "game_adapter", relative=True))
    probe("projection_adapter", lambda: setting(config, "projection_adapter", relative=True))
    probe("game", lambda: game_tools(config))
    probe("projection", lambda: projection_tools(config))
    probe("rig", lambda: (setting(config, "blender", executable=True), required_path(RIG, "RIG_MISSING")))
    probe("compression", lambda: (setting(config, "node", executable=True), setting(config, "gltf_transform")))
    probe("lab", lambda: (setting(config, "node", executable=True), required_path(VITE, "VITE_MISSING")))
    warnings = []
    for key in ("python", "comfy_python", "trellis_worker_python", "node", "blender", "gltf_transform",
                "comfy_launcher"):
        value = config.get(key)
        if not value:
            continue
        parts = [part.casefold() for part in PureWindowsPath(value).parts]
        if "windowsapps" in parts or any(
                part == "codex" and previous == "documents" for previous, part in zip(parts, parts[1:])):
            warnings.append({"setting": key, "path": value, "code": "UNSTABLE_TOOL_PATH",
                             "detail": "Use a stable installation or a portable tool under E:/AI-Native/tools."})
    results["path_warnings"] = warnings
    if not offline and config.get("comfy_root"):
        probe("nvidia_gpu", lambda: (sample := nvidia_sample()) | {"device": sample["name"]})
        probe("comfy_torch", lambda: torch_gpu(setting(config, "comfy_python", executable=True)))
        probe("blender_gpu", lambda: blender_gpu(setting(config, "blender", executable=True)))
        if results["comfy"]["state"] == "responding":
            probe("comfy_gpu", lambda: {"device": comfy_device(system_stats)})
    results["handoff"] = {"state": "available with a verified candidate report"}
    results["runs_root"] = {"path": config.get("runs_root"), "exists": bool(config.get("runs_root") and Path(config["runs_root"]).is_dir())}
    for kind in (*CONCEPT_PRESETS, "3d", "3d-1024", "3d-bf16"):
        model_requirements = []

        def check():
            graph, binding = workflow(config, kind)
            if registry is None:
                raise PipelineError("COMFY_UNVERIFIED: live node and model validation needs a responding server.")
            model_inputs = {
                "UNETLoader": ("unet_name",), "DualCLIPLoader": ("clip_name1", "clip_name2"),
                "VAELoader": ("vae_name",), "CLIPVisionLoader": ("clip_name",),
                "LoraLoader": ("lora_name",),
                "LoadBackgroundRemovalModel": ("bg_removal_name",),
            }
            for node in graph.values():
                node_class = node["class_type"]
                available = registry.get(node_class, {}).get("input", {}).get("required", {})
                for key in model_inputs.get(node_class, ()):
                    name = node["inputs"][key]
                    options = input_choices(available.get(key))
                    model_requirements.append({"model": name, "available": isinstance(options, list) and name in options})
            deferred = [binding["image"]] if not kind.startswith("concept") else []
            device = comfy_device(system_stats)
            validate_graph(graph, registry, deferred)
            if not kind.startswith("concept") and binding.get("requires_worker"):
                worker = setting(config, "trellis_worker_python", "TRELLIS_WORKER_MISSING", executable=True)
                return {"device": device, "worker_device": torch_gpu(worker)["device"]}
            return {"device": device, "graph_validation": "static"}
        probe(kind, check)
        if model_requirements:
            results[kind]["models"] = model_requirements
    return results


def stage_workflows(sources, destination):
    if len({path.name.casefold() for path in sources}) != len(sources):
        raise PipelineError("WORKFLOW_CONFLICT: duplicate destination name.")
    entries = [(source, destination / source.name, sha256(source)) for source in sources]
    for _, target, digest in entries:
        if target.is_symlink() or target.exists() and sha256(target) != digest:
            raise PipelineError(f"WORKFLOW_CONFLICT: {target}")
    destination.mkdir(parents=True, exist_ok=True)
    for source, target, digest in entries:
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix=".blackwood-", dir=destination) as directory:
                staged = Path(directory) / source.name
                shutil.copyfile(source, staged)
                if sha256(staged) != digest:
                    raise PipelineError(f"WORKFLOW_HASH: {source}")
                try:
                    staged.rename(target)
                except FileExistsError:
                    pass
        if sha256(target) != digest:
            raise PipelineError(f"WORKFLOW_CONFLICT: {target}")
    return {target.name: digest for _, target, digest in entries}


def run_folder(config, run, *, create=False):
    identifier(run)
    root = Path(config.get("runs_root") or "")
    if not root.is_absolute():
        raise PipelineError("RUNS_ROOT: set an absolute approved Windows run directory.")
    folder = root / run
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return required_path(folder, "RUN_MISSING", directory=True)


def completed_report(path, data):
    try:
        write_json(path, data, exclusive=True)
    except FileExistsError:
        if read_json(path) != data:
            raise PipelineError(f"REPORT_CONFLICT: {path}")
    return data


def generate(config, args, kind):
    resolution = getattr(args, "resolution", 512)
    preset = "3d-1024" if kind == "3d" and resolution == 1024 else kind
    if kind == "3d" and getattr(args, "bf16", False):
        if resolution != 512:
            raise PipelineError("BF16_PRESET: the comparison graph uses resolution 512.")
        preset = "3d-bf16"
    graph, binding = workflow(config, preset)
    if kind == "3d" and binding.get("requires_worker"):
        worker = setting(config, "trellis_worker_python", "TRELLIS_WORKER_MISSING", executable=True)
        worker_device = torch_gpu(worker)["device"]
    else:
        worker_device = None
    client = Comfy(config["comfy_url"])
    device = comfy_device(client.request("/system_stats"))
    registry = client.request("/object_info")
    if args.timeout < 0:
        raise PipelineError("TIMEOUT: use a non-negative number of seconds.")
    if kind.startswith("concept"):
        if not 0 <= args.seed < 2**64:
            raise PipelineError("SEED: expected an unsigned 64-bit integer.")
        bind(graph, binding, "seed", args.seed)
        identity = {"seed": args.seed}
        if "body" in binding:
            if not getattr(args, "body", None):
                raise PipelineError("BODY_REQUIRED: pass --body for this concept preset.")
            node_id, key = binding["body"]
            prompt = graph[node_id]["inputs"][key]
            body_token = binding["body_token"]
            if not body_token or prompt.count(body_token) != 1:
                raise PipelineError("WORKFLOW_BINDING: expected one reviewed body segment in the concept prompt.")
            bind(graph, binding, "body", prompt.replace(body_token, args.body))
            identity["body"] = args.body
        elif getattr(args, "body", None) is not None:
            raise PipelineError("FIXED_PROMPT: omit --body for this concept preset.")
        validate_graph(graph, registry)
        items = [(0, identity, None)]
        run = run_folder(config, args.run, create=True)
    else:
        run = run_folder(config, args.run)
        report = read_json(run / "concepts/report.json")
        if report["run"] != args.run or len(set(args.select)) != len(args.select) or not 1 <= len(args.select) <= 3:
            raise PipelineError("SELECTION: select 1–3 distinct concept batch indices from this run.")
        images = {entry["batch"]: entry for entry in report["artifacts"]}
        items = []
        for batch in args.select:
            if batch not in images:
                raise PipelineError(f"SELECTION: batch {batch} does not exist in run {args.run}.")
            entry = images[batch]
            if Path(entry["file"]).name != entry["file"]:
                raise PipelineError("SELECTION_FILENAME: expected a filename in the report.")
            path = run / "concepts" / entry["file"]
            check_png(path)
            actual = artifact(path, "concept")
            require_artifact(report, actual)
            items.append((batch, {"seed": report["seed"], "batch": batch, "concept_sha256": actual["sha256"],
                                  "resolution": resolution}, path))
        validate_graph(graph, registry, [binding["image"]])
    results = []
    for batch, identity, source in items:
        job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"blackwood:{args.run}:{kind}:{batch}"))
        folder = run / ("concepts" if kind.startswith("concept") else f"raw/{batch}")
        folder.mkdir(parents=True, exist_ok=True)
        report_path = folder / "report.json"
        if report_path.is_file():
            saved = read_json(report_path)
            expected = {"run": args.run, "workflow_sha256": binding["workflow_sha256"], **identity}
            if any(saved.get(key) != value for key, value in expected.items()):
                raise PipelineError(f"REPORT_CONFLICT: {report_path} was produced from different inputs.")
            roles = ["raw", "cutout"] if source and binding.get("cutout") else ["raw"] if source else ["concept"] * 8
            if sorted(item["role"] for item in saved["artifacts"]) != sorted(roles):
                raise PipelineError(f"REPORT_CONFLICT: unexpected artifacts in {report_path}")
            for item in saved["artifacts"]:
                if Path(item["file"]).name != item["file"]:
                    raise PipelineError(f"ARTIFACT_FILENAME: {item['file']}")
                require_artifact(saved, artifact(folder / item["file"], item["role"]))
            results.append(saved | {"directory": str(folder)})
            continue
        intent = folder / "intent.json"
        if not intent.exists():
            require_idle(config)
        prefix = f"blackwood/{args.run}/{job_id}/{kind.replace('3d', 'raw')}"
        bind(graph, binding, "prefix", prefix)
        cutout = binding.get("cutout")
        cutout_prefix = f"blackwood/{args.run}/{job_id}/cutout"
        if cutout:
            bind(graph, cutout, "prefix", cutout_prefix)
        if source:
            digest = identity["concept_sha256"]
            image_folder = f"blackwood/{args.run}/{job_id}"
            if not intent.exists():
                client.upload(source, image_folder, digest)
            bind(graph, binding, "image", f"{image_folder}/{digest}.png")
        validate_graph(graph, registry, [binding["image"]] if source else [])
        complete_telemetry = not intent.exists()
        with VramMonitor() as telemetry:
            history = client.job(job_id, graph, intent, args.timeout)
        measurements = telemetry.report() | {"vram_complete_observation": complete_telemetry}
        count, ext, role, validate = (1, ".glb", "raw", check_glb) if source else (8, ".png", "concept", check_png)
        refs = collect_outputs(history, *binding["output"], prefix, ext, count)
        entries = []
        for index, ref in enumerate(refs, 1):
            batch_index = batch if source else index
            path = folder / f"seed-{identity['seed']}_batch{batch_index}_{role}{ext}"
            client.download(ref, path, validate)
            entries.append(artifact(path, role) | {"batch": batch_index, "seed": identity["seed"], "output": ref})
        if cutout:
            ref, = collect_outputs(history, *cutout["output"], cutout_prefix, ".png", 1)
            path = folder / f"seed-{identity['seed']}_batch{batch}_cutout.png"
            client.download(ref, path, check_png)
            entries.append(artifact(path, "cutout") | {"batch": batch, "seed": identity["seed"], "output": ref})
        report = completed_report(report_path, {
            "run": args.run, "job": job_id, "workflow_sha256": binding["workflow_sha256"],
            **identity, "device": device, "worker_device": worker_device, **measurements, "artifacts": entries,
        })
        results.append(report | {"directory": str(folder)})
    return results


def one_artifact(folder, role):
    report = read_json(folder / "report.json")
    items = [entry for entry in report["artifacts"] if entry["role"] == role]
    if len(items) != 1 or Path(items[0]["file"]).name != items[0]["file"]:
        raise PipelineError(f"ARTIFACT_ROLE: expected one {role} in {folder}")
    source = folder / items[0]["file"]
    check_glb(source, baked=role == "baked")
    require_artifact(report, artifact(source, role))
    return source, report


def blender_args(script, *args):
    return ["--background", "--factory-startup", "--python-exit-code", "1", "--python", script, "--", *args]


def process_model(config, args, stage):
    if stage == "game":
        exe, adapter = game_tools(config)
        imported, input_role = args.raw, "raw"
    else:
        exe, adapter = projection_tools(config)
        imported, input_role = args.game, "game"
    if imported:
        if args.seed is None or not 0 <= args.seed < 2**64:
            raise PipelineError(f"SEED_REQUIRED: pass the original seed of the imported {input_role.upper()}.")
        source = imported.resolve()
        check_glb(source)
        parent = {"run": args.run, "batch": args.batch, "seed": args.seed}
    run = run_folder(config, args.run, create=bool(imported))
    target = run / stage / str(args.batch)
    if not imported:
        source, parent = one_artifact(run / input_role / str(args.batch), input_role)
        if parent.get("run") != args.run or parent.get("batch") != args.batch:
            raise PipelineError(f"REPORT_IDENTITY: run or batch mismatch for {source}")
    original = sha256(source)
    identity = {"run": args.run, "batch": args.batch, "seed": parent["seed"], "source_sha256": original,
                "concept_sha256": parent.get("concept_sha256")}
    remesh = stage == "game" and getattr(args, "remesh", False)
    bake_mask = getattr(args, "bake_mask", None)
    face_preview = getattr(args, "face_preview", False)
    if remesh:
        identity["game_method"] = "remesh"
    if getattr(args, "save_bake_mask", False):
        identity["save_bake_mask"] = True
    if bake_mask:
        check_png(bake_mask)
        identity["bake_mask_sha256"] = sha256(bake_mask)
    if face_preview:
        identity["face_preview"] = True
    if stage == "baked":
        if args.image:
            image = args.image.resolve()
        elif imported:
            raise PipelineError("PROJECTION_IMAGE: pass --image with an imported GAME.")
        else:
            raw_folder = run / "raw" / str(args.batch)
            cutout_report = raw_folder / "report.json"
            if not cutout_report.is_file():
                raise PipelineError("PROJECTION_IMAGE: this run has no saved cutout. Pass --image.")
            raw_report = read_json(cutout_report)
            cutouts = [entry for entry in raw_report["artifacts"] if entry["role"] == "cutout"]
            if len(cutouts) != 1 or Path(cutouts[0]["file"]).name != cutouts[0]["file"]:
                raise PipelineError("PROJECTION_IMAGE: supply the approved cutout with --image.")
            image = raw_folder / cutouts[0]["file"]
            require_artifact(raw_report, artifact(image, "cutout"))
            if raw_report.get("run") != args.run or raw_report.get("batch") != args.batch or parent.get(
                    "concept_sha256") != raw_report.get("concept_sha256"):
                raise PipelineError("PROJECTION_IMAGE: cutout and GAME have different concept provenance.")
        check_png(image)
        identity["projection_image_sha256"] = sha256(image)
    if target.exists():
        _, report = one_artifact(target, stage)
        if any(report.get(key) != value for key, value in identity.items()):
            raise PipelineError(f"STAGE_CONFLICT: {target} was produced from different inputs.")
        return report
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".blackwood-", dir=target.parent) as directory:
        work = Path(directory)
        out = work / f"seed-{parent['seed']}_batch{args.batch}_{stage}.glb"
        previews = work / "previews"
        previews.mkdir()
        report = work / "adapter-report.json"
        common = ["--output", out, "--previews", previews, "--report", report]
        if stage == "game":
            worker = config.get("trellis_worker_python") or config.get("comfy_python")
            worker_args = []
            if worker and Path(worker).is_file():
                worker_args = ["--trellis-python", required_path(worker, "TRELLIS_WORKER_MISSING", executable=True)]
            if config.get("cumesh_site_packages"):
                if not worker_args:
                    raise PipelineError("TRELLIS_WORKER_MISSING: CuMesh needs a configured Windows Python.")
                packages = setting(config, "cumesh_site_packages", directory=True)
                worker_args.extend(("--cumesh-site-packages", packages))
            argv = blender_args(adapter, "--raw", source, *common, *worker_args)
            if remesh:
                argv.append("--remesh")
            if identity.get("save_bake_mask"):
                argv.extend(("--bake-mask", work / "bake-mask.png"))
        else:
            python = setting(config, "comfy_python", executable=True)
            argv = blender_args(adapter, "--game", source, "--image", image, "--comfy-python", python, *common)
            if bake_mask:
                argv.extend(("--bake-mask", bake_mask.resolve()))
            if face_preview:
                argv.append("--face-preview")
        log = run / f"{stage}-{args.batch}-{uuid.uuid4()}.log"
        with VramMonitor() as telemetry:
            command(exe, argv, adapter.parent, log)
        if sha256(source) != original:
            raise PipelineError(f"SOURCE_CHANGED: {source}")
        if stage == "baked" and sha256(image) != identity["projection_image_sha256"]:
            raise PipelineError(f"SOURCE_CHANGED: {image}")
        if bake_mask and sha256(bake_mask) != identity["bake_mask_sha256"]:
            raise PipelineError(f"SOURCE_CHANGED: {bake_mask}")
        check_glb(out, baked=stage == "baked")
        evidence = read_json(report)
        checks = ("unique_triangles",) if stage == "game" else ("geometry_preserved", "uv_preserved", "transform_preserved")
        if any(evidence.get(key) is not True for key in checks):
            raise PipelineError(f"ADAPTER_REPORT: expected checks {', '.join(checks)}. Log: {log}")
        if stage == "game" and not isinstance(evidence.get("extremities_present"), bool):
            raise PipelineError(f"ADAPTER_REPORT: missing extremity check. Log: {log}")
        images = sorted(previews.glob("*.png"))
        if not images:
            raise PipelineError(f"PREVIEWS_MISSING: {stage}. Log: {log}")
        for image in images:
            check_png(image)
        mask = work / "bake-mask.png"
        if identity.get("save_bake_mask") and mask.is_file():
            check_png(mask)
            evidence["bake_mask"] = artifact(mask, "bake-mask")
        inherited = {}
        if stage == "baked" and not imported:
            inherited = {"raw_sha256": parent.get("raw_sha256") or parent["source_sha256"],
                         "silhouette_iou": model_metrics(parent)["silhouette_iou"]}
        manifest = identity | inherited | {"artifacts": [artifact(out, stage)],
                               "previews": [artifact(path, "preview") for path in images], "diagnostics": evidence,
                               "device": evidence["device"], **telemetry.report()}
        write_json(work / "report.json", manifest)
        work.rename(target)
    return manifest


@contextmanager
def operation_lock(name):
    import msvcrt

    directory = REPO_ROOT / "build/blackwood"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{name}.lock").open("a+b") as handle:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise PipelineError(f"PIPELINE_BUSY: {name}") from error
        yield


def require_idle(config):
    try:
        queue = Comfy(config["comfy_url"]).request("/queue")
    except URLError as error:
        if isinstance(error.reason, ConnectionRefusedError):
            return
        raise
    if queue["queue_running"] or queue["queue_pending"]:
        raise PipelineError("COMFY_BUSY: existing jobs are running or pending.")


def publication_id(run, batch, stage, version=""):
    suffix = f"-b{batch}-{stage}" if batch is not None else f"-{stage}"
    if len(run + suffix + version) > 64:
        suffix += "-" + uuid.uuid5(uuid.NAMESPACE_URL, run).hex[:12]
    return identifier(run[:64 - len(suffix) - len(version)] + suffix + version)


def managed_candidate(config, run, batch, stage):
    role = "baked" if stage == "projected" else stage
    folder = run_folder(config, run) / role / str(batch)
    source, data = one_artifact(folder, role)
    previews = []
    for entry in data["previews"]:
        if Path(entry["file"]).name != entry["file"]:
            raise PipelineError("PREVIEW_FILENAME: expected a filename in the report.")
        previews.append(folder / "previews" / entry["file"])
    return source, folder / "report.json", previews


def lab_link(config, result):
    path = result["lab_path"].removeprefix("3d/")
    return lab_origin(config) + "/model-lab.html?model=" + quote(path, safe="/")


def handoff(config, args):
    manual = [args.candidate, args.report]
    publication = None
    if any(manual):
        if not all(manual) or args.batch is not None:
            raise PipelineError("HANDOFF_INPUTS: use --candidate and --report together, or --batch for a managed run.")
        source, report, previews = args.candidate, args.report, args.preview or []
    else:
        if args.batch is None or args.preview:
            raise PipelineError("HANDOFF_INPUTS: specify --batch for a managed run.")
        source, report, previews = managed_candidate(config, args.run, args.batch, args.stage)
        if args.stage != "baked":
            publication = publication_id(args.run, args.batch, args.stage)
    result = publish(REPO_ROOT, args.name, args.stage, report, source, previews, args.run, args.note, args.dry_run,
                     publication=publication)
    return result | {"lab_url": lab_link(config, result)}


def rig_provenance(source, digest):
    for filename in ("report.json", "manifest.json"):
        path = source.with_name(filename)
        if not path.is_file():
            continue
        data = read_json(path)
        entries = data.get("artifacts", data.get("files", []))
        if any(entry["file"] == source.name and entry["sha256"] == digest for entry in entries):
            return data
    return {}


def rig(config, args):
    if args.seed is not None and not 0 <= args.seed < 2**64:
        raise PipelineError("SEED_INVALID: rig seed must be an unsigned 64-bit integer.")
    exe = setting(config, "blender", executable=True)
    source = args.source.resolve()
    check_glb(source)
    digest = sha256(source)
    parent = rig_provenance(source, digest)
    dest = args.output.resolve()
    diagnostics = dest.with_name(dest.stem + "-diagnostics")
    if dest.suffix.lower() != ".glb" or dest.exists() or diagnostics.exists():
        raise PipelineError(f"RIG_OUTPUT: choose a new .glb destination: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    log = dest.with_name(f"{dest.stem}-{uuid.uuid4()}.log")
    with tempfile.TemporaryDirectory(prefix=".blackwood-", dir=dest.parent) as directory:
        staged = Path(directory) / dest.name
        staged_diagnostics = staged.with_name(diagnostics.name)
        argv = blender_args(RIG, source, staged)
        if args.fit_puppet:
            argv.append("--fit-puppet")
        with VramMonitor() as telemetry:
            command(exe, argv, REPO_ROOT, log)
        rigged = check_glb(staged)
        skins = rigged.get("skins", [])
        if len(skins) != 1 or len(skins[0].get("joints", [])) != 19:
            raise PipelineError(f"RIG_CONTRACT: expected a 19-bone skin. Log: {log}")
        required_path(staged_diagnostics / "report.txt", "RIG_DIAGNOSTICS_MISSING")
        if sha256(source) != digest:
            raise PipelineError(f"SOURCE_CHANGED: {source}")
        previews = sorted(staged_diagnostics.glob("*.png"))
        if not previews:
            raise PipelineError(f"PREVIEWS_MISSING: rigged. Log: {log}")
        for preview in previews:
            check_png(preview)
        provenance = parent.get("source", {})
        raw_digest = parent.get("raw_sha256") or provenance.get("raw_sha256")
        if not raw_digest and any(entry["role"] == "game" for entry in parent.get("artifacts", [])):
            raw_digest = parent.get("source_sha256")
        report = read_json(staged_diagnostics / "report.json") | telemetry.report()
        report |= {
            "run": args.run or parent.get("run") or f"rig-{digest[:16]}",
            "batch": args.batch if args.batch is not None else parent.get("batch"),
            "seed": args.seed if args.seed is not None else parent.get("seed"),
            "source_sha256": digest,
            "concept_sha256": parent.get("concept_sha256", provenance.get("concept_sha256")),
            "raw_sha256": raw_digest,
            "silhouette_iou": model_metrics(parent)["silhouette_iou"],
            "projection_iou": model_metrics(parent)["projection_iou"],
            "artifacts": [artifact(staged, "rigged")],
            "previews": [artifact(path, "preview") for path in previews],
        }
        write_json(staged_diagnostics / "report.json", report)
        staged_diagnostics.rename(diagnostics)
        try:
            staged.rename(dest)
        except OSError:
            diagnostics.rename(staged_diagnostics)
            raise
    return {"rigged": str(dest), "diagnostics": str(diagnostics), "log": str(log), **report}


def playable_model(config, args, stage):
    phase = "model"
    try:
        require_idle(config)
        result = rig(config, args) if stage == "rigged" else process_model(
            config, args, "baked" if stage == "projected" else stage)
        if args.no_lab:
            return result
        phase = "handoff"
        version = ""
        if stage == "rigged":
            source, folder = Path(result["rigged"]), Path(result["diagnostics"])
            candidate = source, folder / "report.json", [folder / entry["file"] for entry in result["previews"]]
            version = "-" + result["artifacts"][0]["sha256"][:12]
        else:
            candidate = managed_candidate(config, args.run, args.batch, stage)
        run, batch = result["run"], result["batch"]
        published = publish(REPO_ROOT, args.lab_name, stage, candidate[1], candidate[0], candidate[2], run,
                            publication=publication_id(run, batch, stage, version))
    except (PipelineError, OSError, KeyError, ValueError, TypeError) as error:
        failures = REPO_ROOT / "build/blackwood"
        failures.mkdir(parents=True, exist_ok=True)
        report = failures / f"{stage}-failed-{uuid.uuid4()}.json"
        write_json(report, {"status": "failed", "stage": stage, "phase": phase,
                            "run": args.run, "batch": args.batch, "error": str(error)}, exclusive=True)
        raise PipelineError(f"{error} Failure report: {report}") from error
    url = lab_link(config, published)
    result |= {"handoff": published, "lab_url": url}
    if getattr(args, "action", None) == "3d":
        print(url, file=sys.stderr, flush=True)
    if args.open:
        try:
            model_lab(config, url)
        except (PipelineError, OSError) as error:
            result["lab_open_error"] = str(error)
    return result


def compress(config, args):
    node = setting(config, "node", executable=True)
    cli = setting(config, "gltf_transform")
    source = args.source.resolve()
    doc = check_glb(source)
    if not doc.get("skins"):
        raise PipelineError("RIG_REQUIRED: compression for the game expects a skinned GLB.")
    dest = WEB / "src/assets/werewolf" / f"ledge-wolf-v{args.version}.glb"
    if args.version < 4 or dest.exists():
        raise PipelineError(f"VERSION_CONFLICT: choose a new game model version: {dest}")
    with tempfile.TemporaryDirectory(prefix=".blackwood-", dir=dest.parent) as directory:
        work = Path(directory)
        color, webp, final = (work / name for name in ("color.glb", "webp.glb", "final.glb"))
        logs = REPO_ROOT / "build/blackwood"
        logs.mkdir(parents=True, exist_ok=True)
        steps = [
            ["webp", source, color, "--slots", "baseColorTexture", "--quality", "93"],
            ["webp", color, webp, "--slots", "metallicRoughnessTexture", "--lossless", "true"],
            ["draco", webp, final, "--quantize-position", "15", "--quantize-normal", "12", "--quantize-texcoord", "14"],
        ]
        for step, arguments in enumerate(steps, 1):
            command(node, [cli, *arguments], REPO_ROOT, logs / f"compress-{step}-{uuid.uuid4()}.log")
        check_glb(final)
        final.rename(dest)
    report = artifact(dest, "rigged") | {"path": str(dest), "device": CPU_ONLY}
    write_json(logs / f"compress-v{args.version}-{uuid.uuid4()}.json", report, exclusive=True)
    return report


def build(config):
    node = setting(config, "node", executable=True)
    tsc = required_path(WEB / "node_modules/typescript/bin/tsc", "TSC_MISSING")
    vite = required_path(VITE, "VITE_MISSING")
    logs = REPO_ROOT / "build/blackwood"
    logs.mkdir(parents=True, exist_ok=True)
    run = str(uuid.uuid4())
    command(node, [tsc, "--noEmit"], WEB, logs / f"tsc-{run}.log")
    command(node, [vite, "build"], WEB, logs / f"vite-{run}.log")
    return {"built": str(WEB / "dist"), "device": CPU_ONLY}


def lab_health(url):
    client = Comfy(url)
    try:
        marker = client.request("/__blackwood_model_lab")
        if Path(marker.get("root", "")).resolve() != WEB:
            return False
        with client.opener.open(url + "/model-lab.html", timeout=3) as response:
            return b"@vite/client" in response.read()
    except (OSError, ValueError):
        return False


def port_free(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return False
    except ConnectionRefusedError:
        return True


def lab_origin(config):
    port = int(config.get("lab_port", 5173))
    return f"http://localhost:{port}"


def start_model_lab(config):
    for file in ("model-lab.html", "src/model-lab.ts", "vite.config.ts"):
        required_path(WEB / file, "LOCAL_LAB_MISSING: Model Lab is installed separately from the pipeline")
    port = int(config.get("lab_port", 5173))
    url = f"http://127.0.0.1:{port}"
    page = lab_origin(config) + "/model-lab.html"
    if lab_health(url):
        return {"lab": page, "state": "reused"}
    node = setting(config, "node", executable=True)
    npm = node.parent / "node_modules/npm/bin/npm-cli.js"
    if not npm.is_file() and (launcher := shutil.which("npm.cmd")):
        npm = Path(launcher).parent / "node_modules/npm/bin/npm-cli.js"
    # A portable Node installation can ship without npm. Run the same dev script with Vite directly.
    dev = [str(npm), "run", "dev", "--"] if npm.is_file() else [str(required_path(VITE, "VITE_MISSING"))]
    env = os.environ | {"PATH": str(node.parent) + os.pathsep + os.environ.get("PATH", "")}
    with operation_lock("lab"):
        if lab_health(url):
            return {"lab": page, "state": "reused"}
        try:
            free = port_free(port)
        except TimeoutError:
            free = True  # Vite's strict-port bind still rejects an occupied port.
        if not free:
            raise PipelineError(f"LAB_PORT_BUSY: {url}")
        logs = REPO_ROOT / "build/blackwood"
        run = str(uuid.uuid4())
        receipt, log = logs / f"lab-{run}.json", logs / f"lab-{run}.log"
        with log.open("xb") as output:
            child = subprocess.Popen([str(node), *dev, "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
                                     cwd=WEB, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW, env=env)
            write_json(receipt, {"pid": child.pid, "exe": str(node), "url": page, "cwd": str(WEB),
                                 "started_unix": time.time(), "log": str(log)}, exclusive=True)
            for _ in range(30):
                if child.poll() is not None:
                    raise PipelineError(f"LAB_EXIT: {child.returncode}. Log: {log}")
                if lab_health(url):
                    return {"lab": page, "state": "started", "receipt": str(receipt)}
                time.sleep(0.5)
    raise PipelineError(f"LAB_START_UNVERIFIED: {receipt}")


def model_lab(config, target=None):
    result = start_model_lab(config)
    os.startfile(target or result["lab"])
    return result | {"opened": target or result["lab"]}


def lab_options(parser):
    switches = parser.add_mutually_exclusive_group()
    switches.add_argument("--no-lab", action="store_true", help="Skip automatic Model Lab publication.")
    switches.add_argument("--open", action="store_true", help="Open the published candidate in Model Lab.")
    parser.add_argument("--lab-name", type=identifier, default="werewolf", help="Model group in the lab.")


def comfy_start(config):
    client = Comfy(config["comfy_url"])
    try:
        client.request("/system_stats")["system"]
        return {"comfy": client.url, "state": "reused"}
    except URLError as error:
        if not isinstance(error.reason, ConnectionRefusedError):
            raise
    launcher = setting(config, "comfy_launcher")
    if launcher.suffix.lower() != ".ps1":
        raise PipelineError("COMFY_LAUNCHER: expected the reviewed native PowerShell launcher.")
    port = urlsplit(client.url).port
    pwsh = required_path(shutil.which("pwsh.exe"), "PWSH_MISSING", executable=True)
    with operation_lock("comfy-start"):
        if not port_free(port):
            raise PipelineError(f"COMFY_PORT_BUSY: {client.url}")
        receipt = REPO_ROOT / "build/blackwood" / f"comfy-launcher-{uuid.uuid4()}.json"
        with subprocess.Popen([str(pwsh), "-NoProfile", "-File", str(launcher)], cwd=launcher.parent) as process:
            write_json(receipt, {"pid": process.pid, "exe": str(pwsh), "launcher": str(launcher),
                                 "url": client.url, "started_unix": time.time()}, exclusive=True)
            print(json.dumps({"state": "foreground launcher started", "receipt": str(receipt)}), flush=True)
            exit_code = process.wait()
        if exit_code:
            raise PipelineError(f"COMFY_LAUNCHER_EXIT: {exit_code}. Receipt: {receipt}")
    return {"state": "foreground launcher exited", "receipt": str(receipt)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXAMPLE)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init", help="Create the repo-local configuration if absent.")
    sub.add_parser("test", help="Run isolated standard-library fixtures.")
    sub.add_parser("build", help="Run the existing web type-check and Vite build using configured Node.")
    status = sub.add_parser("doctor", aliases=["status"], help="Read-only native inventory and optional live validation.")
    status.add_argument("--offline", action="store_true")
    sync = sub.add_parser("stage-workflows", help="Copy exact workflow sources to an explicitly approved destination.")
    sync.add_argument("--destination", type=Path, required=True)
    sync.add_argument("--approved", action="store_true", required=True)
    for kind in (*CONCEPT_PRESETS, "3d"):
        action = sub.add_parser(kind, help="Submit or recover one job per concept batch or selected image.")
        action.add_argument("--run", type=identifier, required=True)
        action.add_argument("--timeout", type=int, default=1800)
        action.add_argument("--approved", action="store_true", required=True)
        if kind.startswith("concept"):
            action.add_argument("--seed", type=int, required=True)
            if kind == "concept":
                action.add_argument("--preset", choices=CONCEPT_PRESETS, default="concept")
            if kind != "concept-photo":
                action.add_argument("--body", required=kind != "concept")
        else:
            action.add_argument("--select", nargs="+", type=int, required=True)
            action.add_argument("--resolution", type=int, choices=(512, 1024), default=512,
                                help="512 is standard. 1024 requires its own approved test.")
            action.add_argument("--raw-only", action="store_true")
            action.add_argument("--bf16", action="store_true", help="Use the unquantized BF16 TRELLIS.2 weights at 512.")
            lab_options(action)
    for kind in ("game", "project", "handoff"):
        action = sub.add_parser(kind)
        action.add_argument("--run", type=identifier, required=True)
        action.add_argument("--batch", type=int, choices=range(1, 9), required=kind != "handoff")
        if kind == "game":
            action.add_argument("--raw", type=Path, help="Use an existing RAW without ComfyUI generation.")
            action.add_argument("--remesh", action="store_true", help="Build a closed outer shell before simplification.")
            action.add_argument("--save-bake-mask", action="store_true", help="Save the actual bake hits for hole filling.")
            action.add_argument("--seed", type=int, help="Original seed when importing existing RAW.")
        if kind == "project":
            action.add_argument("--bake-mask", type=Path, help="Fill texture holes using the matching GAME bake hit mask.")
            action.add_argument("--face-preview", action="store_true")
            action.add_argument("--image", type=Path, help="Approved cutout PNG. Defaults to the managed 3D job's cutout.")
            action.add_argument("--game", type=Path, help="Use an existing GAME GLB as the projection source.")
            action.add_argument("--seed", type=int, help="Original seed when importing an existing GAME.")
        if kind != "handoff":
            action.add_argument("--approved", action="store_true", required=True)
            lab_options(action)
        else:
            action.add_argument("--name", type=identifier, required=True)
            action.add_argument("--stage", choices=("game", "projected", "rigged", "baked"), default="baked")
            action.add_argument("--candidate", type=Path)
            action.add_argument("--report", type=Path)
            action.add_argument("--preview", type=Path, action="append")
            action.add_argument("--note", default="")
            action.add_argument("--dry-run", action="store_true")
    lab = sub.add_parser("lab", help="Start or reuse the development server and open Model Lab.")
    lab.add_argument("--start", action="store_true", help=argparse.SUPPRESS)
    comfy = sub.add_parser("comfy-start", help="Reuse healthy ComfyUI or run the configured manual launcher in the foreground.")
    comfy.add_argument("--approved", action="store_true", required=True)
    for kind in ("rig", "compress"):
        action = sub.add_parser(kind)
        action.add_argument("--source", required=True, type=Path)
        action.add_argument("--approved", action="store_true", required=True)
        if kind == "rig":
            action.add_argument("--output", required=True, type=Path)
            action.add_argument("--fit-puppet", action="store_true")
            action.add_argument("--run", type=identifier)
            action.add_argument("--batch", type=int, choices=range(1, 9))
            action.add_argument("--seed", type=int)
            lab_options(action)
        else:
            action.add_argument("--version", required=True, type=int)
    args = parser.parse_args()
    if args.action == "concept":
        args.action = args.preset
    return execute(args)


def execute(args):
    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    outcome = {"status": "completed"}
    exit_code = 0
    try:
        outcome["result"] = dispatch(read_json(args.config), args)
    except (PipelineError, OSError, KeyError, ValueError, TypeError) as error:
        outcome = {"status": "failed", "error": str(error)}
        exit_code = 1
    except KeyboardInterrupt:
        outcome = {"status": "interrupted", "error": "Interrupted by user."}
        exit_code = 130
    receipt = {}
    if args.action in REPORTED_ACTIONS:
        directory = REPO_ROOT / "build/blackwood/run-reports"
        path = directory / f"{started:%Y%m%dT%H%M%SZ}-{args.action}-{uuid.uuid4().hex}.json"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            write_json(path, {
                "command": args.action,
                **{key: getattr(args, key) for key in ("run", "batch", "seed", "select", "no_lab", "dry_run")
                   if getattr(args, key, None) is not None},
                "started_utc": started.isoformat(),
                "finished_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(time.monotonic() - clock, 3),
                **outcome,
            }, exclusive=True)
            receipt = {"run_report": str(path)}
        except (OSError, TypeError, ValueError) as error:
            receipt = {"run_report_error": f"{path}: {error}"}
            if not exit_code:
                exit_code = 1
    if receipt:
        print(json.dumps(receipt, ensure_ascii=False), file=sys.stderr)
    if "result" in outcome:
        print(json.dumps(outcome["result"], indent=2))
    else:
        print(json.dumps({"error": outcome["error"]}), file=sys.stderr)
    return exit_code


def dispatch(config, args):
    action = args.action
    if action in ("status", "doctor"):
        return doctor(config, args.offline)
    if action == "init":
        try:
            write_json(LOCAL, config, exclusive=True)
        except FileExistsError:
            pass
        return {"config": str(LOCAL)}
    if action == "test":
        import unittest

        suite = unittest.defaultTestLoader.discover(str(TOOLS), pattern="test_blackwood.py")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful():
            raise PipelineError("TEST_FAILED")
        return {"tests": result.testsRun}
    if action == "build":
        return build(config)
    if action == "stage-workflows":
        return stage_workflows([required_path(path, "WORKFLOW_MISSING", relative=True)
                                for path in [*config["workflows"].values(), *config.get("workflow_gui", [])]],
                               args.destination.resolve())
    if action == "lab":
        return model_lab(config)
    if action == "comfy-start":
        return comfy_start(config)
    if action == "handoff":
        return handoff(config, args)
    if action == "compress":
        with operation_lock("compression"):
            return compress(config, args)
    with operation_lock("gpu"):
        if action in (*CONCEPT_PRESETS, "3d"):
            if action == "3d" and not args.raw_only:
                game_tools(config)
            reports = generate(config, args, action)
            if action == "3d" and not args.raw_only:
                return {"raw": reports, "game": [
                    playable_model(config, argparse.Namespace(**(vars(args) | {"batch": batch, "raw": None})), "game")
                    for batch in args.select
                ]}
            return reports
        return playable_model(config, args, {"game": "game", "project": "projected", "rig": "rigged"}[action])


if __name__ == "__main__":
    sys.exit(main())
