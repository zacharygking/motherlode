"""Datasets are directories with a manifest. They are the only thing that crosses a project
boundary: a producer writes one, a consumer reads it by path and checks the hash.

    manifest.json   name, schema, version, created_at, producer, sources, files (sha256 each),
                    dataset_sha256 (over the file hashes), meta
    items.jsonl     schema "items-v1": one row per item, {"id", "text", optional "truth"
                    ({dimension: label}), optional "meta", any extra context fields}
    rubric.md       optional, the rubric the producer wants applied
    rubric.json     optional, its spec
    judgments.jsonl / labels/*.jsonl / validation.json
                    schema "graded-v1": dimensioned label rows and the prospect report, with a
                    source pointing at the items dataset they grade

Hashes are 12 hex chars of sha256, like every other hash here.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SCHEMAS = ("items-v1", "graded-v1")


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def _dataset_hash(files: dict[str, str]) -> str:
    return hashlib.sha256("\n".join(f"{k} {v}" for k, v in sorted(files.items())).encode()).hexdigest()[:12]


@dataclass
class Dataset:
    path: Path
    manifest: dict

    @property
    def name(self) -> str:
        return self.manifest["name"]

    @property
    def schema(self) -> str:
        return self.manifest["schema"]

    @property
    def hash(self) -> str:
        return self.manifest["dataset_sha256"]

    def ref(self) -> dict:
        return {"name": self.name, "dataset_sha256": self.hash, "path": str(self.path)}

    def file(self, rel: str) -> Path:
        return self.path / rel

    def items(self) -> list[dict]:
        p = self.path / "items.jsonl"
        return read_jsonl(p) if p.exists() else []

    def rows(self, rel: str) -> list[dict]:
        return read_jsonl(self.path / rel)

    def rubric(self):
        from .rubric import load_rubric
        return load_rubric(self.path / "rubric.md", self.path / "rubric.json")


def write_dataset(out_dir: Path | str, name: str, schema: str, *, items: Iterable[dict] | None = None,
                  files: dict[str, str | bytes | Path] | None = None, sources: list[dict] | None = None,
                  producer: str = "", meta: dict | None = None, version: str = "1") -> Dataset:
    """Write files and the manifest. ``files`` maps a relative path to text, bytes or a source path."""
    if schema not in SCHEMAS:
        raise ValueError(f"unknown schema {schema!r}; known: {SCHEMAS}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    if items is not None:
        rows = list(items)
        for r in rows:
            if "id" not in r:
                raise ValueError("every item needs an id")
            if schema == "items-v1" and "text" not in r:
                raise ValueError(f"item {r['id']} has no text")
        write_jsonl(rows, out / "items.jsonl")
        written["items.jsonl"] = file_hash(out / "items.jsonl")
    for rel, content in (files or {}).items():
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, Path):
            dest.write_bytes(content.read_bytes())
        elif isinstance(content, bytes):
            dest.write_bytes(content)
        else:
            dest.write_text(content, encoding="utf-8")
        written[rel] = file_hash(dest)
    manifest = {
        "name": name, "schema": schema, "version": version,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "producer": producer, "sources": sources or [], "files": written,
        "dataset_sha256": _dataset_hash(written), "meta": meta or {},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return Dataset(out, manifest)


def read_dataset(path: Path | str, verify: bool = True) -> Dataset:
    p = Path(path)
    manifest = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
    ds = Dataset(p, manifest)
    if verify:
        problems = verify_dataset(ds)
        if problems:
            raise ValueError(f"dataset {p} fails verification: " + "; ".join(problems))
    return ds


def verify_dataset(ds: Dataset) -> list[str]:
    problems = []
    for rel, expected in ds.manifest.get("files", {}).items():
        f = ds.path / rel
        if not f.exists():
            problems.append(f"missing {rel}")
        elif file_hash(f) != expected:
            problems.append(f"{rel} hash {file_hash(f)} != manifest {expected}")
    if _dataset_hash(ds.manifest.get("files", {})) != ds.manifest.get("dataset_sha256"):
        problems.append("dataset_sha256 does not match the file hashes")
    return problems


def read_jsonl(path: Path | str) -> list[dict]:
    rows = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(rows: Iterable[dict], path: Path | str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def append_jsonl(rows: Iterable[dict], path: Path | str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def truth_rows(items: Iterable[dict], rubric_hash_: str) -> list[dict]:
    """Ground truth as a rater: one label row per item and dimension in the item's ``truth``."""
    rows = []
    for it in items:
        for dim, label in (it.get("truth") or {}).items():
            rows.append({"item_id": str(it["id"]), "rater": "ground_truth", "dimension": dim,
                         "label": str(label), "rubric_hash": rubric_hash_, "pass": "blind"})
    return rows
