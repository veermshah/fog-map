"""Vercel Python function: POST a Markdown spec, get a ranked divergence report.

GET  /api/analyze  -> which backend this deployment uses and the input limits.
POST /api/analyze  -> {"spec": "..."} returns findings plus interpretations.

The default backend is the labeled offline rules demo, which costs nothing.
A live model backend is used only when the deployment sets FOG_LIVE_BACKEND
to "api" (with OPENAI_API_KEY, and optionally OPENAI_BASE_URL and FOG_MODEL)
or "ollama" (with a reachable OLLAMA_HOST). Keys stay server side.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fog  # noqa: E402

MAX_BODY_BYTES = fog.MAX_SPEC_CHARS * 4 + 1024


def configured_backend():
    live = os.getenv('FOG_LIVE_BACKEND', '').strip().lower()
    if live == 'api' and os.getenv('OPENAI_API_KEY'):
        return 'api'
    if live == 'ollama':
        return 'ollama'
    return 'offline'


def public_interpretation(answer):
    """Drop raw provider text from the response; keep model name, usage, timing."""
    answer = dict(answer)
    evidence = answer.get('provider_evidence')
    if isinstance(evidence, dict):
        answer['provider_evidence'] = {k: v for k, v in evidence.items() if k != 'raw_content'}
    return answer


def run(body):
    """Pure request logic, kept separate from HTTP plumbing so it can be tested."""
    try:
        payload = json.loads(body or b'{}')
    except (ValueError, UnicodeDecodeError):
        return 400, dict(error='Body must be JSON like {"spec": "..."}')
    if not isinstance(payload, dict):
        return 400, dict(error='Body must be a JSON object')
    spec = payload.get('spec')
    backend = configured_backend()
    try:
        result = fog.analyze(spec, backend)
    except ValueError as error:
        status = 400 if backend == 'offline' or 'Spec' in str(error) else 502
        return status, dict(error=str(error), backend=backend)
    except OSError as error:  # network failure reaching a live provider
        return 502, dict(error=f'Model provider unavailable: {error}', backend=backend)
    result['interpretations'] = [public_interpretation(a) for a in result['interpretations']]
    result['line_count'] = len(spec.splitlines())
    return 200, result


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        backend = configured_backend()
        self._send(200, dict(backend=backend, label=fog.backend_label(backend),
                             max_chars=fog.MAX_SPEC_CHARS, max_lines=fog.MAX_SPEC_LINES))

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self._send(413, dict(error='Request body too large'))
            return
        status, payload = run(self.rfile.read(length))
        self._send(status, payload)

    def log_message(self, *args):
        pass
