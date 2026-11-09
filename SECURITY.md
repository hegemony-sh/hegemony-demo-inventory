<!--
SPDX-FileCopyrightText: 2025-2026 Rexonix s.r.o.
SPDX-FileContributor: Jakub Travnik <jakub.travnik@gmail.com>

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Security policy

Report vulnerabilities, suspected compromise or accidentally published
credentials privately to [security@hegemony.sh](mailto:security@hegemony.sh).
Do not open public issues containing exploit details or secrets.

This repository contains synthetic inventory records and their validator.
Reports about the validator, CI workflows, unsafe inventory examples or
real credentials committed by mistake are in scope. The fictional device
addresses and names are intentional demo data.

Include the affected release tag or commit, a description of the impact and
safe reproduction steps. Do not include real credentials or customer data.
The Hegemony demo uses the same security contact; see its
[security policy](https://github.com/hegemony-sh/hegemony-demo/blob/main/SECURITY.md)
for the shared reporting process and response targets.

Fixes land on `main` and can be published in a new inventory release.
Existing release tags are not rewritten. Demo consumers must update their
inventory pin to receive a released fix.
