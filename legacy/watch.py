#!/usr/bin/env python3
"""
DashML File Watcher & Auto-reload Server
Watches .dashml files and auto-reloads browser demos
"""
import time
import http.server
import socketserver
import os
import hashlib
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class DashMLFileHandler(FileSystemEventHandler):
    """Watches for .dashml file changes"""
    
    def __init__(self):
        self.last_modified = {}
        self.reload_flag_file = Path('.dashml_reload')
    
    def on_modified(self, event):
        if event.src_path.endswith('.dashml'):
            print(f"🔄 Detected change in: {event.src_path}")
            self.trigger_reload()
    
    def on_created(self, event):
        if event.src_path.endswith('.dashml'):
            print(f"✨ New DashML file: {event.src_path}")
            self.trigger_reload()
    
    def trigger_reload(self):
        """Create a flag file that browser can poll"""
        self.reload_flag_file.write_text(str(time.time()))
        print("   → Browser will auto-reload")


class CORSHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler with CORS support for local development"""
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress standard logging for cleaner output
        pass


def start_file_watcher():
    """Start watching .dashml files"""
    event_handler = DashMLFileHandler()
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=True)
    observer.start()
    print("👀 Watching for .dashml file changes...")
    return observer


def start_http_server(port=8000):
    """Start HTTP server with CORS support"""
    handler = CORSHTTPRequestHandler
    
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"🌐 HTTP Server running at http://localhost:{port}")
        print(f"   → index.html: http://localhost:{port}/index.html")
        print(f"   → example_integration.html: http://localhost:{port}/example_integration.html")
        print("\n📝 Edit any .dashml file and see instant updates in the browser!")
        print("   Press Ctrl+C to stop\n")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n👋 Shutting down...")


def main():
    print("=" * 60)
    print("🚀 DashML Development Server with Auto-reload")
    print("=" * 60)
    print()
    
    # Start file watcher in background
    observer = start_file_watcher()
    
    try:
        # Start HTTP server (blocking)
        start_http_server(port=8000)
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()

