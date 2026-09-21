import json
import os
import re
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

USER_AGENT = "SimpleUpdater/1.0 (Windows NT 6.1; Win64; x64)"


class GitRepoInfo:
    def __init__(self, owner: str, repo: str, original_url: str):
        self.owner = owner
        self.repo = repo
        self.original_url = original_url

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_git_url(url: str) -> Optional[GitRepoInfo]:
    """
    Parses a GitHub URL into owner and repo name.
    Supports:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - git@github.com:owner/repo.git
    - owner/repo shorthand
    """
    url = url.strip()
    if not url:
        return None

    # Shorthand: owner/repo
    shorthand_match = re.match(r"^([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)$", url)
    if shorthand_match and not url.startswith("http"):
        return GitRepoInfo(shorthand_match.group(1), shorthand_match.group(2).rstrip(".git"), f"https://github.com/{url}")

    # HTTPS GitHub URL
    http_match = re.match(r"^https?://(?:www\.)?github\.com/([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+?)(?:\.git)?(?:/.*)?$", url, re.IGNORECASE)
    if http_match:
        return GitRepoInfo(http_match.group(1), http_match.group(2), url)

    # SSH GitHub URL
    ssh_match = re.match(r"^git@github\.com:([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+?)(?:\.git)?$", url, re.IGNORECASE)
    if ssh_match:
        return GitRepoInfo(ssh_match.group(1), ssh_match.group(2), url)

    return None


class GitHubClient:
    def __init__(self, repo_info: GitRepoInfo):
        self.repo_info = repo_info
        self.base_api = f"https://api.github.com/repos/{self.repo_info.owner}/{self.repo_info.repo}"

    def _api_get(self, endpoint: str = "") -> Any:
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            url = endpoint
        elif endpoint.startswith("/"):
            url = f"{self.base_api}{endpoint}"
        elif endpoint:
            url = f"{self.base_api}/{endpoint}"
        else:
            url = self.base_api

        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github.v3+json"
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise RuntimeError(f"GitHub API Error ({e.code}): {e.reason}")
        except Exception as e:
            raise RuntimeError(f"Network error connecting to GitHub: {str(e)}")

    def get_repo_details(self) -> Dict[str, Any]:
        data = self._api_get("")
        if not data:
            raise RuntimeError(f"Repository {self.repo_info.full_name} not found or private.")
        return {
            "name": data.get("name", self.repo_info.repo),
            "description": data.get("description", ""),
            "default_branch": data.get("default_branch", "main"),
            "html_url": data.get("html_url", self.repo_info.original_url),
        }

    def get_latest_release(self) -> Optional[Dict[str, Any]]:
        """
        Fetches the latest release, including assets.
        Returns None if no release exists.
        """
        try:
            rel = self._api_get("/releases/latest")
            if not rel:
                # Try getting releases list if latest tag isn't marked "latest"
                releases = self._api_get("/releases")
                if releases and isinstance(releases, list) and len(releases) > 0:
                    rel = releases[0]
                else:
                    return None

            assets = []
            for a in rel.get("assets", []):
                assets.append({
                    "name": a.get("name"),
                    "size": a.get("size", 0),
                    "download_url": a.get("browser_download_url"),
                    "content_type": a.get("content_type", ""),
                })

            # Format published date
            pub_date = rel.get("published_at") or rel.get("created_at") or ""
            return {
                "tag_name": rel.get("tag_name", ""),
                "name": rel.get("name") or rel.get("tag_name", "Release"),
                "published_at": pub_date,
                "body": rel.get("body", ""),
                "assets": assets,
                "tarball_url": rel.get("tarball_url"),
                "zipball_url": rel.get("zipball_url"),
            }
        except Exception:
            return None

    def get_latest_commit(self, branch: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetches the latest commit on the branch (or default branch).
        """
        endpoint = f"/commits?per_page=1"
        if branch:
            endpoint += f"&sha={urllib.parse.quote(branch)}"
        
        commits = self._api_get(endpoint)
        if not commits or not isinstance(commits, list) or len(commits) == 0:
            raise RuntimeError(f"No commits found for {self.repo_info.full_name}")

        latest = commits[0]
        sha = latest.get("sha", "")
        short_sha = sha[:7]
        commit_info = latest.get("commit", {})
        message = commit_info.get("message", "").split("\n")[0]
        committer = commit_info.get("committer", {}) or commit_info.get("author", {})
        date_str = committer.get("date", "")

        zip_url = f"https://github.com/{self.repo_info.owner}/{self.repo_info.repo}/archive/{sha}.zip"

        return {
            "sha": sha,
            "short_sha": short_sha,
            "name": f"commit {short_sha}: {message[:40]}",
            "message": message,
            "date": date_str,
            "zip_url": zip_url,
        }

    def get_raw_file_url(self, file_path: str, ref: str) -> str:
        """
        Constructs a URL to download a raw single file from GitHub at a specific ref/branch/commit.
        """
        return f"https://raw.githubusercontent.com/{self.repo_info.owner}/{self.repo_info.repo}/{ref}/{file_path}"
