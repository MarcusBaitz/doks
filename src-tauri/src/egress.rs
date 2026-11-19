//! The egress chokepoint.
//!
//! **Every** outbound network request from the application must pass through
//! [`Egress::request`]. ESLint and CI prohibit `fetch` in the frontend, while
//! Ruff prohibits network imports in the Python sidecar. The function checks
//! a target and returns the validated URL; no request is sent through it yet
//! and no command calls it.
//!
//! Every attempt, allowed or refused, is appended to a spool file in the data
//! directory and synced before `request` returns. The sidecar moves the lines
//! into the table `audit_log` of its database. A file was chosen over a call
//! to the sidecar because it is durable at the moment of the attempt, also
//! while the sidecar is not running, and needs no second local connection.
//!
//! This is the technical enforcement of the core promise. A configuration
//! switch could be bypassed silently; one path can be audited and tested.
//!
//! The sidecar on `127.0.0.1` is not egress: it runs on the same machine for
//! the same user and is started by this application. It therefore uses
//! `bridge.rs` rather than this module.

use crate::policy::Mode;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use url::Url;

#[derive(Debug, thiserror::Error)]
pub enum EgressError {
    #[error("Target is not a valid URL: {0}")]
    InvalidUrl(String),

    #[error("Mode {mode} does not allow outbound connections")]
    ModeRefuses { mode: &'static str },

    #[error("Target {target} is not on the allowlist")]
    NotOnAllowlist { target: String },

    #[error("Unencrypted connections are allowed only on the local machine")]
    UnencryptedRemote,
}

/// The spool file in the data directory; the sidecar reads the same name.
pub const AUDIT_FILE: &str = "egress-audit.jsonl";

/// Attempts kept in memory while the spool file cannot be written. Beyond
/// this the oldest is given up, and that loss is logged as an error.
const PENDING_LIMIT: usize = 10_000;

/// An entry destined for the `audit_log` table, one JSON line in the spool.
#[derive(Debug, Clone, serde::Serialize)]
pub struct AuditEntry {
    /// Seconds since the epoch; the sidecar stores it as ISO 8601.
    pub occurred_at: String,
    pub action: String,
    pub target: String,
    pub bytes: u64,
    pub result: &'static str,
    pub mode: &'static str,
}

pub struct Egress {
    mode: Mode,
    allowlist: Vec<String>,
    /// The spool file and the attempts not yet written to it. They wait here
    /// only until the data directory is known or while the file cannot be
    /// written; every later attempt tries to write them again.
    audit: Mutex<Audit>,
}

#[derive(Default)]
struct Audit {
    file: Option<PathBuf>,
    pending: Vec<AuditEntry>,
}

impl Audit {
    /// Append the pending entries and sync them; on failure they stay pending.
    fn write_pending(&mut self) {
        let Some(file) = &self.file else { return };
        if self.pending.is_empty() {
            return;
        }
        let lines: String = self
            .pending
            .iter()
            .filter_map(|entry| serde_json::to_string(entry).ok())
            .map(|line| line + "\n")
            .collect();
        let written = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(file)
            .and_then(|mut spool| {
                spool.write_all(lines.as_bytes())?;
                spool.sync_all()
            });
        match written {
            Ok(()) => self.pending.clear(),
            Err(error) => log::error!("Egress audit could not be written: {error}"),
        }
    }
}

impl Egress {
    pub fn new(mode: Mode, mut allowlist: Vec<String>, inference_server: Option<String>) -> Self {
        // An inference server in the customer network is a regular on-premise
        // target on the same list, not a separate network path.
        if let Some(server) = inference_server {
            allowlist.push(server);
        }
        Self {
            mode,
            allowlist,
            audit: Mutex::new(Audit::default()),
        }
    }

    pub fn mode(&self) -> Mode {
        self.mode
    }

    /// Check whether a target is allowed and log the result.
    ///
    /// The actual request happens later and must use the validated URL returned
    /// by this function.
    pub fn request(&self, raw: &str, action: &str) -> Result<Url, EgressError> {
        let result = self.check(raw);

        self.log_attempt(AuditEntry {
            occurred_at: epoch_seconds(),
            action: action.to_string(),
            target: raw.to_string(),
            bytes: 0,
            // The words of the CHECK on `audit_log.result`; a test reads the
            // migration and rejects any other status.
            result: if result.is_ok() { "allowed" } else { "denied" },
            mode: self.mode.as_str(),
        });

        if let Err(ref error) = result {
            log::warn!("Egress refused: {} → {}", action, error);
        }
        result
    }

    fn check(&self, raw: &str) -> Result<Url, EgressError> {
        let url = Url::parse(raw).map_err(|_| EgressError::InvalidUrl(raw.into()))?;

        let host = url
            .host_str()
            .ok_or_else(|| EgressError::InvalidUrl(raw.into()))?
            .to_ascii_lowercase();

        // Air-gap allows nothing through. The local sidecar does not use this
        // path, so 127.0.0.1 needs no exception here.
        if self.mode == Mode::AirGap {
            return Err(EgressError::ModeRefuses {
                mode: self.mode.as_str(),
            });
        }

        // Unencrypted traffic is allowed only on the same machine.
        let is_local = matches!(host.as_str(), "127.0.0.1" | "localhost" | "::1");
        if url.scheme() != "https" && !is_local {
            return Err(EgressError::UnencryptedRemote);
        }

        let port = url.port_or_known_default().unwrap_or(0);
        let allowed = self.allowlist.iter().any(|entry| {
            let entry = entry.trim().to_ascii_lowercase();
            entry == host || entry == format!("{host}:{port}")
        });

        if !allowed {
            return Err(EgressError::NotOnAllowlist { target: host });
        }

        Ok(url)
    }

    /// Name the data directory once it is known and write what waited for it.
    pub fn store_audit_in(&self, data_dir: &Path) {
        // The sidecar creates the directory too, but an attempt may come first.
        let _ = std::fs::create_dir_all(data_dir);
        if let Ok(mut audit) = self.audit.lock() {
            audit.file = Some(data_dir.join(AUDIT_FILE));
            audit.write_pending();
        }
    }

    fn log_attempt(&self, entry: AuditEntry) {
        if let Ok(mut audit) = self.audit.lock() {
            if audit.pending.len() >= PENDING_LIMIT {
                log::error!("Egress audit is full; the oldest unwritten attempt is lost");
                audit.pending.remove(0);
            }
            audit.pending.push(entry);
            audit.write_pending();
        }
    }
}

fn epoch_seconds() -> String {
    // Epoch seconds from the standard library avoid another dependency; the
    // sidecar turns them into ISO 8601 when it stores the entry.
    let seconds = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("{seconds}")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn egress(mode: Mode) -> Egress {
        Egress::new(
            mode,
            vec!["files.customer.internal".into(), "10.0.4.12:8000".into()],
            None,
        )
    }

    #[test]
    fn airgap_refuses_everything() {
        let e = egress(Mode::AirGap);
        assert!(e
            .request("https://files.customer.internal/x", "test")
            .is_err());
        assert!(e.request("https://example.com", "test").is_err());
    }

    #[test]
    fn onprem_allows_only_the_allowlist() {
        let e = egress(Mode::OnPrem);
        assert!(e
            .request("https://files.customer.internal/x", "test")
            .is_ok());
        assert!(e.request("https://dropbox.com/x", "test").is_err());
    }

    #[test]
    fn port_is_checked_with_the_host() {
        let e = egress(Mode::OnPrem);
        // The inference server appears on the list with its port.
        assert!(e
            .request("http://10.0.4.12:8000/v1/chat/completions", "llm")
            .is_err());
        // It is still refused because the connection is remote and unencrypted.
    }

    #[test]
    fn unencrypted_connections_are_local_only() {
        let mut e = egress(Mode::OnPrem);
        e.allowlist.push("localhost:11434".into());
        assert!(e.request("http://localhost:11434/api", "test").is_ok());
        assert!(e
            .request("http://files.customer.internal/x", "test")
            .is_err());
    }

    /// The values `audit_log.result` accepts, read from the migration itself
    /// so that shell and table cannot drift apart unnoticed.
    fn accepted_results() -> Vec<&'static str> {
        include_str!("../../sidecar/substrakt/db/migrations/001_initial_schema.sql")
            .split("CHECK (result IN (")
            .nth(1)
            .and_then(|rest| rest.split("))").next())
            .expect("audit_log has a CHECK on result")
            .split(',')
            .map(|status| status.trim().trim_matches('\''))
            .collect()
    }

    #[test]
    fn every_status_the_shell_writes_is_one_the_audit_table_accepts() {
        let accepted = accepted_results();
        assert_eq!(accepted, ["allowed", "denied", "error"]);

        let refusing = egress(Mode::AirGap);
        let allowing = egress(Mode::OnPrem);
        assert!(refusing.request("https://example.com", "test").is_err());
        assert!(allowing
            .request("https://files.customer.internal/x", "test")
            .is_ok());

        let written = [pending(&refusing), pending(&allowing)].concat();
        assert_eq!(written.len(), 2);
        for entry in written {
            assert!(
                accepted.contains(&entry.result),
                "audit_log would reject the status {:?}",
                entry.result
            );
        }
    }

    fn pending(egress: &Egress) -> Vec<AuditEntry> {
        egress.audit.lock().unwrap().pending.clone()
    }

    /// An empty directory of its own for one test.
    fn data_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("substrakt-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn spooled(dir: &Path) -> Vec<serde_json::Value> {
        std::fs::read_to_string(dir.join(AUDIT_FILE))
            .unwrap_or_default()
            .lines()
            .map(|line| serde_json::from_str(line).expect("one JSON object per line"))
            .collect()
    }

    #[test]
    fn audit_keeps_every_allowed_and_refused_attempt_across_a_restart() {
        let dir = data_dir("audit-restart");
        let first = egress(Mode::OnPrem);
        first.store_audit_in(&dir);
        assert!(first
            .request("https://files.customer.internal/x", "export")
            .is_ok());
        assert!(first.request("https://example.com", "export").is_err());
        assert!(pending(&first).is_empty(), "written, not kept in memory");
        drop(first);

        // A new shell on the same data directory, as after a restart.
        let second = egress(Mode::AirGap);
        second.store_audit_in(&dir);
        assert!(second.request("https://example.org", "update").is_err());

        let lines = spooled(&dir);
        let seen: Vec<(&str, &str, &str)> = lines
            .iter()
            .map(|line| {
                (
                    line["target"].as_str().unwrap(),
                    line["result"].as_str().unwrap(),
                    line["mode"].as_str().unwrap(),
                )
            })
            .collect();
        assert_eq!(
            seen,
            [
                ("https://files.customer.internal/x", "allowed", "onprem"),
                ("https://example.com", "denied", "onprem"),
                ("https://example.org", "denied", "airgap"),
            ]
        );
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn audit_keeps_an_attempt_that_could_not_be_written_and_writes_it_later() {
        let dir = data_dir("audit-later");
        let e = egress(Mode::AirGap);
        let _ = e.request("https://example.com", "before the data directory is known");
        assert_eq!(pending(&e).len(), 1);

        // A path below a regular file cannot take the spool.
        std::fs::write(dir.join("blocker"), b"").unwrap();
        e.store_audit_in(&dir.join("blocker"));
        let _ = e.request("https://example.org", "while the file cannot be written");
        assert_eq!(pending(&e).len(), 2, "nothing is dropped");

        e.store_audit_in(&dir);
        assert!(pending(&e).is_empty());
        let targets: Vec<String> = spooled(&dir)
            .iter()
            .map(|line| line["target"].as_str().unwrap().to_string())
            .collect();
        assert_eq!(targets, ["https://example.com", "https://example.org"]);
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn audit_line_has_the_form_the_sidecar_reads() {
        let entry = AuditEntry {
            occurred_at: "1794300000".into(),
            action: "export".into(),
            target: "https://example.com/x".into(),
            bytes: 0,
            result: "denied",
            mode: "airgap",
        };
        // The sidecar test ingests the same file; see tests/sidecar/test_audit.py.
        let fixture = include_str!("../../tests/sidecar/fixtures/egress_audit.jsonl");
        assert_eq!(
            fixture.lines().next(),
            Some(serde_json::to_string(&entry).unwrap().as_str())
        );
    }
}
