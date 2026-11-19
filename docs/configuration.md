# Configuration

Substrakt has deliberately few settings. Its defaults are the safe ones; the
only setting that can open a network path is controlled by the machine's
administrator, not by the user.

## Operating mode and machine-wide policy

The operating mode decides which outbound targets `Egress::request` may
release. It is read at start-up from a JSON policy file:

| Platform | Path (first found wins) |
|---|---|
| Linux | `/etc/substrakt/policy.json`, then `/usr/local/etc/substrakt/policy.json` |
| macOS | `/Library/Application Support/Substrakt/policy.json` |
| Windows | `%ProgramData%\Substrakt\policy.json` |

```json
{
  "mode": "onprem",
  "allowlist": ["files.example.internal", "10.0.4.12:8000"],
  "inference_server": "http://10.0.4.12:8000"
}
```

| Key | Values | Meaning |
|---|---|---|
| `mode` | `airgap`, `onprem`, `cloud` | operating mode; missing means `airgap` |
| `allowlist` | list of `host` or `host:port` | permitted targets; only effective in `onprem` and `cloud` |
| `inference_server` | URL | a vLLM server in the customer network; added to the allowlist and counted as on-premise, not cloud |

**No file means Air-gap. A broken file also means Air-gap**, and the error is
logged. A configuration mistake can never make the application more open.

The policy file is the ceiling. A per-user setting may only narrow the mode,
never widen it (`policy::narrow`); that setting is not yet exposed in the
interface.

## Directories

| What | Default | Override |
|---|---|---|
| Application data, SQLite | The shell passes the Tauri app data directory of the identifier `it.baitz.substrakt` (`src-tauri/tauri.conf.json`): Linux `$XDG_DATA_HOME/it.baitz.substrakt` (`~/.local/share/it.baitz.substrakt`); macOS `~/Library/Application Support/it.baitz.substrakt`; Windows `%APPDATA%\it.baitz.substrakt`. A sidecar started without the shell falls back to `~/.local/share/substrakt`, `~/Library/Application Support/Substrakt` or `%APPDATA%\Substrakt`. | `SUBSTRAKT_DATA_DIR` |
| Model weights | `<data dir>/models`; in development `models/` in the repository | `SUBSTRAKT_MODEL_DIR` |
| Logs | `<data dir>/logs`, local and rotating | `SUBSTRAKT_LOG_DIR` |

Logs contain file names, hashes and metrics, never document content.

## Customer setup

What a customer's watched folder means is not code but files, and three
folders in the data directory replace the files the core ships under the
same name. A customer setup is therefore a set of files copied there; nothing
is merged, and a file read again after a change needs no restart.

| Folder | Replaces | Holds |
|---|---|---|
| `<data dir>/pipeline_profiles/` | `sidecar/substrakt/pipeline_profiles/<name>.yml` | the profile: folder level of the customer, kinds, expected values, target and the block `hand_over` ([`pipeline-profiles.md`](pipeline-profiles.md)) |
| `<data dir>/document_kinds/` | `sidecar/substrakt/document_kinds/<name>.yml` | a kind file of the customer, or a changed copy of a shipped one ([`document-types.md`](document-types.md)); Belegarten writes its changes here as well |
| `<data dir>/gdv/` | `sidecar/substrakt/gdv/tables/<name>.yml` | the GDV mapping tables with the customer's insurers, lines of business and payment modes ([`gdv-hand-over.md`](gdv-hand-over.md)) |

The core ships one example profile, `insurance_folder.yml`, whose target has
no writer. Material of a real customer (its profile, its contracts and its
research) is kept in a private repository and copied into these folders; the
core names no customer and no target program. A profile that names a kind
without a file or a value the kind does not read is refused with
`pipeline-profile-invalid` when it is loaded.

## Read roots

The sidecar opens only files below its read roots. The shell sets them in
`SUBSTRAKT_ROOTS`: the user's home directory and, where present, `/media`,
`/mnt` and `/srv` on Linux or `/Volumes` on macOS. System directories such as
`/etc`, `/tmp` and `/` are never included. Files on other network shares are
rejected; a share list filled from the file dialog is planned for stage 4.

## Environment variables

The shell sets these when it starts the sidecar. They are documented for
development and diagnosis, not as user settings.

| Variable | Set by | Purpose |
|---|---|---|
| `SUBSTRAKT_TOKEN` | shell | random session token; the sidecar refuses to start without it unless `SUBSTRAKT_DEV=1` |
| `SUBSTRAKT_BIND` | shell | `127.0.0.1:0` |
| `SUBSTRAKT_MODE` | shell | the effective operating mode |
| `SUBSTRAKT_DATA_DIR` | shell | application data directory |
| `SUBSTRAKT_ROOTS` | shell | read roots, separated by the platform path separator |
| `SUBSTRAKT_PARENT_PID` | shell | process ID of the shell |
| `SUBSTRAKT_MODEL_DIR` | optional | model directory; also used by `scripts/fetch-models.sh` |
| `SUBSTRAKT_LOG_DIR` | optional | log directory |
| `SUBSTRAKT_DEV` | developer | `1` lets the sidecar run without a token; `tests/sidecar/conftest.py` sets it for tests |
