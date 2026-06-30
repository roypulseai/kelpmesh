"""Shim for ``import kelpmesh_core`` — the PyPI package is ``kelpmesh-core`` but the import is ``kelpmesh``."""

from kelpmesh import *
from kelpmesh import __all__, __version__
