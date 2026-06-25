"""Commit data changes to the private nested git repo under data/.

Every maintainer action (Excel upload, alias edit) lands as one commit in
data/.git, so the group keeps a full, revertable history with a readable delta.
The public repo never sees any of it — data/ is gitignored there.

Authorship is passed through from the web request (a free-text "who"), while
the committer identity stays the repo's configured Ihsara identity.
"""

from __future__ import annotations

import subprocess

from .config import DATA_DIR


class GitError(RuntimeError):
    pass


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", str(DATA_DIR), *args],
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def is_repo() -> bool:
    return (DATA_DIR / ".git").exists()


def ensure_repo() -> None:
    if is_repo():
        return
    _git("init")
    _git("config", "user.name", "Ihsara")
    _git("config", "user.email", "ihsara@users.noreply.github.com")


def _sanitize_who(who: str | None) -> str:
    who = (who or "").strip()
    # Keep it a single clean line; no addresses, no control chars.
    who = "".join(c for c in who if c.isprintable())[:80]
    return who or "web"


def commit(paths: list[str], message: str, who: str | None = None) -> str | None:
    """Stage `paths` (relative to data/) and commit. Returns the short hash, or
    None if there was nothing to commit."""
    ensure_repo()
    _git("add", "--", *paths)
    status = _git("status", "--porcelain", "--", *paths).stdout.strip()
    if not status:
        return None
    actor = _sanitize_who(who)
    full = f"{message}\n\nvia web by: {actor}"
    _git("-c", "commit.gpgsign=false", "commit", "-m", full, "--", *paths)
    return _git("rev-parse", "--short", "HEAD").stdout.strip()


def history(path: str, limit: int = 20) -> list[dict]:
    """Recent commits touching `path` (relative to data/)."""
    if not is_repo():
        return []
    fmt = "%h%x1f%an%x1f%ad%x1f%s"
    proc = _git(
        "log",
        f"-n{limit}",
        f"--pretty=format:{fmt}",
        "--date=short",
        "--",
        path,
        check=False,
    )
    out = []
    for line in proc.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            out.append(
                {"hash": parts[0], "author": parts[1], "date": parts[2], "subject": parts[3]}
            )
    return out


def last_diff(path: str) -> str:
    """Unified diff of `path` from the previous commit to the latest (readable
    delta for CSV mirrors). Empty string if not available."""
    if not is_repo():
        return ""
    proc = _git("diff", "HEAD~1", "HEAD", "--", path, check=False)
    return proc.stdout
