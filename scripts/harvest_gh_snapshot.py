#!/usr/bin/env python3
"""harvest_gh_snapshot.py — Article XXIV (Static Data Covenant, kody-w/RAR
CONSTITUTION.md) compliance for this seed.

classic.html is self-referential: every planted copy of this page derives
its OWN owner/repo from location.host + location.pathname at view time, then
used to call the GitHub REST API live, unauthenticated, from the visitor's
browser, for:
  - repo metadata           (forks_count, etc.)
  - recent commits          (mutation log, egg-seal provenance)
  - the agents/ contents listing (agent chips, custom-agent count)
  - (fallback path only) the PARENT seed's same three signals + its raw
    memory.json, for older seeds planted before lineage_snapshot was baked
    into rappid.json at plant time.

This script is the CI harvester: it runs with repo-scoped GITHUB_TOKEN auth
(never shipped to the browser), fetches those same endpoints ONCE, and
writes the responses verbatim (same JSON shape as the API) into state/*.json
so the page can read committed data instead of calling api.github.com.

Writes:
  state/self-repo.json          <- GET /repos/{owner}/{repo}
  state/self-commits.json       <- GET /repos/{owner}/{repo}/commits?per_page=10
  state/self-agents.json        <- GET /repos/{owner}/{repo}/contents/agents
  state/parent-lineage.json     <- bundle of the same three shapes + raw
                                    memory.json text for rappid.json's
                                    parent_repo, or JSON `null` if this seed
                                    has no parent_repo (or already carries a
                                    baked-in lineage_snapshot, in which case
                                    the live-fetch fallback path in
                                    classic.html never runs anyway).

Self owner/repo comes from $GITHUB_REPOSITORY (set automatically in GitHub
Actions) with a `git remote` fallback for local/manual runs.
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
API = "https://api.github.com"


def _headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "pkstop-harvester"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _get(url):
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"message": str(e), "status": str(e.code)}
    except Exception as e:
        return {"message": str(e), "status": "error"}


def _get_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "pkstop-harvester"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8")
    except Exception as e:
        return f"404: {e}"


def _self_owner_repo():
    env = os.environ.get("GITHUB_REPOSITORY")  # "owner/repo"
    if env and "/" in env:
        owner, repo = env.split("/", 1)
        return owner, repo
    # Local/manual fallback: parse origin remote.
    try:
        url = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
        if m:
            return m.group(1), m.group(2)
    except Exception:
        pass
    return None, None


def main():
    owner, repo = _self_owner_repo()
    if not owner or not repo:
        print("✗ could not determine owner/repo (no $GITHUB_REPOSITORY, no origin remote)")
        return 2

    STATE.mkdir(parents=True, exist_ok=True)

    self_repo = _get(f"{API}/repos/{owner}/{repo}")
    (STATE / "self-repo.json").write_text(json.dumps(self_repo, indent=1) + "\n")

    self_commits = _get(f"{API}/repos/{owner}/{repo}/commits?per_page=10")
    (STATE / "self-commits.json").write_text(json.dumps(self_commits, indent=1) + "\n")

    self_agents = _get(f"{API}/repos/{owner}/{repo}/contents/agents")
    (STATE / "self-agents.json").write_text(json.dumps(self_agents, indent=1) + "\n")

    print(f"✓ self snapshot for {owner}/{repo}: "
          f"repo={'ok' if 'id' in self_repo else self_repo.get('message')}, "
          f"commits={len(self_commits) if isinstance(self_commits, list) else self_commits.get('message')}, "
          f"agents={len(self_agents) if isinstance(self_agents, list) else self_agents.get('message')}")

    # Parent lineage — only needed by classic.html's legacy fallback path,
    # which itself only runs when rappid.json has parent_repo but no baked
    # lineage_snapshot. Harvest it anyway so the fallback never needs the
    # live API even for older seeds.
    parent_bundle = None
    rappid_path = ROOT / "rappid.json"
    if rappid_path.exists():
        try:
            rappid = json.loads(rappid_path.read_text())
        except Exception:
            rappid = {}
        parent_repo_url = rappid.get("parent_repo")
        m = re.search(r"github\.com/([^/]+)/([^/.]+?)(?:\.git)?/?$", parent_repo_url or "")
        if m:
            p_owner, p_repo = m.group(1), m.group(2)
            parent_bundle = {
                "schema": "pkstop-parent-lineage/1",
                "parent_repo": parent_repo_url,
                "repo": _get(f"{API}/repos/{p_owner}/{p_repo}"),
                "commits": _get(f"{API}/repos/{p_owner}/{p_repo}/commits?per_page=6"),
                "agentsContents": _get(f"{API}/repos/{p_owner}/{p_repo}/contents/agents"),
                "memoryText": _get_text(
                    f"https://raw.githubusercontent.com/{p_owner}/{p_repo}/main/.brainstem_data/memory.json"),
            }
            print(f"✓ parent lineage snapshot for {p_owner}/{p_repo}")
        else:
            print("· no parent_repo on rappid.json — parent-lineage.json will be null")

    (STATE / "parent-lineage.json").write_text(json.dumps(parent_bundle, indent=1) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
