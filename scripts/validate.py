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
``field_schema`` within the plugin's JSON Schema subset, ``ui`` and ``filters``
that name declared attributes, a folder for every type, every file in its place
and declared once, attributes that match their type's ``field_schema``, and
relationships that name declared relationships and existing records, once each.
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
UI_KEYS = frozenset({"icon", "columns", "detail_layout", "search_fields", "default_sort"})
# Record fields ui metadata may name besides attributes.
ENVELOPE_FIELDS = frozenset({"name", "display_name", "external_id"})
# hegemony_inventory_sdk.identifiers.OBJECT_TYPE_ID_PATTERN.
OBJECT_TYPE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
YAML = frozenset({".yaml", ".yml"})
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


def _yaml_files(section: Path) -> list[Path]:
    """Every YAML file under section, at any depth, as the plugin discovers them."""
    if not section.is_dir():
        return []
    return sorted(p for p in section.rglob("*") if p.is_file() and p.suffix.lower() in YAML)


def _schema_type(schema: dict[str, Any], name: str) -> list[str] | None:
    """The JSON types of a top-level attribute, or None when it is not declared.

    An empty list is a declared attribute whose type is malformed."""
    properties = schema.get("properties")
    if not isinstance(properties, dict) or "." in name or not isinstance(properties.get(name), dict):
        return None
    kinds = properties[name].get("type", [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    # A malformed type is reported by the schema checks: the attribute is
    # declared, with no type the scalar checks can read.
    if not isinstance(kinds, list) or not all(isinstance(k, str) for k in kinds):
        return []
    return kinds


def _check_type_metadata(location: Any, doc: dict[str, Any]) -> list[str]:
    """The plugin's spec() rules for an object type beyond its keys."""
    errors: list[str] = []
    type_id = doc.get("id")
    if not (isinstance(type_id, str) and OBJECT_TYPE_ID_RE.fullmatch(type_id)):
        errors.append(f"{location}: id must be lowercase letters, digits, '.', '_' or '-'")
    elif type_id in {"device", "site"}:
        errors.append(f"{location}: id {type_id!r} is reserved")
    schema = doc.get("field_schema")
    if not isinstance(schema, dict):
        return [*errors, f"{location}: field_schema must be a mapping"]
    if schema.get("type") != "object":
        errors.append(f"{location}: field_schema.type must be object")
    errors.extend(_check_schema_subset(location, schema))
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        errors.append(f"{location}: field_schema is not a valid JSON Schema: {exc.message}")
    definitions = _mapping_list(location, doc.get("relationships"), "relationships", errors)
    names = [d.get("rel") for d in definitions]
    if not all(isinstance(n, str) and n for n in names):
        errors.append(f"{location}: relationships: every rel must be a non-empty string")
    elif len(set(names)) != len(names):
        errors.append(f"{location}: relationships: duplicate relation name")
    for definition in definitions:
        errors.extend(
            _check_known_keys(f"{location} relationship", definition, RELATIONSHIP_DEFINITION_KEYS)
        )
        target = definition.get("target_object_type")
        if not (isinstance(target, str) and target):
            errors.append(f"{location}: relationships: target_object_type must be a non-empty string")
    ui = doc.get("ui", {})
    if not isinstance(ui, dict):
        return [*errors, f"{location}: ui must be a mapping"]
    errors.extend(_check_known_keys(f"{location} ui", ui, UI_KEYS))
    for key in ("columns", "detail_layout", "search_fields"):
        values = ui.get(key, [])
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            errors.append(f"{location}: ui.{key} must be a list of attribute names")
            continue
        for value in values:
            if value not in ENVELOPE_FIELDS and _schema_type(schema, value) is None:
                errors.append(f"{location}: ui.{key} names undeclared attribute {value!r}")
    sort = ui.get("default_sort")
    if sort is not None:
        if not isinstance(sort, str):
            errors.append(f"{location}: ui.default_sort must be a string")
        elif sort.lstrip("-") not in ENVELOPE_FIELDS:
            kinds = _schema_type(schema, sort.lstrip("-"))
            if kinds is None:
                errors.append(f"{location}: ui.default_sort names undeclared attribute {sort!r}")
            elif {"object", "array"} & set(kinds):
                errors.append(f"{location}: ui.default_sort needs a scalar attribute")
    filters = doc.get("filters", [])
    if not isinstance(filters, list) or not all(isinstance(f, str) for f in filters):
        return [*errors, f"{location}: filters must be a list of attribute names"]
    for name in filters:
        kinds = _schema_type(schema, name)
        if kinds is None:
            errors.append(f"{location}: filters name undeclared attribute {name!r}")
        elif {"object", "array"} & set(kinds):
            errors.append(f"{location}: filter {name!r} needs a scalar attribute")
    return errors


def _validate_objects(root: Path) -> list[str]:
    """Validate object-types/ and objects/, both optional, as the plugin loads them."""
    errors: list[str] = []
    types: dict[str, dict[str, Any]] = {}
    # Types whose file is broken: their folder and records are not checked
    # again, so one broken type reports once rather than once per record.
    broken: set[str] = set()
    types_root = root / "object-types"
    for type_file in _yaml_files(types_root):
        rel = type_file.relative_to(root)
        if type_file.parent != types_root:
            errors.append(f"{rel}: object types must be directly inside object-types/")
            continue
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
        errors.extend(_check_type_metadata(rel, doc))
        if type_file.stem in types or type_file.stem in broken:
            errors.append(f"{rel}: object type {type_file.stem!r} is declared twice")
        if len(errors) > found:
            broken.add(type_file.stem)
            continue
        types[type_file.stem] = doc

    objects_root = root / "objects"
    for type_id, doc in types.items():
        # Git keeps no empty folder: an empty type needs objects/<id>/.gitkeep.
        if not (objects_root / type_id).is_dir():
            errors.append(f"objects/{type_id}: missing folder (add .gitkeep for an empty type)")
        for definition in _mapping_list(type_id, doc.get("relationships"), "", []):
            target = definition.get("target_object_type")
            if target not in types and target not in broken:
                errors.append(
                    f"object-types/{type_id}: relationship target type {target!r} is not declared"
                )

    records: dict[tuple[str, str], tuple[Path, dict[str, Any]]] = {}
    for record_file in _yaml_files(objects_root):
        rel = record_file.relative_to(root)
        folder = record_file.parent
        if folder.parent != objects_root:
            errors.append(f"{rel}: records must sit directly in objects/<object type>/")
            continue
        if folder.name in broken:
            continue
        if folder.name not in types:
            errors.append(f"{rel}: no object type {folder.name!r} under object-types/")
            continue
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
        if not (isinstance(name, str) and name.strip() and name == name.strip()):
            errors.append(f"{rel}: object needs a non-blank name without surrounding spaces")
        errors.extend(_check_known_keys(rel, doc, OBJECT_KEYS))
        attributes = doc.get("attributes", {})
        if not isinstance(attributes, dict):
            errors.append(f"{rel}: attributes must be a mapping")
        else:
            validator = Draft202012Validator(types[folder.name]["field_schema"])
            for problem in validator.iter_errors(attributes):
                where = "/".join(str(p) for p in problem.absolute_path) or "attributes"
                errors.append(f"{rel}: {where}: {problem.message}")
        identity = (folder.name, record_file.stem)
        if identity in records:
            errors.append(f"{rel}: duplicate record {record_file.stem!r} in {folder.name}")
            continue
        records[identity] = (rel, doc)

    for (type_id, _), (rel, doc) in records.items():
        declared = {
            r.get("rel"): r for r in _mapping_list(rel, types[type_id].get("relationships"), "", [])
        }
        named: dict[str, int] = {}
        seen: set[tuple[Any, Any, Any]] = set()
        for link in _mapping_list(rel, doc.get("relationships"), "relationships", errors):
            errors.extend(_check_known_keys(f"{rel} relationship", link, RELATIONSHIP_KEYS))
            rel_name = link.get("rel")
            target = (link.get("target_object_type"), link.get("target_external_id"))
            if not all(isinstance(v, str) and v for v in (rel_name, *target)):
                errors.append(
                    f"{rel}: relationship rel, target_object_type and target_external_id"
                    " must be non-empty strings"
                )
                continue
            edge = (rel_name, *target)
            if edge in seen:
                errors.append(f"{rel}: relationship {rel_name!r} to {target[1]!r} is listed twice")
                continue
            seen.add(edge)
            spec = declared.get(rel_name)
            if spec is None:
                errors.append(f"{rel}: relationship {rel_name!r} is not declared by {type_id}")
                continue
            named[rel_name] = named.get(rel_name, 0) + 1
            if target[0] != spec.get("target_object_type"):
                errors.append(
                    f"{rel}: relationship {rel_name!r} must target {spec.get('target_object_type')}"
                )
            elif target not in records and target[0] not in broken:
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
