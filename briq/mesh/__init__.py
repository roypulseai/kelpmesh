"""briq Mesh — cross-project model references, access control, and contracts."""

from briq.mesh.config import MeshConfig, MeshProject
from briq.mesh.resolver import MeshResolver, CrossProjectRef
from briq.mesh.contracts import ProducerContract, ContractValidator, InterfaceModel
from briq.mesh.access import AccessPolicy, AccessChecker
from briq.mesh.health import MeshHealthChecker, ProjectHealth

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
