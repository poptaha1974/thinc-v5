from __future__ import annotations

from typing import Protocol

from thinc_v5.domain.common import Provenance


class Engine[InputT, OutputT](Protocol):
    def assess(self, input: InputT, provenance: Provenance) -> OutputT:
        ...
