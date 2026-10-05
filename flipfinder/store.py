"""Tiny JSON state store (lives on the repo's `state` branch between GitHub Actions runs)."""
from __future__ import annotations

import gzip
import json
import os


class Store:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _p(self, name):
        return os.path.join(self.root, name)

    def load(self, name: str, default=None):
        p = self._p(name)
        if not os.path.exists(p):
            return default if default is not None else {}
        try:
            if name.endswith(".gz"):
                with gzip.open(p, "rt", encoding="utf-8") as f:
                    return json.load(f)
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}

    def save(self, name: str, data):
        p = self._p(name)
        tmp = p + ".tmp"
        if name.endswith(".gz"):
            with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, p)
