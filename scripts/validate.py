#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Jakub Travnik <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Validate the git-provider inventory tree under ``demo-inventory/``.

Applies the same fail-closed rules Hegemony's git inventory plugin enforces at
runtime, so the published source of truth cannot silently drift: schema_version
1, ``external_id`` equal to the file stem, the fields the plugin schema
requires (non-blank ``name`` on sites and devices, ``mgmt_host`` on devices),
resolved site references, and templated (never literal) access-config refs.
Fields the plugin treats as optional (``mgmt_port``, ``platform``, ``vendor``,
``model``, ``site``, ``role``) stay optional here too.

Ported from the ``hegemony-demo-data`` repository's ``scripts/validate.py``,
which guarded this tree before it moved into its own repository.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
# Mirrors the platform's access-ref validation (validate_access_config in
# apps/api/services/inventory/validation.py): a ref must be one full
# protected-template call — {{ secret(...) }} / {{ env(...) }} /
# {{ file(...) }} — or one {{ vars.NAME }} reference, nothing more.
TEMPLATE_CALL_RE = re.compile(r"^\s*\{\{\s*(secret|env|file)\s*\(.*\)\s*\}\}\s*$")
TEMPLATE_VAR_RE = re.compile(r"^\s*\{\{\s*vars\.[A-Za-z_][A-Za-z0-9_]*\s*\}\}\s*$")


def _derive_site_path(sites_root: Path, site_file: Path) -> str:
    """Derive a git-inventory site path from a site file's location.

    Mirrors the git inventory plugin: a file whose stem equals its parent
    directory name identifies that directory (``sites/emea/emea.yaml`` ->
    ``emea``); any other file is a leaf site under its directory
    (``sites/emea/nl/ams01.yaml`` -> ``emea/nl/ams01``).
    """
    rel_dir = site_file.parent.relative_to(sites_root)
    dir_path = rel_dir.as_posix()
    if site_file.stem == site_file.parent.name:
        return dir_path
    return f"{dir_path}/{site_file.stem}" if dir_path != "." else site_file.stem


def _check_access_refs_templated(location: Any, access_config: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(access_config, dict):
        return errors
    for section in access_config.values():
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            if not (isinstance(key, str) and key.endswith("_ref")) or value is None:
                continue
            if not isinstance(value, str) or not (
                TEMPLATE_CALL_RE.match(value) or TEMPLATE_VAR_RE.match(value)
            ):
                errors.append(
                    f"{location}: {key} must be exactly one template reference like"
                    " '{{ secret(...) }}', '{{ env(...) }}', '{{ file(...) }}', or"
                    " '{{ vars.NAME }}' — never a literal or partial value"
                )
    return errors


def validate_inventory_tree(root: Path) -> list[str]:
    """Validate the inventory tree, returning a list of error strings."""
    errors: list[str] = []
    if not root.is_dir():
        return [f"{root}: inventory tree is missing"]

    site_paths: set[str] = set()
    sites_root = root / "sites"
    site_files = sorted(sites_root.rglob("*.y*ml")) if sites_root.is_dir() else []
    for site_file in site_files:
        rel = site_file.relative_to(root)
        try:
            doc = yaml.safe_load(site_file.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"{rel}: invalid YAML: {exc}")
            continue
        except (OSError, UnicodeError) as exc:
            errors.append(f"{rel}: unreadable file: {exc}")
            continue
        if not isinstance(doc, dict):
            errors.append(f"{rel}: expected a YAML mapping")
            continue
        if doc.get("schema_version") != 1:
            errors.append(f"{rel}: site schema_version must be 1")
        if doc.get("kind") != "site":
            errors.append(f"{rel}: kind must be 'site'")
        if doc.get("external_id") != site_file.stem:
            errors.append(
                f"{rel}: external_id {doc.get('external_id')!r} must equal file stem {site_file.stem!r}"
            )
        name = doc.get("name")
        if not (isinstance(name, str) and name.strip()):
            errors.append(f"{rel}: site is missing a non-blank name")
        site_paths.add(_derive_site_path(sites_root, site_file))
    if not site_files:
        errors.append(f"{root}: no site files found under sites/")

    devices_root = root / "devices"
    device_files = sorted(devices_root.rglob("*.y*ml")) if devices_root.is_dir() else []
    for device_file in device_files:
        rel = device_file.relative_to(root)
        try:
            doc = yaml.safe_load(device_file.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"{rel}: invalid YAML: {exc}")
            continue
        except (OSError, UnicodeError) as exc:
            errors.append(f"{rel}: unreadable file: {exc}")
            continue
        if not isinstance(doc, dict):
            errors.append(f"{rel}: expected a YAML mapping")
            continue
        if doc.get("schema_version") != 1:
            errors.append(f"{rel}: device schema_version must be 1")
        if doc.get("kind") != "device":
            errors.append(f"{rel}: kind must be 'device'")
        if doc.get("external_id") != device_file.stem:
            errors.append(
                f"{rel}: external_id {doc.get('external_id')!r} must equal file stem {device_file.stem!r}"
            )
        name = doc.get("name")
        if not (isinstance(name, str) and name.strip()):
            errors.append(f"{rel}: device is missing a non-blank name")
        if not doc.get("mgmt_host"):
            errors.append(f"{rel}: device is missing mgmt_host")
        site = doc.get("site")
        if site is not None and site not in site_paths:
            errors.append(f"{rel}: references unknown site {site!r}")
        errors.extend(_check_access_refs_templated(rel, doc.get("access_config")))
    if not device_files:
        errors.append(f"{root}: no device files found under devices/")

    return errors


def main() -> int:
    errors = validate_inventory_tree(ROOT / "demo-inventory")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"validated {ROOT / 'demo-inventory'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
