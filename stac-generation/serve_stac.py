#!/usr/bin/env python3
"""
Minimal HTTP server with CORS headers for local STAC browser testing.

Usage:
    python serve_stac.py              # serves stac-wocat/ on port 8866
    python serve_stac.py stac-global  # serves stac-global/ on port 8866
    python serve_stac.py stac-wocat 8877
"""
import http.server, sys, os

directory = sys.argv[1] if len(sys.argv) > 1 else "stac-wocat"
port      = int(sys.argv[2]) if len(sys.argv) > 2 else 8866

class CORSHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # silence request logs

print(f"Serving {os.path.abspath(directory)}/ on http://localhost:{port}")
print()
print("Open in STAC Browser:")
print(f"  https://radiantearth.github.io/stac-browser/#/http://localhost:{port}/collection.json")
print()
print("Press Ctrl+C to stop.")

with http.server.HTTPServer(("", port), CORSHandler) as s:
    s.serve_forever()
