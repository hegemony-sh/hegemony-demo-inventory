<!--
SPDX-FileCopyrightText: 2025-2026 Jakub Travnik <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Hegemony Demo Inventory

Git inventory source of truth for the [Hegemony](https://github.com/hegemony-sh/hegemony)
demo: the site and device records that the demo's `lab-inventory` git
inventory provider syncs into the platform.

The [`hegemony-demo-data`](https://github.com/hegemony-sh/hegemony-demo-data)
repository bootstraps the demo instance with a git repository entry pointing
here and an enabled git inventory provider reading
[`demo-inventory/`](demo-inventory) from it. Hegemony clones this repository
**anonymously over HTTPS from inside the platform containers**, which is why
the tree lives in its own always-public repository: the provider works on the
first startup sync with zero credentials, independent of the visibility of the
other Hegemony repositories.

## Layout

```text
demo-inventory/
├── sites/      # site records; paths derive from the directory layout
└── devices/    # device records (schema_version: 1), credential-free
```

- **Sites** — the fictional operator Meridian Networks' virtual-lab hierarchy:
  two lab datacenters and two branches under a root `virtual-lab` site. A file
  whose stem equals its directory name identifies that directory
  (`sites/virtual-lab/dc1/dc1.yaml` → site path `virtual-lab/dc1`).
- **Devices** — the eleven FRR lab routers and four Linux endpoint hosts the
  demo's containerlab topology deploys. Device files carry **no credentials**:
  the provider merges shared SSH material via its `default_access_config`, and
  any `*_ref` value in a device file must use `env()`/`file()`/`secret()`
  template syntax, never a literal.

The records use the git inventory plugin's `schema_version: 1` format
(`kind: site` / `kind: device`, `external_id` equal to the file stem).
Descriptive facts such as `vendor` and `model` go under a device's
`attributes:` mapping, not at the top level: the plugin rejects any key its
schema does not know, and one rejected file fails the whole sync. The provider
is configured with `path: demo-inventory` and a release tag of this repository
as its branch.

## Validation

```bash
uv sync
uv run python scripts/validate.py
```

`scripts/validate.py` applies the same fail-closed rules the git inventory
plugin enforces at runtime (schema version, external-id/file-stem equality,
the plugin's required fields — non-blank `name` on sites and devices,
`mgmt_host` on devices — no keys the plugin schema does not know, resolved
site references, templated access refs), so a broken tree fails CI here
instead of failing the demo's inventory sync. Fields the plugin schema treats
as optional (`mgmt_port`, `platform`, `attributes`, `site`, `role`) are
optional here too.

## Making changes

The demo reads this repository at a release tag (`vYYYY.MM.DD`), not at
`main`, so a change reaches it only once it is tagged and
`hegemony-demo-data` bumps its pin to that tag (its `docs/release.md` says
how). Keep the
tree consistent with the lab topology defined in `hegemony-demo-data`
(`src/files/lab/topology.clab.yml`): management addresses here must match the
addresses containerlab assigns there.

## License

AGPL-3.0-or-later, same as the other Hegemony repositories — see
[LICENSE](LICENSE). Copyright (C) 2025-2026 Jakub Travnik.
