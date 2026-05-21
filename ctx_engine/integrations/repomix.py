from __future__ import annotations


class RepomixDisabled:
    """P0 boundary marker: no external repo packer is used."""

    def __init__(self) -> None:
        raise RuntimeError("Repomix-style packing is P1/P2 only; use local providers in P0.")
