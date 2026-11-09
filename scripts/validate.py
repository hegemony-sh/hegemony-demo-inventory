#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-2026 Rexonix s.r.o.
# SPDX-FileContributor: Jakub Travnik <jakub.travnik@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Validate the Git inventory tree under ``inventory/``.

Applies the same fail-closed rules Hegemony's Git inventory plugin enforces at
runtime, so a broken tree fails here instead of failing the demo's inventory
sync. Sites and devices: schema_version 1, ``external_id`` equal to the file
stem, the fields the plugin schema requires (non-blank ``name`` on sites and
devices, ``mgmt_host`` on devices), no fields the plugin schema does not know,
resolved site references, and templated (never literal) access-config refs.
Fields the plugin treats as optional (``mgmt_port``, ``platform``,
``attributes``, ``site``, ``role``) stay optional here too.

Object types (``object-types/<id>.yaml``) and their records
(``objects/<id>/<external_id>.yaml``, read by plugin 0.5.0 and later): the id
and external id equal the file stem, no fields the plugin does not know, a
``field_schema`` within the plugin's JSON Schema subset, a record in the folder
of a declared type, attributes that match that type's ``field_schema``, and
relationships that name declared relationships and existing records.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

ROOT = Path(__file__).resolve().parents[1]
# Mirrors the platform's access-ref validation (validate_access_config in
# apps/api/services/inventory/validation.py): a ref must be one full
# protected-template call — {{ secret(...) }} / {{ env(...) }} /
# {{ file(...) }} — or one {{ vars.NAME }} reference, nothing more.
TEMPLATE_CALL_RE = re.compile(r"^\s*\{\{\s*(secret|env|file)\s*\(.*\)\s*\}\}\s*$")
TEMPLATE_VAR_RE = re.compile(r"^\s*\{\{\s*vars\.[A-Za-z_][A-Za-z0-9_]*\s*\}\}\s*$")

# The keys the git inventory plugin's schema v1 accepts. Its models forbid
# anything else, and one unknown key fails the whole provider sync -- which is
# how top-level ``vendor``/``model`` broke the demo when the plugin moved them
# under ``attributes``. Mirrors GitInventorySiteV1, GitInventoryDeviceV1,
# GitInventoryAccessConfigV1 and GitInventoryJumpHostV1 in
# hegemony-inventory-plugins (plugins/inventory_git/.../inventory_schema.py).
SITE_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "external_id",
        "name",
        "description",
        "location",
        "tags",
        "custom_fields",
    }
)
DEVICE_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "external_id",
        "name",
        "mgmt_host",
        "mgmt_port",
        "platform",
        "attributes",
        "site",
        "role",
        "tags",
        "access_config",
        "custom_fields",
    }
)
ACCESS_CONFIG_KEYS = frozenset({"ssh", "enable", "jump_host"})
JUMP_HOST_KEYS = frozenset({"host", "port", "username_ref", "password_ref", "private_key_ref"})


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


def _check_known_keys(location: Any, doc: dict[str, Any], allowed: frozenset[str]) -> list[str]:
    unknown = sorted(str(key) for key in doc if key not in allowed)
    if not unknown:
        return []
    return [f"{location}: unknown field(s) {', '.join(unknown)}; the plugin schema rejects them"]


def _check_access_config_keys(location: Any, access_config: Any) -> list[str]:
    if access_config is None:
        return []
    if not isinstance(access_config, dict):
        return [f"{location}: access_config must be a mapping"]
    errors = _check_known_keys(f"{location} access_config", access_config, ACCESS_CONFIG_KEYS)
    jump_host = access_config.get("jump_host")
    if isinstance(jump_host, dict):
        errors.extend(
            _check_known_keys(f"{location} access_config.jump_host", jump_host, JUMP_HOST_KEYS)
        )
    return errors


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
        errors.extend(_check_known_keys(rel, doc, SITE_KEYS))
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
        errors.extend(_check_known_keys(rel, doc, DEVICE_KEYS))
        if not isinstance(doc.get("attributes", {}), dict):
            errors.append(f"{rel}: attributes must be a mapping")
        errors.extend(_check_access_config_keys(rel, doc.get("access_config")))
        site = doc.get("site")
        if site is not None and site not in site_paths:
            errors.append(f"{rel}: references unknown site {site!r}")
        errors.extend(_check_access_refs_templated(rel, doc.get("access_config")))
    if not device_files:
        errors.append(f"{root}: no device files found under devices/")

    errors.extend(_validate_objects(root))
    return errors


def _load(root: Path, path: Path, errors: list[str]) -> dict[str, Any] | None:
    rel = path.relative_to(root)
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        errors.append(f"{rel}: invalid YAML: {exc}")
        return None
    except (OSError, UnicodeError) as exc:
        errors.append(f"{rel}: unreadable file: {exc}")
        return None
    if not isinstance(doc, dict):
        errors.append(f"{rel}: expected a YAML mapping")
        return None
    if doc.get("schema_version") != 1:
        errors.append(f"{rel}: schema_version must be 1")
    return doc


# The keys and the JSON Schema subset the plugin's generic loader accepts.
# Mirrors TypeDefinition, RelationshipDefinition, Record, Relationship and
# _KEYWORDS in hegemony-inventory-plugins (plugins/inventory_git/.../generic.py).
OBJECT_TYPE_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "id",
        "display_name",
        "plural",
        "description",
        "group",
        "field_schema",
        "relationships",
        "ui",
        "filters",
    }
)
RELATIONSHIP_DEFINITION_KEYS = frozenset(
    {"rel", "target_object_type", "label", "many", "required"}
)
OBJECT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "object_type",
        "external_id",
        "name",
        "display_name",
        "attributes",
        "relationships",
    }
)
RELATIONSHIP_KEYS = frozenset({"rel", "target_object_type", "target_external_id"})
SCHEMA_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "minProperties",
        "maxProperties",
        "title",
        "description",
    }
)


def _check_schema_subset(location: Any, schema: Any, path: str = "field_schema") -> list[str]:
    """The plugin's own schema rules on top of JSON Schema: a bounded keyword set."""
    if not isinstance(schema, dict):
        return [f"{location}: {path} must be a mapping"]
    errors: list[str] = []
    unsupported = sorted(set(schema) - SCHEMA_KEYWORDS)
    if unsupported:
        errors.append(f"{location}: {path}: keyword(s) the plugin does not support: {unsupported}")
    if "type" not in schema:
        errors.append(f"{location}: {path}.type is required")
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for key, child in properties.items():
            if not key or "." in str(key):
                errors.append(f"{location}: {path}.properties: names must be nonempty, no dots")
            errors.extend(_check_schema_subset(location, child, f"{path}.properties.{key}"))
    if "items" in schema:
        errors.extend(_check_schema_subset(location, schema["items"], f"{path}.items"))
    if isinstance(schema.get("additionalProperties"), dict):
        errors.extend(
            _check_schema_subset(
                location, schema["additionalProperties"], f"{path}.additionalProperties"
            )
        )
    return errors


def _mapping_list(location: Any, value: Any, what: str, errors: list[str]) -> list[dict[str, Any]]:
    """value as a list of mappings; anything else is reported and read as empty."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        errors.append(f"{location}: {what} must be a list of mappings")
        return []
    return value


def _validate_objects(root: Path) -> list[str]:
    """Validate object-types/ and objects/, both optional."""
    errors: list[str] = []
    types: dict[str, dict[str, Any]] = {}
    # Declared types that failed validation: their records are not checked
    # again, so one broken type reports once rather than once per record.
    broken: set[str] = set()
    types_root = root / "object-types"
    type_files = sorted(types_root.glob("*.y*ml")) if types_root.is_dir() else []
    for type_file in type_files:
        rel = type_file.relative_to(root)
        doc = _load(root, type_file, errors)
        if doc is None:
            broken.add(type_file.stem)
            continue
        found = len(errors)
        if doc.get("kind") != "object_type":
            errors.append(f"{rel}: kind must be 'object_type'")
        if doc.get("id") != type_file.stem:
            errors.append(f"{rel}: id {doc.get('id')!r} must equal file stem {type_file.stem!r}")
        name = doc.get("display_name")
        if not (isinstance(name, str) and name.strip()):
            errors.append(f"{rel}: object type is missing a non-blank display_name")
        errors.extend(_check_known_keys(rel, doc, OBJECT_TYPE_KEYS))
        for definition in _mapping_list(rel, doc.get("relationships"), "relationships", errors):
            errors.extend(
                _check_known_keys(f"{rel} relationship", definition, RELATIONSHIP_DEFINITION_KEYS)
            )
        schema = doc.get("field_schema")
        errors.extend(_check_schema_subset(rel, schema))
        if isinstance(schema, dict):
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                errors.append(f"{rel}: field_schema is not a valid JSON Schema: {exc.message}")
        if len(errors) > found:
            broken.add(type_file.stem)
            continue
        types[type_file.stem] = doc

    objects_root = root / "objects"
    records: dict[tuple[str, str], tuple[Path, dict[str, Any]]] = {}
    if objects_root.is_dir():
        for folder in sorted(p for p in objects_root.iterdir() if p.is_dir()):
            if folder.name in broken:
                continue
            if folder.name not in types:
                errors.append(
                    f"{folder.relative_to(root)}: no object type {folder.name!r} under object-types/"
                )
                continue
            for record_file in sorted(folder.glob("*.y*ml")):
                rel = record_file.relative_to(root)
                doc = _load(root, record_file, errors)
                if doc is None:
                    continue
                if doc.get("kind") != "object":
                    errors.append(f"{rel}: kind must be 'object'")
                if doc.get("object_type") != folder.name:
                    errors.append(f"{rel}: object_type must be {folder.name!r}, its folder")
                if doc.get("external_id") != record_file.stem:
                    errors.append(
                        f"{rel}: external_id {doc.get('external_id')!r} must equal file stem"
                        f" {record_file.stem!r}"
                    )
                name = doc.get("name")
                if not (isinstance(name, str) and name.strip()):
                    errors.append(f"{rel}: object is missing a non-blank name")
                errors.extend(_check_known_keys(rel, doc, OBJECT_KEYS))
                attributes = doc.get("attributes", {})
                if not isinstance(attributes, dict):
                    errors.append(f"{rel}: attributes must be a mapping")
                else:
                    validator = Draft202012Validator(types[folder.name]["field_schema"])
                    for problem in validator.iter_errors(attributes):
                        where = "/".join(str(p) for p in problem.absolute_path) or "attributes"
                        errors.append(f"{rel}: {where}: {problem.message}")
                records[(folder.name, record_file.stem)] = (rel, doc)

    for (type_id, _), (rel, doc) in records.items():
        declared = {
            r.get("rel"): r for r in _mapping_list(rel, types[type_id].get("relationships"), "", [])
        }
        named: dict[str, int] = {}
        for link in _mapping_list(rel, doc.get("relationships"), "relationships", errors):
            errors.extend(_check_known_keys(f"{rel} relationship", link, RELATIONSHIP_KEYS))
            rel_name = link.get("rel")
            spec = declared.get(rel_name)
            if spec is None:
                errors.append(f"{rel}: relationship {rel_name!r} is not declared by {type_id}")
                continue
            named[rel_name] = named.get(rel_name, 0) + 1
            target = (link.get("target_object_type"), link.get("target_external_id"))
            if target[0] != spec.get("target_object_type"):
                errors.append(
                    f"{rel}: relationship {rel_name!r} must target {spec.get('target_object_type')}"
                )
            elif target not in records:
                errors.append(f"{rel}: relationship {rel_name!r} names no record {target[1]!r}")
        for rel_name, spec in declared.items():
            count = named.get(rel_name, 0)
            if spec.get("required") and count == 0:
                errors.append(f"{rel}: required relationship {rel_name!r} is missing")
            if not spec.get("many", False) and count > 1:
                errors.append(f"{rel}: relationship {rel_name!r} allows one target")
    return errors

def main() -> int:
    tree = ROOT / "inventory"
    errors = validate_inventory_tree(tree)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"validated {tree}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
