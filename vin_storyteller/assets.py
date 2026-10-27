# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cache-busting for the app's static assets: templates add ``?v=<version>`` to every ``/assets/vin_storyteller/...``
URL, so a CDN that caches assets for hours (Cloudflare) serves new code as soon as it is deployed.

The version is the app checkout's git commit (short), read from ``.git`` without running git; outside a checkout it
is the package version. No Frappe import in the pure part.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from vin_storyteller import __version__

APP_ROOT = Path(__file__).resolve().parent.parent  # the app checkout (apps/vin_storyteller)


def git_commit(root: Path) -> str | None:
	"""The commit ``root``'s checkout is on, from ``.git/HEAD`` (a branch ref, a packed ref, or a detached hash)."""
	git = root / ".git"
	if git.is_file():  # a worktree: "gitdir: <path>"
		text = git.read_text().strip()
		if not text.startswith("gitdir:"):
			return None
		git = (root / text.split(":", 1)[1].strip()).resolve()
	try:
		head = (git / "HEAD").read_text().strip()
	except OSError:
		return None
	if not head.startswith("ref:"):
		return head or None
	ref = head.split(":", 1)[1].strip()
	for base in (git, _common_dir(git)):
		path = base / ref
		if path.is_file():
			return path.read_text().strip() or None
		packed = base / "packed-refs"
		if packed.is_file():
			for line in packed.read_text().splitlines():
				if line.endswith(f" {ref}"):
					return line.split(" ", 1)[0]
	return None


def _common_dir(git: Path) -> Path:
	common = git / "commondir"
	return (git / common.read_text().strip()).resolve() if common.is_file() else git


@cache
def asset_version() -> str:
	"""The version query value for this app's assets: the short commit, else the package version."""
	commit = git_commit(APP_ROOT)
	return commit[:7] if commit else __version__


def vin_storyteller_asset_version() -> str:
	"""jinja method (hooks.py): Frappe registers a plain function under its own name, so this is the template's."""
	return asset_version()
