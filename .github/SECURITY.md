# Security policy

## Supported versions

Persistra provides security fixes for the latest patch release in the current release line.

| Release line | Supported |
| --- | --- |
| Latest 4.1.x patch | Yes |
| 4.0.x and earlier | No |

The `develop` branch contains unreleased work and is not a supported release. A fix is staged there
or on a hotfix branch according to the repository's release workflow. This table is updated when a
new release line becomes supported.

## Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/fallblu/persistra/security/advisories/new)
to report a suspected vulnerability. Do not open a public issue for an undisclosed vulnerability.

A useful report includes:

- the affected Persistra version or commit;
- the security impact and the conditions needed to trigger it;
- a minimal, sanitized reproduction or proof of concept;
- relevant operating-system, Python, and dependency versions; and
- any suggested mitigation or disclosure constraints.

Do not include credentials, API keys, personal data, customer data, or licensed datasets. Replace
sensitive values with synthetic examples. If a safe reproduction cannot be shared, describe the
behavior and its boundaries instead.

## Response and disclosure

The maintainer aims to acknowledge a report within three business days and provide an initial
assessment within seven business days. Remediation timing depends on severity, exploitability, and
release risk. These targets are goals, not guarantees.

Keep the report private while it is being assessed and fixed. The maintainer and reporter will
coordinate public disclosure after a fix or mitigation is available. A GitHub security advisory
may credit the reporter when requested. The project does not currently offer a bug bounty.

Repository dependency and analysis controls are described in the
[security maintenance guide](../docs/concepts/security-maintenance.md).
