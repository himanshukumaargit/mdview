#!/usr/bin/env python3
import argparse
import webbrowser
import threading
import time
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

try:
    import markdown
except ImportError:
    print("Missing dependency: markdown. Install with: pip install markdown")
    sys.exit(1)

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("Missing dependency: watchdog. Install with: pip install watchdog")
    sys.exit(1)


def parse_front_matter(text):
    """Parse YAML front-matter and extract css field.
    Returns (css, body) where css is from front-matter or None.
    """
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    fm_block = text[3:end]
    body = text[end + 4:]
    css = None
    in_block_scalar = False
    block_lines = []
    for line in fm_block.split("\n"):
        if in_block_scalar:
            if line.startswith(" ") or line == "":
                block_lines.append(line)
                continue
            else:
                css = "\n".join(block_lines)
                in_block_scalar = False
                block_lines = []
        if line.startswith("css:"):
            val = line[4:].strip()
            if val == "|" or val == "|-":
                in_block_scalar = True
                block_lines = []
            elif val == ">" or val == ">-":
                in_block_scalar = True
                block_lines = []
            elif val:
                css = val
    if in_block_scalar:
        css = "\n".join(block_lines)
    return css, body


DEFAULT_CSS = """
body {
    max-width: 800px;
    margin: 0 auto;
    padding: 20px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    background: #fff;
}
h1, h2, h3 { color: #1a1a1a; margin-top: 24px; }
code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
pre code { background: none; padding: 0; }
pre { background: #f5f5f5; padding: 16px; border-radius: 6px; overflow-x: auto; }
blockquote { border-left: 4px solid #ddd; margin: 0; padding-left: 16px; color: #666; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
th { background: #f5f5f5; }
img { max-width: 100%; }
a { color: #0366d6; }
"""

LIVERELOAD_SCRIPT = """
<script>
(function() {
    var evtSource = new EventSource("/events");
    evtSource.onerror = function() {
        if (evtSource.readyState === EventSource.CLOSED) return;
    };
    evtSource.addEventListener("reload", function() {
        evtSource.close();
        window.location.reload();
    });
    evtSource.addEventListener("css-update", function(e) {
        var style = document.getElementById("mdview-css");
        if (style) style.textContent = e.data;
    });
})();
</script>
"""


class DebouncedHandler(FileSystemEventHandler):
    def __init__(self, target_path, callback, delay=0.3):
        self.target = Path(target_path).resolve()
        self.callback = callback
        self.delay = delay
        self._timer = None

    def on_modified(self, event):
        if event.is_directory:
            return
        if Path(event.src_path).resolve() != self.target:
            return
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(self.delay, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def _fire(self):
        try:
            self.callback()
        except Exception:
            pass


class SSEServer(HTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._clients = []
        self._lock = threading.Lock()

    def add_client(self, client):
        with self._lock:
            self._clients.append(client)

    def remove_client(self, client):
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)

    def broadcast(self, event_type, data=""):
        with self._lock:
            for client in self._clients:
                try:
                    client.write(f"event: {event_type}\ndata: {data}\n\n".encode())
                    client.flush()
                except:
                    pass


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.server.add_client(self.wfile)
            self.wfile.write(": connected\n\n".encode())
            self.wfile.flush()
            while True:
                time.sleep(2)
                try:
                    self.wfile.write(": heartbeat\n\n".encode())
                    self.wfile.flush()
                except:
                    try:
                        self.server.remove_client(self.wfile)
                    except Exception:
                        pass
                    break
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            content = generate_html(self.server.md_path, self.server.css_text)
            self.wfile.write(content.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def handle(self):
        try:
            super().handle()
        except ConnectionError:
            pass

    def log_message(self, format, *args):
        pass


def read_file_with_retry(path, retries=5, delay=0.1):
    for i in range(retries):
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            if i == retries - 1:
                raise
            time.sleep(delay)


def resolve_css(md_path, cli_css, no_default_css):
    raw = read_file_with_retry(md_path)
    fm_css, _ = parse_front_matter(raw)

    if cli_css is not None:
        return cli_css, raw
    if fm_css is not None:
        return fm_css, raw
    if no_default_css:
        return "", raw
    return DEFAULT_CSS, raw


def strip_front_matter(text):
    _, body = parse_front_matter(text)
    return body


def generate_html(md_path, css_text):
    raw = read_file_with_retry(md_path)
    md_content = strip_front_matter(raw)
    html_body = markdown.markdown(
        md_content,
        extensions=["fenced_code", "codehilite", "tables", "sane_lists"]
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{Path(md_path).stem}</title>
<style id="mdview-css">{css_text}</style>
</head>
<body><div class="markdown-body">{html_body}</div>{LIVERELOAD_SCRIPT}</body>
</html>"""


def on_file_changed():
    srv = getattr(on_file_changed, "server", None)
    if srv is None:
        return
    for i in range(3):
        try:
            new_css, _ = resolve_css(srv.md_path, srv.cli_css, srv.no_default_css)
            break
        except OSError:
            if i == 2:
                return
            time.sleep(0.15)
    try:
        if new_css != srv.css_text:
            srv.css_text = new_css
        srv.broadcast("reload")
    except Exception:
        pass


def get_free_port(start=8765):
    import socket
    port = start
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
            port += 1


def main():
    parser = argparse.ArgumentParser(
        description="Render a Markdown file in your browser with live reload."
    )
    parser.add_argument("file", help="Path to the Markdown file")
    parser.add_argument("--css", "-c", help="Inline CSS string (overrides default)")
    parser.add_argument("--css-file", help="Path to a CSS file to use")
    parser.add_argument("--no-default-css", action="store_true",
                        help="Start with no CSS (use with --css or --css-file)")
    parser.add_argument("--port", "-p", type=int, default=0,
                        help="Port for the HTTP server (default: auto)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Don't open browser automatically")
    args = parser.parse_args()

    md_path = Path(args.file).resolve()
    if not md_path.exists():
        print(f"Error: file not found: {md_path}")
        sys.exit(1)

    cli_css = None
    if args.css_file:
        cli_css = Path(args.css_file).read_text(encoding="utf-8")
    if args.css:
        cli_css = args.css

    css_text, _ = resolve_css(md_path, cli_css, args.no_default_css)

    port = args.port if args.port else get_free_port()
    server = SSEServer(("127.0.0.1", port), RequestHandler)
    server.md_path = md_path
    server.css_text = css_text
    server.cli_css = cli_css
    server.no_default_css = args.no_default_css
    on_file_changed.server = server

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    observer = Observer()
    event_handler = DebouncedHandler(md_path, on_file_changed, delay=0.3)
    observer.schedule(event_handler, str(md_path.parent), recursive=False)
    observer.start()

    url = f"http://127.0.0.1:{port}"
    if not args.no_browser:
        webbrowser.open(url)

    print(f"Serving {md_path.name} at {url}")
    print("Watching for changes... Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        observer.stop()
        observer.join()
        server.shutdown()


if __name__ == "__main__":
    main()
