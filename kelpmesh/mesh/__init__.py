"""kelpmesh Mesh — cross-project model references, access control, and contracts."""

from kelpmesh.mesh.access import AccessChecker, AccessPolicy
from kelpmesh.mesh.config import MeshConfig, MeshProject
from kelpmesh.mesh.contracts import ContractValidator, InterfaceModel, ProducerContract
from kelpmesh.mesh.health import MeshHealthChecker, ProjectHealth
from kelpmesh.mesh.resolver import CrossProjectRef, MeshResolver

__all__ = [
    "MeshConfig",
    "MeshProject",
    "MeshResolver",
    "CrossProjectRef",
    "ProducerContract",
    "ContractValidator",
    "InterfaceModel",
    "AccessPolicy",
    "AccessChecker",
    "MeshHealthChecker",
    "ProjectHealth",
]
