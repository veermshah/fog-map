#!/usr/bin/env python3
"""Serve docs/ and /api/analyze locally, mirroring the Vercel deployment (stdlib).

    python dev_server.py            # http://127.0.0.1:8080/
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from api.analyze import handler as AnalyzeHandler

ROOT = Path(__file__).resolve().parent


class DevHandler(SimpleHTTPRequestHandler):
    def _api(self, method):
        if self.path.split('?')[0].rstrip('/') == '/api/analyze':
            getattr(AnalyzeHandler, method)(self)
            return True
        return False

    def do_GET(self):
        if not self._api('do_GET'):
            super().do_GET()

    def do_POST(self):
        if not self._api('do_POST'):
            self.send_error(404)

    _send = AnalyzeHandler._send


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(DevHandler, directory=str(ROOT / 'docs')))
    print(f'Fog Map dev server on http://127.0.0.1:{args.port}/')
    server.serve_forever()


if __name__ == '__main__':
    main()
