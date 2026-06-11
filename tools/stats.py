"""Adoption stats: HF model downloads + GitHub repo signals. Run: ./ohmatic stats"""

import json
import os
import urllib.request

HF_REPOS = [
    ("model", "VittoriaLanzo/Ohmatic-Qwen3-8B"),
    ("model", "VittoriaLanzo/ohmatic-t5-normalizer"),
    ("model", "VittoriaLanzo/ohmatic-qwen3-adapter"),
    ("model", "VittoriaLanzo/ohmatic-merged-base"),
]
GH_REPO = "VittoriaLanzo/Ohmatic"


def _get(url: str, token: str = "") -> dict:
    req = urllib.request.Request(url, headers=(
        {"Authorization": f"Bearer {token}"} if token else {}))
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except Exception as exc:
        return {"_error": str(exc)[:80]}


def main() -> None:
    hf_token = os.environ.get("HF_TOKEN", "")
    print(f"{'repo':45s} {'downloads':>9s} {'likes':>6s}")
    print("-" * 64)
    for kind, repo in HF_REPOS:
        d = _get(f"https://huggingface.co/api/{kind}s/{repo}", hf_token)
        if "_error" in d:
            print(f"{repo:45s} {'?':>9s} {'?':>6s}  ({d['_error']})")
        else:
            private = " (private)" if d.get("private") else ""
            print(f"{repo:45s} {d.get('downloads', 0):>9d} {d.get('likes', 0):>6d}{private}")
    g = _get(f"https://api.github.com/repos/{GH_REPO}", os.environ.get("GITHUB_TOKEN", ""))
    if "_error" not in g:
        print(f"\ngithub {GH_REPO}: {g.get('stargazers_count', 0)} stars, "
              f"{g.get('forks_count', 0)} forks, {g.get('open_issues_count', 0)} open issues")
    else:
        print(f"\ngithub: {g['_error']}")


if __name__ == "__main__":
    main()
