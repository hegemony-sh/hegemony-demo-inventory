<!--
SPDX-FileCopyrightText: 2025-2026 Rexonix s.r.o.
SPDX-FileContributor: Jakub Travnik <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Contributing

This repository holds synthetic inventory records for the Hegemony demo and
the Python validator that checks them. For changes to the running lab, flows
or installer, use [hegemony-demo](https://github.com/hegemony-sh/hegemony-demo).

## Workflow

1. Open an issue for a proposed change, or a pull request with a clear
   explanation of the problem and the resulting records or behaviour.
2. Edit `inventory/` or `scripts/validate.py`. Keep file names, identifiers,
   site references and object links consistent. Use synthetic data only;
   never commit credentials, customer records or private keys.
3. With Python 3.12 or newer and [uv](https://docs.astral.sh/uv/), run:

   ```sh
   uv sync --frozen
   uv run python -m py_compile scripts/validate.py
   uv run python scripts/validate.py
   uv run reuse lint
   ```

4. Update the README when the format, examples or validation commands change.
5. Use Conventional Commits, for example `fix(data): correct a site reference`,
   and sign off every commit with `git commit -s`.

The Check workflow validates inventory and licensing, and checks commit
messages on pull requests. Validation checks the tree as a whole: one invalid
record rejects the sync. For changes to the validator, describe how you
checked both valid records and rejection of the invalid input being fixed.

## Releases and the demo

Maintainers publish immutable inventory releases using `vYYYY.MM.DD` tags.
Never move an existing release tag. Include release notes describing the
changed records and any effect on the demo; if a date's tag already exists,
choose a distinct release identifier and update the consumer pin explicitly.

After the inventory change is merged, validated and released:

1. Update `HEGEMONY_INVENTORY_REF` in the demo's `platform.env`.
2. Update the demo's `spec/basic.yaml` if its expected inventory changed.
3. In the demo checkout, run `deploy/lab/fetch-inventory.sh`, then
   `uv run demo-gen --check-inventory deploy/lab/inventory`.

See the demo's [contribution guide](https://github.com/hegemony-sh/hegemony-demo/blob/main/CONTRIBUTING.md)
for regeneration and full demo checks. Merging here alone does not update a
pinned demo installation.

## Licensing and sign-off

Contributions are accepted under `AGPL-3.0-or-later`, with no copyright
assignment or Contributor License Agreement. Keep SPDX metadata on changed
files and add it to new files; see [Licensing](LICENSING.md).

The one exception is the [Code of Conduct](CODE_OF_CONDUCT.md): it is adapted
third-party documentation under `CC-BY-4.0`, and changes to it are contributed
under `CC-BY-4.0`. Preserve its attribution and licence when editing it.

A sign-off certifies the [Developer Certificate of Origin](https://developercertificate.org/)
version 1.1. The name and email in `Signed-off-by:` must match the commit
author. For work written with an AI coding agent, the person directing and
submitting the work is the author and signs off; credit the agent in a
`Co-authored-by:` trailer, never as the signatory.

Follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report vulnerabilities and
leaked credentials privately through [Security](SECURITY.md), not public issues.
