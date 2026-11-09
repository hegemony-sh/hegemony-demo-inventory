<!--
SPDX-FileCopyrightText: 2025-2026 Rexonix s.r.o.
SPDX-FileContributor: Jakub Travnik <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Hegemony demo inventory

[![License: AGPL-3.0-or-later](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue.svg)](LICENSE)
[![Inventory validation](https://github.com/hegemony-sh/hegemony-demo-inventory/actions/workflows/check.yml/badge.svg?branch=main&event=push)](https://github.com/hegemony-sh/hegemony-demo-inventory/actions/workflows/check.yml)
[![Latest release](https://img.shields.io/github/v/release/hegemony-sh/hegemony-demo-inventory?label=Release)](https://github.com/hegemony-sh/hegemony-demo-inventory/releases)

[Website](https://hegemony.sh/) · [Run the demo](https://github.com/hegemony-sh/hegemony-demo) ·
[Git inventory provider](https://github.com/hegemony-sh/hegemony-inventory-plugins/tree/main/plugins/inventory_git)

An example Git inventory repository for [Hegemony](https://hegemony.sh/),
supplying the planned site Olympia, its devices and the service catalogue
used by the [Hegemony demo](https://github.com/hegemony-sh/hegemony-demo).
The rest of the demo inventory is generated in the demo repository.
Hegemony's Git inventory provider reads records like these from a Git
repository and keeps the platform's inventory in step with them.

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

## Example device

[`inventory/devices/oly1-edge-01.yaml`](inventory/devices/oly1-edge-01.yaml)
is a complete device record (SPDX comments omitted):

```yaml
schema_version: 1
kind: device
external_id: oly1-edge-01
name: oly1-edge-01
mgmt_host: 10.90.2.1
platform: junos
attributes:
  vendor: Juniper
  model: MX204
  serial: DEMO6253DCC7
  loopback: 10.255.0.7
site: oly1
role: edge
tags:
- edge
- planned
```

The `site: oly1` reference resolves to
[`inventory/sites/oly1/oly1.yaml`](inventory/sites/oly1/oly1.yaml). These
addresses describe fictional planned devices; importing them does not create
or start routers.

## Use outside the demo

Use this repository as an example for your own inventory, or register it as a
Git repository in Hegemony and configure the Git inventory provider with
`path: inventory`. The provider must be installed in your deployment; see
its [installation and configuration guide](https://github.com/hegemony-sh/hegemony-inventory-plugins/tree/main/plugins/inventory_git).

Keep credentials in the platform's secret backend and provider access
configuration. Do not put literal credentials in inventory files. If you
adapt these records, change the identifiers, sites and addresses together,
then validate the entire tree before syncing it.

## Compatibility

The records use `schema_version: 1`. Object types and objects require Git
inventory plugin 0.5.0 or later; choose the plugin release supported by your
platform. The demo pins its tested inventory tag in `platform.env`, separately
from the platform and plugin versions.

## Validation

Requires Python 3.12 or newer and [uv](https://docs.astral.sh/uv/). From a
checkout of this repository:

```bash
uv sync --frozen
uv run python scripts/validate.py
uv run reuse lint
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

## Contributing, security and licence

- Report invalid examples or request improvements through
  [GitHub Issues](https://github.com/hegemony-sh/hegemony-demo-inventory/issues).
- Read [Contributing](CONTRIBUTING.md) for validation and the release process.
  Every commit requires a DCO sign-off (`git commit -s`).
- Report vulnerabilities or accidentally published credentials privately;
  see [Security](SECURITY.md).
- Participation follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- Licensed under `AGPL-3.0-or-later`; see [Licensing](LICENSING.md).
