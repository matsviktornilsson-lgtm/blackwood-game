import argparse
import io
import json
import struct
import sys
import tempfile
import unittest
import uuid
import zlib
from pathlib import Path
from unittest.mock import patch

from blackwood import command, doctor, execute, generate, playable_model, process_model, stage_workflows
from comfy import Comfy, validate_graph, collect_outputs
from gpu_runtime import GPU_NAME, VramMonitor, comfy_device
from send_to_game import PipelineError, publish, sha256


def glb(path, material=None):
    doc = {"asset": {"version": "2.0"}, "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
           "buffers": [{"byteLength": 36}], "bufferViews": [{"buffer": 0, "byteLength": 36}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
           "materials": [material or {}]}
    data = json.dumps(doc).encode()
    data += b" " * (-len(data) % 4)
    binary = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    path.write_bytes(struct.pack("<4sIIII", b"glTF", 2, 28 + len(data) + len(binary), len(data), 0x4E4F534A)
                     + data + struct.pack("<II", len(binary), 0x004E4942) + binary)


def png(pixel=128):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes([0, pixel]))) + chunk(b"IEND", b""))


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Blackwood övning ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "web").mkdir()
        (self.root / "web/package.json").touch()
        self.model = self.root / "modell ö.glb"
        glb(self.model)
        self.preview = self.root / "framifrån.png"
        self.preview.write_bytes(png())
        self.report = self.root / "report.json"
        self.run = str(uuid.uuid4())

    def record(self, role="baked"):
        self.report.write_text(json.dumps({"run": self.run, "artifacts": [
            {"file": self.model.name, "role": role, "sha256": sha256(self.model)},
        ]}), encoding="utf-8")

    def publish(self):
        return publish(self.root, "stalker", "baked", self.report, self.model, [self.preview], self.run)

    def test_idempotent_conflict_and_latest(self):
        self.record()
        result = self.publish()
        self.assertEqual(result, self.publish())
        model_dir = self.root / "3d/incoming/stalker"
        self.assertEqual(json.loads((model_dir / "latest.json").read_text())["run"], self.run)
        self.assertEqual(result["lab_path"], f"3d/incoming/stalker/{self.run}/{self.model.name}")
        self.preview.write_bytes(png(254))
        with self.assertRaisesRegex(PipelineError, "HANDOFF_CONFLICT"):
            self.publish()

    def test_raw_role_refused_even_when_small(self):
        self.record("raw")
        with self.assertRaisesRegex(PipelineError, "ARTIFACT_ROLE"):
            self.publish()
        self.assertFalse((self.root / "3d").exists())

    def test_failed_copy_does_not_advance_latest(self):
        self.record()
        self.publish()
        latest = self.root / "3d/incoming/stalker/latest.json"
        saved = latest.read_bytes()
        self.run = str(uuid.uuid4())
        self.record()
        with patch("send_to_game.shutil.copy2", side_effect=OSError("fixture copy error")):
            with self.assertRaises(OSError):
                self.publish()
        self.assertEqual(latest.read_bytes(), saved)
        self.assertFalse((latest.parent / self.run).exists())

    def test_baked_rejects_normal_map(self):
        glb(self.model, {"normalTexture": {"index": 0}})
        self.record()
        with self.assertRaisesRegex(PipelineError, "BAKED_MATERIAL"):
            self.publish()

    def test_old_retry_keeps_new_latest_and_hash_tampering_fails(self):
        self.record()
        old = self.run
        self.publish()
        self.run = new = str(uuid.uuid4())
        self.record()
        self.publish()
        self.run = old
        self.record()
        prior = Path(self.publish()["candidate"])
        latest = self.root / "3d/incoming/stalker/latest.json"
        self.assertEqual(json.loads(latest.read_text())["run"], new)
        prior.write_bytes(b"changed")
        with self.assertRaisesRegex(PipelineError, "HANDOFF_HASH"):
            self.publish()
        self.assertEqual(json.loads(latest.read_text())["run"], new)


class ComfyTests(unittest.TestCase):
    def test_upload_boundary_fits_comfy_parser_and_keeps_full_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selected.png"
            path.write_bytes(png())
            digest = sha256(path)
            client = Comfy("http://127.0.0.1:8188")
            reply = {"name": f"{digest}.png", "subfolder": "blackwood/run", "type": "input"}
            with patch.object(client.opener, "open", return_value=io.BytesIO(json.dumps(reply).encode())) as opener:
                self.assertEqual(client.upload(path, "blackwood/run", digest), f"blackwood/run/{digest}.png")
            request = opener.call_args.args[0]
            boundary = request.get_header("Content-type").split("boundary=", 1)[1]
            self.assertLessEqual(len(boundary), 70)
            self.assertIn(f'filename="{digest}.png"'.encode(), request.data)
    def test_lost_response_recovers_exact_history_without_resubmission(self):
        with tempfile.TemporaryDirectory() as directory:
            intent = Path(directory) / "intent.json"
            job = str(uuid.uuid4())
            result = {"status": {"completed": True, "status_str": "success"}, "outputs": {}}
            client = Comfy("http://127.0.0.1:8188")
            with patch.object(client, "request", side_effect=[TimeoutError(), {job: result}, {job: result}]) as request:
                self.assertEqual(client.job(job, {}, intent, 1), result)
                self.assertEqual(client.job(job, {}, intent, 1), result)
            self.assertEqual([call.args[0] for call in request.call_args_list], ["/prompt", f"/history/{job}", f"/history/{job}"])

    def test_unknown_submission_and_error_history(self):
        with tempfile.TemporaryDirectory() as directory:
            intent = Path(directory) / "intent.json"
            job = str(uuid.uuid4())
            client = Comfy("http://127.0.0.1:8188")
            with patch.object(client, "request", side_effect=[TimeoutError(), {}, {"queue_running": [], "queue_pending": []}]) as request:
                with self.assertRaisesRegex(PipelineError, "SUBMISSION_UNKNOWN"):
                    client.job(job, {}, intent, 1)
            self.assertEqual(request.call_count, 3)
            failed = {"status": {"completed": False, "status_str": "error",
                                 "messages": [["execution_error", {"node_id": "4", "exception_type": "RuntimeError"}]]}}
            with patch.object(client, "request", return_value={job: failed}):
                with self.assertRaisesRegex(PipelineError, "EXECUTION_ERROR.*RuntimeError"):
                    client.job(job, {}, intent, 1)

    def test_graph_validation_and_exact_output_count(self):
        graph = {"4": {"class_type": "Loader", "inputs": {"weights": "flux.safetensors"}}}
        with self.assertRaisesRegex(PipelineError, "NODE_MISSING"):
            validate_graph(graph, {})
        with self.assertRaisesRegex(PipelineError, "MODEL_MISSING"):
            validate_graph(graph, {"Loader": {"input": {"required": {"weights": [["sdxl.safetensors"]]}}}})
        validate_graph(graph, {"Loader": {"input": {
            "required": {"weights": ["COMBO", {"options": ["flux.safetensors"]}]}
        }}})
        ref = {"filename": "concept_00001.png", "type": "output", "subfolder": "blackwood/run"}
        history = {"outputs": {"7": {"images": [ref]}}}
        self.assertEqual(collect_outputs(history, "7", "images", "blackwood/run/concept", ".png", 1), [ref])
        with self.assertRaisesRegex(PipelineError, "OUTPUT_COUNT"):
            collect_outputs(history, "7", "images", "blackwood/run/concept", ".png", 8)


class NativeTests(unittest.TestCase):
    def test_gpu_guard_rejects_cpu_mode_and_other_devices(self):
        gpu = {"type": "cuda", "name": f"cuda:0 {GPU_NAME} : cudaMallocAsync"}
        self.assertEqual(comfy_device({"devices": [gpu]}), f"CUDA: {GPU_NAME}")
        with self.assertRaisesRegex(PipelineError, "COMFY_CPU_MODE"):
            comfy_device({"system": {"argv": ["--cpu"]}, "devices": [gpu]})
        with self.assertRaisesRegex(PipelineError, "COMFY_GPU_REQUIRED"):
            comfy_device({"devices": [{"type": "cpu", "name": "CPU"}]})

    def test_process_uses_exact_executable_arguments_and_cwd(self):
        with tempfile.TemporaryDirectory(prefix="Blackwood svensk ä ") as directory:
            cwd = Path(directory)
            exe = cwd / "node.exe"
            exe.touch()
            with patch("blackwood.subprocess.run") as run:
                run.return_value.returncode = 0
                command(exe, [cwd / "Räv med mellanrum.mjs", "--mode", "ö"], cwd, cwd / "tool.log")
            self.assertEqual(run.call_args.args[0], [str(exe), str(cwd / "Räv med mellanrum.mjs"), "--mode", "ö"])
            self.assertEqual(run.call_args.kwargs["cwd"], cwd)
            self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_native_child_preserves_non_ascii_argv_and_cwd(self):
        with tempfile.TemporaryDirectory(prefix="Blackwood svensk ä ") as directory:
            cwd = Path(directory)
            fixture = cwd / "prov ö.py"
            fixture.write_text("import os, sys, json\nprint(json.dumps([os.getcwd(), sys.argv[1]], ensure_ascii=False))\n",
                               encoding="utf-8")
            log = cwd / "tool.log"
            command(Path(sys.executable), [fixture, "Blå räv"], cwd, log)
            self.assertEqual(json.loads(log.read_text(encoding="utf-8")), [str(cwd), "Blå räv"])

    def test_doctor_read_only(self):
        with patch("blackwood.subprocess.run") as run, patch("blackwood.Comfy.request") as request:
            request.return_value = {}
            result = doctor({}, offline=False)
        run.assert_not_called()
        self.assertTrue(all(len(call.args) == 1 for call in request.call_args_list))
        self.assertIn("WORKFLOW_MISSING", json.dumps(result))
        self.assertIn("GAME_ADAPTER_MISSING", json.dumps(result))

    def test_doctor_warns_about_unstable_windows_tool_paths(self):
        result = doctor({
            "node": r"C:\Program Files\WindowsApps\CodexRuntime\node.exe",
            "blender": r"C:\Users\Mats\Documents\Codex\work\blender.exe",
            "gltf_transform": r"E:\AI-Native\tools\gltf-transform\cli.js",
        }, offline=True)
        self.assertEqual([warning["setting"] for warning in result["path_warnings"]], ["node", "blender"])
        self.assertTrue(all(warning["code"] == "UNSTABLE_TOOL_PATH" for warning in result["path_warnings"]))

    def test_execution_reports_completion_failure_and_interrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_text("{}", encoding="utf-8")
            args = argparse.Namespace(action="game", config=config, run="fixture", batch=2)
            for expected, status, result, error in [
                (0, "completed", {"device": "CUDA"}, None),
                (1, "failed", None, PipelineError("FIXTURE_FAILURE")),
                (130, "interrupted", None, KeyboardInterrupt()),
            ]:
                with patch("blackwood.REPO_ROOT", root), patch("blackwood.dispatch", return_value=result,
                           side_effect=error), patch("sys.stdout", new_callable=io.StringIO) as out, \
                        patch("sys.stderr", new_callable=io.StringIO) as err:
                    self.assertEqual(execute(args), expected)
                receipt = json.loads(err.getvalue().splitlines()[0])
                report = json.loads(Path(receipt["run_report"]).read_text(encoding="utf-8"))
                self.assertEqual((report["status"], report["run"], report["batch"]), (status, "fixture", 2))
                if result:
                    self.assertEqual(report["result"], json.loads(out.getvalue()))
                else:
                    self.assertIn("error", report)
            self.assertEqual(len(list((root / "build/blackwood/run-reports").glob("*.json"))), 3)

    def test_workflow_staging_refuses_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "workflow.json"
            source.write_bytes(b"{}")
            dest = root / "isolated"
            stage_workflows([source], dest)
            stage_workflows([source], dest)
            (dest / source.name).write_bytes(b"[]")
            with self.assertRaisesRegex(PipelineError, "WORKFLOW_CONFLICT"):
                stage_workflows([source], dest)
            self.assertEqual((dest / source.name).read_bytes(), b"[]")


class RunTests(unittest.TestCase):
    @staticmethod
    def telemetry():
        return VramMonitor(sample=lambda: {"name": GPU_NAME, "used_mib": 123, "utilization_pct": 42})

    def test_rebuilt_workflows_are_pinned_and_gui_links_match_api(self):
        from blackwood import EXAMPLE, REPO_ROOT, workflow
        from send_to_game import read_json

        config = read_json(EXAMPLE)
        for kind in ("concept", "concept-schnell", "concept-photo", "3d", "3d-1024"):
            with self.subTest(kind=kind):
                api, bindings = workflow(config, kind)
                gui = read_json(REPO_ROOT / config["workflows"][kind].replace(".api.json", ".json"))
                nodes = {str(node["id"]): node for node in gui["nodes"]}
                self.assertEqual(set(api), set(nodes))
                for node_id, data in api.items():
                    self.assertEqual(data["class_type"], nodes[node_id]["type"])
                for _, origin, slot, target, input_index, _ in gui["links"]:
                    key = nodes[str(target)]["inputs"][input_index]["name"]
                    self.assertEqual(api[str(target)]["inputs"][key], [str(origin), slot])
                self.assertTrue(bindings["preset"])
        concept, _ = workflow(config, "concept")
        photo, photo_binding = workflow(config, "concept-photo")
        self.assertNotIn("body", photo_binding)
        self.assertNotIn("[BODY]", photo["4"]["inputs"]["t5xxl"])
        for key in ("clip_l", "t5xxl"):
            self.assertNotEqual(photo["4"]["inputs"][key], concept["4"]["inputs"][key])
            photo["4"]["inputs"][key] = concept["4"]["inputs"][key]
        self.assertEqual(photo, concept)
        schnell, _ = workflow(config, "concept-schnell")
        self.assertEqual(concept["1"]["inputs"], {"unet_name": "flux1-dev.safetensors", "weight_dtype": "fp8_e4m3fn"})
        self.assertEqual(concept["7"]["inputs"]["steps"], 28)
        self.assertEqual(concept["7"]["inputs"]["positive"], ["11", 0])
        self.assertEqual(concept["11"]["inputs"]["guidance"], 3.5)
        self.assertEqual(schnell["1"]["inputs"]["unet_name"], "flux1-schnell.safetensors")
        self.assertEqual(schnell["6"]["inputs"], {"width": 1024, "height": 1536, "batch_size": 8})
        for kind in ("3d", "3d-1024"):
            graph, _ = workflow(config, kind)
            unwrap = next(node for node in graph.values() if node["class_type"] == "UnwrapMesh")
            self.assertEqual(unwrap["inputs"]["segmenter"], "pec")
        self.assertNotIn("Trellis2UpsampleStage", {node["class_type"] for node in workflow(config, "3d")[0].values()})
        self.assertIn("Trellis2UpsampleStage", {node["class_type"] for node in workflow(config, "3d-1024")[0].values()})

    def test_game_and_projection_adapter_contracts_without_gpu(self):
        with tempfile.TemporaryDirectory(prefix="Blackwood svensk ä ") as directory:
            root = Path(directory)
            run = root / "körningar/stalker-01"
            raw, image = root / "RAW källa.glb", root / "Bild ö.png"
            glb(raw)
            image.write_bytes(png())
            config = {"runs_root": str(run.parent)}
            (root / "web").mkdir()
            (root / "web/package.json").touch()
            for key, name in {"game_adapter": "make.py", "blender": "blender.exe",
                              "projection_adapter": "bake.py", "comfy_python": "comfy-python.exe"}.items():
                config[key] = str(root / name)
                Path(config[key]).touch()

            def fake_process(exe, argv, cwd, log):
                self.assertEqual(cwd, root)
                glb(argv[argv.index("--output") + 1])
                (argv[argv.index("--previews") + 1] / "framifrån.png").write_bytes(png())
                evidence = dict.fromkeys(("unique_triangles", "extremities_present", "geometry_preserved",
                                          "uv_preserved", "transform_preserved"), True)
                evidence["device"] = f"OPTIX: {GPU_NAME}"
                argv[argv.index("--report") + 1].write_text(json.dumps(evidence), encoding="utf-8")
                self.assertEqual(exe, root / "blender.exe")
                self.assertIn("--python-exit-code", argv)
                if "--raw" in argv:
                    self.assertEqual(argv[argv.index("--raw") + 1], raw)
                else:
                    self.assertEqual(argv[argv.index("--image") + 1], image)

            lab = {"no_lab": False, "lab_name": "stalker", "open": False}
            game = argparse.Namespace(run=run.name, batch=3, raw=raw, seed=42, **lab)
            project = argparse.Namespace(run=run.name, batch=3, image=image, game=None, **lab)
            with patch("blackwood.command", side_effect=fake_process) as command, \
                    patch("blackwood.VramMonitor", side_effect=self.telemetry), \
                    patch("blackwood.require_idle"), patch("blackwood.REPO_ROOT", root):
                made = playable_model(config, game, "game")
                baked = playable_model(config, project, "projected")
                self.assertEqual(playable_model(config, project, "projected"), baked)
                self.assertEqual(command.call_count, 2)
                self.assertEqual(baked["source_sha256"], made["artifacts"][0]["sha256"])
                self.assertEqual([baked["run"], baked["seed"], baked["batch"]], [run.name, 42, 3])
                manifest = json.loads(Path(baked["handoff"]["manifest"]).read_text(encoding="utf-8"))
                self.assertEqual((manifest["stage"], manifest["seed"], manifest["batch"]), ("projected", 42, 3))
                self.assertEqual(manifest["source"]["raw_sha256"], made["source_sha256"])
                self.assertTrue(baked["lab_url"].endswith("/" + baked["artifacts"][0]["file"]))
                command.side_effect = PipelineError("FIXTURE_ADAPTER_FAILED")
                with self.assertRaisesRegex(PipelineError, "FIXTURE_ADAPTER_FAILED.*Failure report"):
                    playable_model(config, argparse.Namespace(**(vars(game) | {"batch": 4})), "game")
                self.assertFalse((root / "3d/incoming/stalker/stalker-01-b4-game").exists())
                failure = next((root / "build/blackwood").glob("game-failed-*.json"))
                self.assertEqual(json.loads(failure.read_text(encoding="utf-8"))["error"], "FIXTURE_ADAPTER_FAILED")
                command.side_effect = fake_process
                private = playable_model(config, argparse.Namespace(**(vars(game) | {"batch": 5, "no_lab": True})), "game")
                self.assertNotIn("handoff", private)
                self.assertFalse((root / "3d/incoming/stalker/stalker-01-b5-game").exists())
                image.write_bytes(png(0))
                with self.assertRaisesRegex(PipelineError, "STAGE_CONFLICT"):
                    process_model(config, project, "baked")

    def test_seed_batch_run_and_explicit_selection(self):
        with tempfile.TemporaryDirectory(prefix="Blackwood körning ") as directory:
            root = Path(directory)
            concept = {"1": {"class_type": "ConceptFixture", "inputs":
                       {"seed": 0, "body": "A-pose [BODY] front", "prefix": "fixed", "batch_size": 8}}}
            trellis = {
                "2": {"class_type": "TrellisFixture", "inputs": {"image": "fixed", "prefix": "fixed", "size": 512}},
                "3": {"class_type": "CutoutFixture", "inputs": {"prefix": "fixed"}},
            }
            bindings = {
                "concept": {"preset": [["1", "batch_size", 8]], "seed": ["1", "seed"], "body": ["1", "body"],
                            "body_token": "[BODY]", "prefix": ["1", "prefix"], "output": ["1", "images"]},
                "3d": {"preset": [["2", "size", 512]], "image": ["2", "image"], "prefix": ["2", "prefix"],
                       "output": ["2", "files"], "cutout": {"prefix": ["3", "prefix"], "output": ["3", "images"]}},
            }
            config = {"workflows": {}, "workflow_bindings": str(root / "bindings.json"),
                      "comfy_url": "http://127.0.0.1:8188", "runs_root": str(root / "körningar")}
            registry = {}
            for name, graph in (("concept", concept), ("3d", trellis)):
                path = root / (name + ".json")
                path.write_text(json.dumps(graph), encoding="utf-8")
                config["workflows"][name] = str(path)
                bindings[name]["workflow_sha256"] = sha256(path)
                for node in graph.values():
                    registry[node["class_type"]] = {"input": {"required": {key: [] for key in node["inputs"]}}}
            Path(config["workflow_bindings"]).write_text(json.dumps(bindings), encoding="utf-8")
            run_id = "stalker-01"
            seed = 2685697290443443

            def job(job_id, graph, intent, timeout):
                node, data = next(iter(graph.items()))
                inputs = data["inputs"]
                prefix = inputs["prefix"]
                if node == "1":
                    self.assertEqual(inputs["body"], "A-pose Slank överkropp front")
                    self.assertEqual(inputs["seed"], seed)
                    count, suffix, field = inputs["batch_size"], ".png", "images"
                else:
                    self.assertEqual(inputs["size"], 512)
                    self.assertTrue(inputs["image"].startswith(f"blackwood/{run_id}/{job_id}/"))
                    count, suffix, field = 1, ".glb", "files"
                outputs = {node: {field: [
                    {"filename": f"{prefix.rsplit('/', 1)[1]}_{i:05d}{suffix}",
                     "subfolder": prefix.rsplit("/", 1)[0], "type": "output"} for i in range(count)
                ]}}
                if node == "2":
                    subfolder, filename = graph["3"]["inputs"]["prefix"].rsplit("/", 1)
                    outputs["3"] = {"images": [{"filename": filename + "_00001.png", "subfolder": subfolder, "type": "output"}]}
                return {"outputs": outputs}

            def download(ref, path, validate):
                if path.suffix == ".png":
                    path.write_bytes(png())
                else:
                    glb(path)
                validate(path)

            stats = {"devices": [{"type": "cuda", "name": GPU_NAME}]}
            with patch("blackwood.require_idle"), \
                    patch.object(Comfy, "request", side_effect=lambda endpoint: stats if endpoint == "/system_stats" else registry), \
                    patch("blackwood.VramMonitor", side_effect=self.telemetry), \
                    patch.object(Comfy, "job", side_effect=job) as submit, patch.object(Comfy, "download", side_effect=download), \
                    patch.object(Comfy, "upload") as upload:
                concepts = generate(config, argparse.Namespace(run=run_id, seed=seed, body="Slank överkropp", timeout=1), "concept")
                self.assertEqual([item["batch"] for item in concepts[0]["artifacts"]], list(range(1, 9)))
                raw = generate(config, argparse.Namespace(run=run_id, select=[3, 7], timeout=1), "3d")
                self.assertEqual(raw, generate(config, argparse.Namespace(run=run_id, select=[3, 7], timeout=1), "3d"))
                self.assertEqual(submit.call_count, 3)
                self.assertEqual(upload.call_count, 2)
            self.assertEqual([(item["run"], item["seed"], item["batch"]) for item in raw],
                             [(run_id, seed, 3), (run_id, seed, 7)])
            self.assertEqual([item["artifacts"][0]["role"] for item in raw], ["raw", "raw"])
            self.assertEqual([item["artifacts"][1]["role"] for item in raw], ["cutout", "cutout"])


if __name__ == "__main__":
    unittest.main()
