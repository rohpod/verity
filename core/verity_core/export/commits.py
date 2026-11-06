"""The commit that introduced each decision (ADR 0029, decision 9; D10).

A decision's Evidence records its file and the file's sha256, but not the commit: a commit SHA
would change the hash on every commit. The SHA is looked up here, at export. For each decision
we walk the history of its file and take the oldest commit whose file content matches the
recorded `file_sha256`. Only `%H` is read, never an author or a message.

A live export refuses if any decision has no such commit, because the file in the snapshot
would then point at a decision nobody can find in git. A fixture export writes `null` and never
runs git, so its bytes do not depend on the checkout.
"""

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

import networkx as nx

from verity_core.model.enums import EvidenceKind
from verity_core.model.nodes import Evidence

_A_SHA = re.compile(r"[0-9a-f]{40}")
_GIT_TIMEOUT_SECONDS = 30


class CommitLookupError(Exception):
    """A decision has no commit, or git could not be read. Names decisions and counts only."""


def decision_files(graph: nx.MultiDiGraph) -> list[tuple[str, str, str]]:
    """`(decision_id, decision_file, file_sha256)` for each decision Evidence, sorted."""
    found: dict[str, tuple[str, str, str]] = {}
    for node in graph.nodes:
        record = graph.nodes[node]["record"]
        if not isinstance(record, Evidence) or record.kind not in (
            EvidenceKind.ATTESTATION,
            EvidenceKind.DOCUMENT_REF,
        ):
            continue
        content = record.content or {}
        if {"decision_id", "decision_file", "file_sha256"} <= content.keys():
            decision_id = content["decision_id"]
            found[decision_id] = (decision_id, content["decision_file"], content["file_sha256"])
    return [found[key] for key in sorted(found)]


def _git(repo: Path, *args: str) -> bytes:
    try:
        done = subprocess.run(  # noqa: S603 - a fixed git command, no shell
            ["git", "-C", str(repo), *args],  # noqa: S607
            capture_output=True,
            check=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CommitLookupError(f"git could not be read: {type(exc).__name__}") from exc
    return done.stdout


def commit_for(repo: Path, path: str, file_sha256: str) -> str | None:
    """The oldest commit in which `path` has the content with `file_sha256`, or None."""
    log = _git(repo, "log", "--format=%H", "--", path).decode("ascii").split()
    for sha in reversed(log):  # `git log` is newest first
        try:
            blob = _git(repo, "show", f"{sha}:{path}")
        except CommitLookupError:  # the file did not exist in that commit (a deletion)
            continue
        if hashlib.sha256(blob).hexdigest() == file_sha256:
            return sha
    return None


def lookup(graph: nx.MultiDiGraph, repo: Path, *, require: bool) -> list[dict[str, Any]]:
    """One row per decision. With `require`, a decision with no commit refuses the export."""
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for decision_id, decision_file, file_sha256 in decision_files(graph):
        sha = commit_for(repo, decision_file, file_sha256)
        if sha is None:
            missing.append(decision_id)
        assert sha is None or _A_SHA.fullmatch(sha)
        rows.append(_row(decision_id, decision_file, file_sha256, sha))
    if require and missing:
        raise CommitLookupError(
            f"no commit holds the recorded file for {len(missing)} decision(s): "
            f"{', '.join(missing)}. Commit the decision files, then export again"
        )
    return rows


def without_commits(graph: nx.MultiDiGraph) -> list[dict[str, Any]]:
    """The fixture source: the same rows with `commit_sha` null, and no git."""
    return [_row(*item, None) for item in decision_files(graph)]


def _row(
    decision_id: str, decision_file: str, file_sha256: str, commit_sha: str | None
) -> dict[str, Any]:
    return {
        "decision_id": decision_id,
        "decision_file": decision_file,
        "file_sha256": file_sha256,
        "commit_sha": commit_sha,
    }
