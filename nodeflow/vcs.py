"""Project-level Git integration (GitPython).

`GitManager` wraps the operations exposed by the GUI's Git controls — init,
status, commit, branch, checkout, history, pull, push — and operates on the
**entire project directory**. Kept GUI-free so it is fully unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import git
from git import GitCommandError, InvalidGitRepositoryError, Repo


class GitError(RuntimeError):
    """Raised for any Git operation failure (wraps GitPython errors)."""


@dataclass
class CommitInfo:
    sha: str
    short_sha: str
    author: str
    email: str
    date: str
    message: str


class GitManager:
    """Git operations scoped to one project directory."""

    def __init__(self, repo_dir: str | Path) -> None:
        self.repo_dir = Path(repo_dir)
        self._repo: Repo | None = None

    # -- construction -----------------------------------------------------
    @classmethod
    def open(cls, repo_dir: str | Path) -> GitManager:
        mgr = cls(repo_dir)
        if not mgr.is_repo():
            raise GitError(f"{repo_dir} is not a Git repository")
        return mgr

    @classmethod
    def init(cls, repo_dir: str | Path) -> GitManager:
        repo_dir = Path(repo_dir)
        repo_dir.mkdir(parents=True, exist_ok=True)
        mgr = cls(repo_dir)
        if not mgr.is_repo():
            Repo.init(repo_dir)
        return mgr

    @property
    def repo(self) -> Repo:
        if self._repo is None:
            try:
                self._repo = Repo(self.repo_dir)
            except InvalidGitRepositoryError as exc:
                raise GitError(f"not a Git repository: {self.repo_dir}") from exc
        return self._repo

    def is_repo(self) -> bool:
        try:
            Repo(self.repo_dir)
            return True
        except (InvalidGitRepositoryError, git.NoSuchPathError):
            return False

    # -- status -----------------------------------------------------------
    def has_commits(self) -> bool:
        try:
            return bool(self.repo.head.is_valid())
        except Exception:
            return False

    def current_branch(self) -> str:
        try:
            return self.repo.active_branch.name
        except (TypeError, ValueError):
            return "(detached)"

    def status(self) -> dict:
        repo = self.repo
        return {
            "branch": self.current_branch() if self.has_commits() else "(no commits)",
            "dirty": repo.is_dirty(untracked_files=True),
            "staged": [d.a_path for d in repo.index.diff("HEAD")] if self.has_commits() else [],
            "modified": [d.a_path for d in repo.index.diff(None)],
            "untracked": repo.untracked_files,
        }

    # -- commit -----------------------------------------------------------
    def stage_all(self) -> None:
        self.repo.git.add(A=True)

    def commit(self, message: str, *, add_all: bool = True) -> str:
        if not message or not message.strip():
            raise GitError("commit message must not be empty")
        if add_all:
            self.stage_all()
        try:
            commit = self.repo.index.commit(message)
        except Exception as exc:  # nothing to commit, etc.
            raise GitError(f"commit failed: {exc}") from exc
        return commit.hexsha

    # -- branches ---------------------------------------------------------
    def branches(self) -> list[str]:
        return sorted(h.name for h in self.repo.heads)

    def create_branch(self, name: str, *, checkout: bool = True) -> None:
        if not self.has_commits():
            raise GitError("cannot branch before the first commit")
        try:
            head = self.repo.create_head(name)
        except GitCommandError as exc:
            raise GitError(f"could not create branch {name!r}: {exc}") from exc
        if checkout:
            head.checkout()

    def checkout(self, name: str) -> None:
        try:
            self.repo.git.checkout(name)
        except GitCommandError as exc:
            raise GitError(f"could not checkout {name!r}: {exc}") from exc

    # -- history ----------------------------------------------------------
    def history(self, limit: int = 20) -> list[CommitInfo]:
        if not self.has_commits():
            return []
        commits = []
        for c in self.repo.iter_commits(max_count=limit):
            commits.append(
                CommitInfo(
                    sha=c.hexsha,
                    short_sha=c.hexsha[:8],
                    author=c.author.name or "",
                    email=c.author.email or "",
                    date=datetime.fromtimestamp(c.committed_date, tz=UTC).isoformat(),
                    message=c.message.strip(),
                )
            )
        return commits

    # -- remotes ----------------------------------------------------------
    def remotes(self) -> list[str]:
        return [r.name for r in self.repo.remotes]

    def add_remote(self, name: str, url: str) -> None:
        if name in self.remotes():
            self.repo.delete_remote(name)
        self.repo.create_remote(name, url)

    def push(self, remote: str = "origin", branch: str | None = None, *, set_upstream: bool = True) -> None:
        if remote not in self.remotes():
            raise GitError(f"no remote named {remote!r}")
        branch = branch or self.current_branch()
        try:
            if set_upstream:
                self.repo.git.push("--set-upstream", remote, branch)
            else:
                self.repo.git.push(remote, branch)
        except GitCommandError as exc:
            raise GitError(f"push failed: {exc}") from exc

    def pull(self, remote: str = "origin", branch: str | None = None) -> None:
        if remote not in self.remotes():
            raise GitError(f"no remote named {remote!r}")
        branch = branch or self.current_branch()
        try:
            self.repo.git.pull(remote, branch)
        except GitCommandError as exc:
            raise GitError(f"pull failed: {exc}") from exc
