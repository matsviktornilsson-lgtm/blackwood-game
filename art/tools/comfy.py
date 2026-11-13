"""Loopback ComfyUI API client. Validation and recovery use GET only."""

import hashlib
import json
import re
import shutil
import tempfile
import time
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from send_to_game import PipelineError, read_json, sha256, write_json


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def graph_hash(graph):
    return hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest()


def input_choices(rule):
    if not rule:
        return None
    if isinstance(rule[0], list):
        return rule[0]
    if rule[0] == "COMBO" and len(rule) > 1:
        return rule[1].get("options")
    return None


def validate_graph(graph, registry, deferred=()):
    deferred = {tuple(pair) for pair in deferred}
    for node_id, node in graph.items():
        if not isinstance(node, dict) or "class_type" not in node or not isinstance(node.get("inputs"), dict):
            raise PipelineError(f"WORKFLOW_API_FORMAT: node {node_id}. Export ComfyUI API format.")
        class_name = node["class_type"]
        if class_name not in registry:
            raise PipelineError(f"NODE_MISSING: {node_id} {class_name}")
        spec = registry[class_name].get("input", {})
        required = spec.get("required", {})
        inputs = node["inputs"]
        for key in required.keys() - inputs.keys():
            raise PipelineError(f"WORKFLOW_INPUT_MISSING: {node_id}.{key}")
        for key, value in inputs.items():
            declared = required | spec.get("optional", {})
            if key not in declared and not registry[class_name].get("accept_all_inputs"):
                raise PipelineError(f"WORKFLOW_INPUT_UNKNOWN: {node_id}.{key}")
            rule = declared.get(key, [])
            if (node_id, key) in deferred:
                continue
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], int):
                upstream = graph.get(value[0])
                outputs = registry.get(upstream["class_type"], {}).get("output", []) if upstream else []
                if not upstream or not 0 <= value[1] < len(outputs):
                    raise PipelineError(f"WORKFLOW_LINK: {node_id}.{key} references {value}")
                continue
            if not rule:
                continue
            choices = input_choices(rule)
            if choices is not None and value not in choices:
                code = "MODEL_MISSING" if isinstance(value, str) and "." in value else "WORKFLOW_CHOICE"
                raise PipelineError(f"{code}: {node_id}.{key} = {value!r}")


def collect_outputs(history, node_id, field, prefix, suffix, count):
    refs = history.get("outputs", {}).get(node_id, {}).get(field, [])
    if len(refs) != count:
        raise PipelineError(f"OUTPUT_COUNT: {node_id}.{field} expected {count}, got {len(refs)}")
    expected = PurePosixPath(prefix)
    names = set()
    for ref in refs:
        filename = ref.get("filename", "")
        subfolder = ref.get("subfolder", "").replace("\\", "/")
        if (ref.get("type") != "output" or subfolder != expected.parent.as_posix() or
                not filename.startswith(expected.name) or not filename.lower().endswith(suffix) or
                not re.fullmatch(r"[a-zA-Z0-9_.-]+", filename) or ".." in filename or filename.casefold() in names):
            raise PipelineError(f"OUTPUT_REFERENCE: {node_id}.{field} does not match {prefix} and {suffix}.")
        names.add(filename.casefold())
    return refs


class Comfy:
    def __init__(self, url):
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or parsed.netloc != f"127.0.0.1:{parsed.port}" or
                parsed.path or parsed.query or parsed.fragment or not parsed.port):
            raise PipelineError("COMFY_URL: expected http://127.0.0.1:<port>.")
        self.url = url
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, endpoint, payload=None, *, timeout=5):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        with self.opener.open(Request(self.url + endpoint, data, headers), timeout=timeout) as response:
            return json.load(response)

    def upload(self, path, subfolder, digest):
        filename = f"{digest}.png"
        # aiohttp rejects multipart boundaries longer than 70 characters.
        boundary = "blackwood-" + digest[:32]
        fields = {"type": "input", "subfolder": subfolder, "overwrite": "false"}
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
                 for key, value in fields.items()]
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\n'
                     'Content-Type: image/png\r\n\r\n'.encode())
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise PipelineError("SELECTION_HASH: selected image changed before upload.")
        parts.extend((data, f"\r\n--{boundary}--\r\n".encode()))
        request = Request(self.url + "/upload/image", b"".join(parts),
                          {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with self.opener.open(request, timeout=30) as response:
            received = json.load(response)
        if (received.get("name"), received.get("subfolder", "").replace("\\", "/"), received.get("type")) != (
                filename, subfolder, "input"):
            raise PipelineError("UPLOAD_REFERENCE: ComfyUI returned an unexpected reference.")
        return f"{subfolder}/{filename}"

    def download(self, ref, path, validate):
        query = urlencode({key: ref[key] for key in ("filename", "type", "subfolder")})
        with tempfile.TemporaryDirectory(prefix=".blackwood-", dir=path.parent) as directory:
            staged = Path(directory) / path.name
            with self.opener.open(self.url + "/view?" + query, timeout=60) as source, staged.open("xb") as dest:
                shutil.copyfileobj(source, dest)
            validate(staged)
            if not path.exists():
                try:
                    staged.rename(path)
                except FileExistsError:
                    pass
            if staged.exists() and sha256(staged) != sha256(path):
                raise PipelineError(f"OUTPUT_CONFLICT: {path}")

    def job(self, job_id, graph, intent_path, timeout):
        intent = {"id": job_id, "graph_sha256": graph_hash(graph), "server": self.url}
        try:
            write_json(intent_path, intent, exclusive=True)
            submit = True
        except FileExistsError:
            if read_json(intent_path) != intent:
                raise PipelineError(f"INTENT_CONFLICT: {intent_path}")
            submit = False
        uncertain = not submit
        if submit:
            try:
                response = self.request("/prompt", {"prompt": graph, "prompt_id": job_id})
            except HTTPError as error:
                if 400 <= error.code < 500:
                    try:
                        failure = json.load(error)
                    except ValueError:
                        failure = {}
                    detail = failure.get("error", {}).get("type", "")
                    raise PipelineError(f"PROMPT_REJECTED: {job_id} HTTP {error.code} {detail}") from error
                uncertain = True
            except (OSError, ValueError):
                uncertain = True
            else:
                uncertain = response.get("prompt_id") != job_id
        deadline = time.monotonic() + timeout
        while True:
            try:
                item = self.request(f"/history/{job_id}").get(job_id)
                if item:
                    status = item.get("status", {})
                    if status.get("status_str") == "error":
                        detail = next((data for event, data in status.get("messages", [])
                                       if event == "execution_error"), {})
                        raise PipelineError(f"EXECUTION_ERROR: {job_id} node {detail.get('node_id')} "
                                            f"{detail.get('exception_type', '')}")
                    if status.get("completed") and status.get("status_str") == "success":
                        return item
                    uncertain = False
                if uncertain:
                    queue = self.request("/queue")
                    if not any(entry[1] == job_id for key in ("queue_running", "queue_pending") for entry in queue[key]):
                        raise PipelineError(f"SUBMISSION_UNKNOWN: {job_id}. Intent retained at {intent_path}.")
                    uncertain = False
            except (URLError, TimeoutError, ValueError) as error:
                raise PipelineError(f"JOB_LOOKUP_UNAVAILABLE: {job_id}. Intent retained at {intent_path}.") from error
            if time.monotonic() >= deadline:
                raise PipelineError(f"JOB_PENDING: {job_id}. Repeat the same command to read its history.")
            time.sleep(min(2, max(0, deadline - time.monotonic())))
