"""Admission boundary for reconstructed model-only supervision.

NO production transport is qualified in this historical-source reconstruction.
Disabling Strands retries alone does not control provider-internal retries,
transport ambiguity, or billing. No environment flag, model config/provenance,
provider name, URL or credential may promote a transport through this boundary.

Local authored-model tests replace this function for their exact fixture class,
under zero-network-attempt sentries. That test injection is not a live transport
implementation or deployment capability.
"""


class ModelOnlyTransportUnqualified(ValueError):
    """The reconstructed mode has no production transport admission."""


def qualified(model: object | None) -> bool:
    """Refuse all production adapters until transport control is separately rebuilt."""
    return False
