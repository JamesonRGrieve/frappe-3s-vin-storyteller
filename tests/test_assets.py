# SPDX-License-Identifier: AGPL-3.0-or-later
"""Asset cache-busting: the app checkout's commit, read from .git without running git."""

import subprocess
from types import FunctionType

from vin_storyteller import __version__
from vin_storyteller.assets import APP_ROOT, git_commit, vin_storyteller_asset_version


def init(path):
	subprocess.run(["git", "init", "-q", str(path)], check=True)
	(path / "f").write_text("x")
	subprocess.run(["git", "-C", str(path), "add", "f"], check=True)
	subprocess.run(
		["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "m"],
		check=True,
	)
	return subprocess.run(
		["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True
	).stdout.strip()


def test_reads_the_branch_commit(tmp_path):
	assert git_commit(tmp_path) is None
	head = init(tmp_path)
	assert git_commit(tmp_path) == head


def test_reads_a_packed_ref(tmp_path):
	head = init(tmp_path)
	subprocess.run(["git", "-C", str(tmp_path), "pack-refs", "--all", "--prune"], check=True)
	assert git_commit(tmp_path) == head


def test_reads_a_detached_head(tmp_path):
	head = init(tmp_path)
	subprocess.run(["git", "-C", str(tmp_path), "checkout", "-q", "--detach"], check=True)
	assert git_commit(tmp_path) == head


def test_the_jinja_method_is_a_plain_function_named_for_the_template():
	"""Frappe's jinja hook registers only plain functions, under their own name."""
	assert isinstance(vin_storyteller_asset_version, FunctionType)
	version = vin_storyteller_asset_version()
	assert version == (git_commit(APP_ROOT) or __version__)[:7] or version == __version__


def test_every_template_asset_carries_the_version():
	import re

	for name in ("codes.html", "storyteller.html"):
		text = (APP_ROOT / "vin_storyteller" / "templates" / "includes" / name).read_text()
		urls = re.findall(r'"(/assets/vin_storyteller/[^"]+)"', text)
		assert urls and all(u.endswith("?v={{ vin_storyteller_asset_version() }}") for u in urls), name
