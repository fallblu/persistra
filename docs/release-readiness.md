# V3 release readiness

The rewrite implementation is pre-release code, not yet a release candidate or release.
The [implementation matrix](implementation-status.md) records remaining functional and
evidence gaps. Version changes, build publication, tags, and repository pushes remain
human-controlled.

The release gate is:

1. `make lint type test`;
2. `make docs-check` and `make docs-build`;
3. `uv lock --check` and clean installation checks for base, research, search, optimize, viz,
   dashboard, and all extras on the supported Linux/Python matrix;
4. flagship reproduction, schema upgrade/downgrade, deterministic replay, fault, resource,
   portable export, offline report relocation, and dashboard loopback smoke tests;
5. wheel/sdist content and license inspection in the human release workflow; and
6. an explicit human decision to update version metadata, build, sign, tag, push, and publish.

The required static-image renderer is not adopted. The `static` extra is an explicit
unimplemented extension point and cannot fail HTML/report/dashboard release acceptance.
Network-hosted dashboards, authentication, public binds, file uploads, arbitrary SQL, and
managed writes remain outside the v3 dashboard support boundary.
