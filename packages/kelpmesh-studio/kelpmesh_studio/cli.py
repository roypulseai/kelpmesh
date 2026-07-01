"""kelpmesh-studio — launch the KelpMesh Studio web dashboard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Launch KelpMesh Studio web dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", "-p", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--project-dir", default=".", help="Project directory")
    parser.add_argument("--debug", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn not installed. Install with: pip install kelpmesh-studio")
        sys.exit(1)

    try:
        import fastapi
    except ImportError:
        print("Error: fastapi not installed. Install with: pip install kelpmesh-studio")
        sys.exit(1)

    from kelpmesh_studio.app import create_app

    project_path = str(Path(args.project_dir).resolve())
    app = create_app(project_path)

    url = f"http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}"
    print()
    print("  kelpmesh Studio  SQL & Python Transformation IDE")
    print(f"  Open: {url}")
    print(f"  Project: {project_path}")
    print("  Press Ctrl+C to stop.")
    print()

    try:
        import threading
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    except Exception:
        pass

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.debug,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
