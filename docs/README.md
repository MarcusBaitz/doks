# Documentation

## Using Substrakt

- [Getting started](getting-started.md): installation with `npm start`, WSL2, first steps
- [Configuration](configuration.md): operating modes, policy file, directories, environment
- [Document types](document-types.md): describing a kind of document in YAML

## Understanding and changing it

- [Architecture](architecture/README.md): three processes, egress chokepoint, persistence boundary; diagram as [SVG](architecture/architecture.svg) with [Mermaid source](architecture/architecture.mmd)
- [Development](development.md): commands, project layout, tests, glossary
- [Gates](gates.md): what CI rejects and why
- [Contributing](../CONTRIBUTING.md) and [Security policy](../SECURITY.md)
- [Changelog](../CHANGELOG.md)
- [Release readiness](release-readiness.md): licence, history and data check before going public

## Records

- [`decisions.md`](decisions.md): binding decisions, condensed
- [`status.md`](status.md): report after stage 1; its lessons on CI, first start and wrong assumptions still apply
- [`design/design-language.md`](design/design-language.md): design language v2 with a reference prototype
- [`measurements/`](measurements/): measurement protocols from `bench/`
- [`harness/`](harness/): rules for coding agents, loaded by `CLAUDE.md`
- [`plans/`](plans/): hand-over plans for coding agents

## Watched folder and hand-over

- [`pipeline-profiles.md`](pipeline-profiles.md): how to write a profile for a broker and a target application, with the shipped example profile as the worked example
- [`job-format.md`](job-format.md): the versioned format of the job file and the states of a job
- [`gdv-hand-over.md`](gdv-hand-over.md): which approved value goes into which record and field of a GDV file
- [`configuration.md`](configuration.md), section “Customer setup”: where a customer's profile, kinds and tables go in the data directory

The material of the first pilot customer (its profile, goal contracts,
research and screenshots) is kept in a private repository and is not part
of this one.

The original analyses behind the decisions (technical evaluation, licence
audit, inference architecture, build brief) are internal documents and not
published. `decisions.md` holds what is binding from them; what is
enforced by machine is in [`../licenses/policy.toml`](../licenses/policy.toml),
not in prose.
