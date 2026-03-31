"""
repo_harvester.py
-----------------
Stage 1 – Discover candidate Java repositories from GitHub.

Queries the GitHub Search API for recent, mid-sized Java repos and filters
out obvious non-candidates (tutorials, Android-only, demos).
"""

from __future__ import annotations

import logging
import time
import urllib.parse
import urllib.request
import json
import os
from pathlib import Path
from typing import Iterator, Optional

import git  # gitpython

from refagent.benchmark.design_patterns.models import RepoCandidate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

_GH_TOKEN: Optional[str] = os.environ.get("GH_TOKEN")

_EXCLUDE_TOPICS = {"android", "tutorial", "demo", "example", "sample", "workshop"}
_EXCLUDE_NAME_FRAGMENTS = {"tutorial", "demo", "example", "sample", "starter", "workshop"}


def _gh_api_get(url: str) -> dict:
    """Make an authenticated GET request to the GitHub API and return parsed JSON."""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    if _GH_TOKEN:
        req.add_header("Authorization", f"Bearer {_GH_TOKEN}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _is_excluded(repo: dict) -> bool:
    """Return True if a raw GitHub repo dict should be skipped."""
    name_lower = repo["name"].lower()
    if any(frag in name_lower for frag in _EXCLUDE_NAME_FRAGMENTS):
        return True
    topics = set(repo.get("topics", []))
    if topics & _EXCLUDE_TOPICS:
        return True
    return False


# ---------------------------------------------------------------------------
# RepoHarvester
# ---------------------------------------------------------------------------

class RepoHarvester:
    """
    Discovers candidate Java repos via the GitHub Search API.

    Parameters
    ----------
    min_stars, max_stars : int
        Star-count window. Mid-size repos (500–5000) tend to have rich history
        without patterns being ancient.
    pushed_after : str
        ISO date string (YYYY-MM-DD).  Only repos pushed after this date.
    max_repos : int
        Hard cap on the number of repos returned.
    """

    def __init__(
        self,
        min_stars: int = 500,
        max_stars: int = 5000,
        pushed_after: str = "2023-01-01",
        max_repos: int = 100,
    ) -> None:
        self.min_stars    = min_stars
        self.max_stars    = max_stars
        self.pushed_after = pushed_after
        self.max_repos    = max_repos

    def discover(self) -> list[RepoCandidate]:
        """Query GitHub and return a deduplicated list of RepoCandidate objects."""
        candidates: list[RepoCandidate] = []
        seen: set[str] = set()

        for page in self._search_pages():
            for item in page.get("items", []):
                full_name = item["full_name"]
                if full_name in seen:
                    continue
                if _is_excluded(item):
                    logger.debug("Skipping excluded repo: %s", full_name)
                    continue
                seen.add(full_name)
                owner, name = full_name.split("/", 1)
                candidates.append(
                    RepoCandidate(
                        owner=owner,
                        name=name,
                        stars=item["stargazers_count"],
                        pushed_at=item["pushed_at"],
                        clone_url=item["clone_url"],
                    )
                )
                if len(candidates) >= self.max_repos:
                    return candidates
            time.sleep(1)  # be polite to the API

        return candidates

    def _search_pages(self) -> Iterator[dict]:
        """Yield raw GitHub search result pages."""
        base = "https://api.github.com/search/repositories"
        query = (
            f"language:java"
            f" stars:{self.min_stars}..{self.max_stars}"
            f" pushed:>{self.pushed_after}"
            f" fork:false"
        )
        page = 1
        while True:
            params = urllib.parse.urlencode({
                "q": query,
                "sort": "updated",
                "order": "desc",
                "per_page": 30,
                "page": page,
            })
            url = f"{base}?{params}"
            logger.info("Fetching search page %d: %s", page, url)
            try:
                data = _gh_api_get(url)
            except Exception as exc:
                logger.error("GitHub API error on page %d: %s", page, exc)
                break

            yield data

            # GitHub caps search results at 1 000 items (33 pages × 30)
            if not data.get("items") or page >= 33:
                break
            page += 1


# ---------------------------------------------------------------------------
# Repo cloner
# ---------------------------------------------------------------------------

class RepoCloner:
    """
    Clones (or updates) repos to a local directory.

    Parameters
    ----------
    base_dir : Path
        Directory under which each repo is cloned as ``{owner}__{name}/``.
    shallow_since : str | None
        If set, perform a shallow clone with ``--shallow-since=<date>``.
        Speeds up cloning for history-mining, but RefactoringMiner needs
        full history – set to None for full clones.
    """

    def __init__(self, base_dir: Path, shallow_since: Optional[str] = None) -> None:
        self.base_dir     = base_dir
        self.shallow_since = shallow_since
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def clone_or_update(self, repo: RepoCandidate) -> RepoCandidate:
        """
        Clone ``repo`` if not already present, or ``git pull`` if it is.
        Returns an updated RepoCandidate with ``local_path`` populated.
        """
        dest = self.base_dir / f"{repo.owner}__{repo.name}"

        if dest.exists():
            logger.info("Repo already cloned, pulling: %s", dest)
            try:
                git.Repo(dest).remotes.origin.pull()
            except Exception as exc:
                logger.warning("Pull failed for %s: %s", dest, exc)
        else:
            logger.info("Cloning %s -> %s", repo.clone_url, dest)
            kwargs: dict = {}
            if self.shallow_since:
                kwargs["shallow_since"] = self.shallow_since
            git.Repo.clone_from(repo.clone_url, dest, **kwargs)

        return repo.model_copy(update={"local_path": dest})
