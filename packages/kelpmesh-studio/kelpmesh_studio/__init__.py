"""kelpmesh-studio meta-package.

Installing this package gives you kelpmesh-core (the full CLI engine) plus
the FastAPI + uvicorn dependencies required to run the browser dashboard:

    pip install kelpmesh-studio
    kelpmesh studio          # opens http://localhost:8501

The browser UI code lives in kelpmesh.studio (part of kelpmesh-core).
This package is purely a dependency declaration — no additional Python code.
"""

__version__ = "0.2.0"
