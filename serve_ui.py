#!/usr/bin/env python3
"""Serve ops console + booking UI (admin at :8090, booking at :8090/fly/). Run from repo root."""
import http.server
import socketserver
import os

os.chdir(os.path.join(os.path.dirname(__file__), "ops_console"))
PORT = 8090
Handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving ops console at http://localhost:{PORT}/")
    print(f"  Admin:  http://localhost:{PORT}/admin-dashboard.html")
    print(f"  Pilot:  http://localhost:{PORT}/pilot-dashboard.html")
    print(f"  Booking: http://localhost:{PORT}/fly/booking.html")
    print(f"Set API base in browser: localStorage.setItem('FLYSUNBIRD_API_BASE','http://localhost:8000/api/v1')")
    print("(Ctrl+C to stop)")
    httpd.serve_forever()
