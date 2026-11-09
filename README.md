<!--
SPDX-FileCopyrightText: 2025-2026 Rexonix s.r.o.
SPDX-FileContributor: Jakub Travnik <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Hegemony Demo Inventory

An example Git inventory repository for [Hegemony](https://github.com/hegemony-sh/hegemony),
and the inventory the [Hegemony demo](https://github.com/hegemony-sh/hegemony-demo)
lab runs on. Hegemony's Git inventory provider reads records like these from a
Git repository and keeps the platform's inventory in step with them.

The demo pins a release tag of this repository. When the lab starts, it
copies [`inventory/`](inventory) from that tag into the lab's Git server
(Gitea, `netops/inventory`), and the demo's Git inventory provider syncs it
from there. All names and addresses are made up for the demo.

## Layout

```text
inventory/
├── sites/          # site records; a site's path comes from its folder
├── devices/        # device records, without credentials
├── object-types/   # inventory types the repository defines (plugin 0.5.0 and later)
└── objects/        # records of those types, one folder per type
```

- **Sites:** Olympia (`oly1`), a datacenter that the fictional operator
  Amphictyon Networks is still planning. A file whose name matches its folder
  describes that folder (`sites/oly1/oly1.yaml` is the site `oly1`).
- **Devices:** the two routers planned for Olympia. Device files carry **no
  credentials**. The provider adds shared SSH settings itself, and any `*_ref`
  value must be a template such as `{{ secret(...) }}`, never a literal.
- **Object types and objects:** a small service catalogue. `demo.service`
  describes a service; `demo.service_address` is an address a service answers
  on, linked to its service. The demo's "service as code" story picks a
  service and an address from them.

Every file uses the Git inventory plugin's `schema_version: 1` format. A
record's `external_id` (an object type's `id`) equals its file name without
`.yaml`.
Descriptive facts such as `vendor` and `model` go under a device's
`attributes:`. The plugin rejects any key its schema does not know, and one
rejected file fails the whole sync.

## Validation

```bash
uv sync
uv run python scripts/validate.py
```

`scripts/validate.py` applies the same fail-closed rules the plugin applies
when it syncs: the schema version, file names, required fields, unknown keys,
site references, templated access refs, object attributes against their
type's JSON Schema, and links between objects. CI runs it on every change.

## Making changes

The demo reads this repository at a release tag (`vYYYY.MM.DD`), not at
`main`. A change reaches the demo in three steps:

1. Change `inventory/` here and tag a release.
2. In the demo, change `spec/basic.yaml` to match, if needed, and pin the new
   tag in `platform.env` (`HEGEMONY_INVENTORY_REF`).
3. The demo's CI (`demo-gen --check-inventory`) checks that the pinned tag
   matches its spec: the sites, devices and service catalogue the demo's
   stories expect, with the addresses its lab uses.

## License

AGPL-3.0-or-later, same as the other Hegemony repositories — see
[LICENSE](LICENSE). Copyright (C) 2025-2026 Rexonix s.r.o. Written by Jakub Trávník.
