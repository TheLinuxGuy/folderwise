"""Read a project's working tree or Git index through the same document boundary."""
from __future__ import annotations

import subprocess
from pathlib import Path

import docslib as dl


class DocumentSource:
    def __init__(self, root: Path, staged: bool = False):
        self.root = root
        self.blobs: dict[str, str] | None = None
        self.directories = {""}
        if staged:
            result = self.git("ls-files", "--stage", "-z")
            self.blobs = {}
            for entry in filter(None, result.split("\0")):
                meta, rel = entry.split("\t", 1)
                mode, blob, stage = meta.split()
                if stage != "0":
                    raise ValueError(f"{rel}: unresolved merge entry")
                if mode in {"100644", "100755", "120000"}:
                    self.blobs[rel] = blob
                    self.directories.update(p.as_posix() for p in Path(rel).parents if p.as_posix() != ".")

    def git(self, *args: str) -> str:
        result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True)
        if result.returncode:
            raise ValueError(result.stderr.strip())
        return result.stdout

    def read(self, rel: str) -> str | None:
        if self.blobs is not None:
            blob = self.blobs.get(rel)
            return self.git("cat-file", "blob", blob) if blob else None
        path = self.root / rel
        return path.read_text() if path.is_file() else None

    def is_file(self, rel: str) -> bool:
        return rel in self.blobs if self.blobs is not None else (self.root / rel).is_file()

    def exact_path(self, rel: str) -> Path | None:
        if self.blobs is None:
            return dl._exact_path(self.root, rel)
        return self.root / rel if rel in self.blobs or rel in self.directories else None

    def docs(self, cfg: dict) -> list[Path]:
        if self.blobs is None:
            return dl.iter_docs(self.root, cfg)
        return [Path(rel) for rel in sorted(self.blobs) if rel.endswith(".md") and not dl.is_excluded(Path(rel), cfg)]
