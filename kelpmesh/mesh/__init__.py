"""kelpmesh Mesh — cross-project model references, access control, and contracts."""

from kelpmesh.mesh.config import MeshConfig, MeshProject
from kelpmesh.mesh.resolver import MeshResolver, CrossProjectRef
from kelpmesh.mesh.contracts import ProducerContract, ContractValidator, InterfaceModel
from kelpmesh.mesh.access import AccessPolicy, AccessChecker
from kelpmesh.mesh.health import MeshHealthChecker, ProjectHealth

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
