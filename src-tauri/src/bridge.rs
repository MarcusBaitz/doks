//! The bridge between frontend and sidecar.
//!
//! Every frontend call passes through a command in this file. The frontend
//! knows neither the sidecar port nor the session token and has no HTTP client;
//! ESLint and CI prohibit `fetch`, `XMLHttpRequest`, `WebSocket` and `axios`.
//!
//! Domain types are deliberately not reproduced in Rust. They live in the
//! sidecar's Pydantic model and the TypeScript contract. Rust passes through
//! `serde_json::Value`, avoiding a third definition that could drift.

use crate::AppState;
use serde::Serialize;
use std::time::Duration;
use tauri::State;

/// Error returned to the frontend, including the stable RFC 9457 problem key.
#[derive(Debug, Serialize)]
pub struct BridgeError {
    /// Stable key, for example `document-password-protected`.
    pub key: String,
    /// Human-readable fallback text from the sidecar.
    pub title: String,
    pub detail: Option<String>,
    pub status: u16,
    /// Why a correction or approval was refused, such as `entry-changed`.
    pub reason: Option<String>,
    /// What a refused approval names, such as `payment_mode_code`; names only, never values.
    pub items: Vec<String>,
}

impl BridgeError {
    fn technical(key: &str, detail: impl Into<String>) -> Self {
        Self {
            key: key.into(),
            title: "Backend connection failed".into(),
            detail: Some(detail.into()),
            status: 503,
            reason: None,
            items: Vec::new(),
        }
    }
}

type BridgeResult<T> = Result<T, BridgeError>;

/// Evaluate a sidecar response as JSON or RFC 9457 problem details.
async fn evaluate(response: reqwest::Response) -> BridgeResult<serde_json::Value> {
    let status = response.status();
    let text = response
        .text()
        .await
        .map_err(|e| BridgeError::technical("response-unreadable", e.to_string()))?;

    let json: serde_json::Value = serde_json::from_str(&text).unwrap_or(serde_json::Value::Null);

    if status.is_success() {
        return Ok(json);
    }

    Err(problem(status.as_u16(), &json))
}

/// Read RFC 9457 problem details into the error the frontend receives.
fn problem(status: u16, json: &serde_json::Value) -> BridgeError {
    // RFC 9457: the `type` URI ends with the stable key.
    let key = json
        .get("key")
        .and_then(|t| t.as_str())
        .or_else(|| {
            json.get("type")
                .and_then(|t| t.as_str())
                .and_then(|t| t.rsplit('/').next())
        })
        .unwrap_or("internal-error")
        .to_string();

    BridgeError {
        key,
        title: json
            .get("title")
            .and_then(|t| t.as_str())
            .unwrap_or("Unknown error")
            .to_string(),
        detail: json
            .get("detail")
            .and_then(|d| d.as_str())
            .map(str::to_string),
        status,
        reason: json
            .get("reason")
            .and_then(|r| r.as_str())
            .map(str::to_string),
        items: json
            .get("items")
            .and_then(|i| i.as_array())
            .map(|i| {
                i.iter()
                    .filter_map(|n| n.as_str().map(str::to_string))
                    .collect()
            })
            .unwrap_or_default(),
    }
}

/// Return the address and token of the running sidecar.
///
/// Both values are copied and the lock is released immediately. Holding the
/// guard across HTTP would serialize requests, so a 120-second render could
/// block concurrent text and word loading.
async fn connection(state: &AppState) -> BridgeResult<(String, String)> {
    let guard = state.sidecar.lock().await;
    let sidecar = guard
        .as_ref()
        .ok_or_else(|| BridgeError::technical("sidecar-not-connected", "Backend is not running"))?;
    Ok((sidecar.basis_url(), sidecar.token.clone()))
}

/// Send GET to the sidecar.
async fn fetch(state: &AppState, path: &str) -> BridgeResult<serde_json::Value> {
    let (base, token) = connection(state).await?;

    let response = state
        .http
        .get(format!("{base}{path}"))
        .bearer_auth(&token)
        .timeout(Duration::from_secs(120))
        .send()
        .await
        .map_err(|e| BridgeError::technical("sidecar-unreachable", e.to_string()))?;

    evaluate(response).await
}

/// Send GET to the sidecar and return raw bytes.
async fn fetch_bytes(state: &AppState, path: &str) -> BridgeResult<Vec<u8>> {
    let (base, token) = connection(state).await?;

    let response = state
        .http
        .get(format!("{base}{path}"))
        .bearer_auth(&token)
        .timeout(Duration::from_secs(120))
        .send()
        .await
        .map_err(|e| BridgeError::technical("sidecar-unreachable", e.to_string()))?;

    if !response.status().is_success() {
        // evaluate() always returns Err here because success was handled above.
        return Err(evaluate(response)
            .await
            .err()
            .unwrap_or_else(|| BridgeError::technical("unknown-error", "unexpected response")));
    }

    response
        .bytes()
        .await
        .map(|b| b.to_vec())
        .map_err(|e| BridgeError::technical("response-unreadable", e.to_string()))
}

/// Send DELETE to the sidecar.
async fn remove(state: &AppState, path: &str) -> BridgeResult<serde_json::Value> {
    let (base, token) = connection(state).await?;

    let response = state
        .http
        .delete(format!("{base}{path}"))
        .bearer_auth(&token)
        .timeout(Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| BridgeError::technical("sidecar-unreachable", e.to_string()))?;

    evaluate(response).await
}

/// Send POST to the sidecar.
async fn send(
    state: &AppState,
    path: &str,
    body: serde_json::Value,
) -> BridgeResult<serde_json::Value> {
    let (base, token) = connection(state).await?;

    let response = state
        .http
        .post(format!("{base}{path}"))
        .bearer_auth(&token)
        .json(&body)
        .timeout(Duration::from_secs(300))
        .send()
        .await
        .map_err(|e| BridgeError::technical("sidecar-unreachable", e.to_string()))?;

    evaluate(response).await
}

// --- Commands --------------------------------------------------------------

#[derive(Serialize)]
pub struct Status {
    pub connected: bool,
    pub version: String,
    pub mode: String,
    /// Label for the status line, for example “Local: granite-4.0-micro”.
    /// Stage 1 has no model yet; inference arrives in stage 3.
    pub backend: String,
}

#[tauri::command]
pub async fn sidecar_status(state: State<'_, AppState>) -> BridgeResult<Status> {
    let sidecar = state.sidecar.lock().await;
    let Some(sidecar) = sidecar.as_ref() else {
        return Ok(Status {
            connected: false,
            version: String::new(),
            mode: state.mode.as_str().into(),
            backend: "not connected".into(),
        });
    };

    Ok(Status {
        connected: true,
        version: sidecar.version.clone(),
        mode: state.mode.as_str().into(),
        backend: match state.mode {
            crate::policy::Mode::AirGap => "Local — Air-gap".into(),
            crate::policy::Mode::OnPrem => "Local — On-premise".into(),
            crate::policy::Mode::Cloud => "Local — Cloud enabled".into(),
        },
    })
}

#[tauri::command]
pub async fn load_document(
    state: State<'_, AppState>,
    path: String,
) -> BridgeResult<serde_json::Value> {
    send(&state, "/documents", serde_json::json!({ "path": path })).await
}

#[tauri::command]
pub async fn document_info(
    state: State<'_, AppState>,
    doc_id: String,
) -> BridgeResult<serde_json::Value> {
    fetch(&state, &format!("/documents/{doc_id}")).await
}

#[tauri::command]
pub async fn page_words(
    state: State<'_, AppState>,
    doc_id: String,
    page: usize,
) -> BridgeResult<serde_json::Value> {
    fetch(&state, &format!("/documents/{doc_id}/pages/{page}/words")).await
}

#[tauri::command]
pub async fn document_text(
    state: State<'_, AppState>,
    doc_id: String,
) -> BridgeResult<serde_json::Value> {
    fetch(&state, &format!("/documents/{doc_id}/text")).await
}

#[tauri::command]
pub async fn sheets(state: State<'_, AppState>, doc_id: String) -> BridgeResult<serde_json::Value> {
    fetch(&state, &format!("/documents/{doc_id}/sheets")).await
}

#[tauri::command]
pub async fn sheet_raster(
    state: State<'_, AppState>,
    doc_id: String,
    index: usize,
) -> BridgeResult<serde_json::Value> {
    fetch(
        &state,
        &format!("/documents/{doc_id}/sheets/{index}/raster"),
    )
    .await
}

/// Extract through path A: region, regex and built-in extractors.
///
/// Field definitions come from the frontend and pass through unchanged; the
/// field builder lives there rather than in the backend.
#[tauri::command]
pub async fn extract(
    state: State<'_, AppState>,
    doc_id: String,
    fields: serde_json::Value,
    manual: Option<serde_json::Value>,
) -> BridgeResult<serde_json::Value> {
    send(
        &state,
        &format!("/documents/{doc_id}/extract"),
        serde_json::json!({
            "fields": fields,
            "manual": manual.unwrap_or_else(|| serde_json::json!({})),
        }),
    )
    .await
}

/// Extract for export, keeping values and provenance separate. `confirmed`
/// names values a person accepted in review without a location; without it
/// the sidecar leaves them out of the result.
#[tauri::command]
pub async fn export(
    state: State<'_, AppState>,
    doc_id: String,
    fields: serde_json::Value,
    manual: Option<serde_json::Value>,
    confirmed: Option<Vec<String>>,
) -> BridgeResult<serde_json::Value> {
    send(
        &state,
        &format!("/documents/{doc_id}/export"),
        serde_json::json!({
            "fields": fields,
            "manual": manual.unwrap_or_else(|| serde_json::json!({})),
            "confirmed": confirmed.unwrap_or_default(),
        }),
    )
    .await
}

#[tauri::command]
pub async fn sample_fields(state: State<'_, AppState>) -> BridgeResult<serde_json::Value> {
    fetch(&state, "/sample-fields").await
}

// --- Document types --------------------------------------------------------

#[tauri::command]
pub async fn document_types(state: State<'_, AppState>) -> BridgeResult<serde_json::Value> {
    fetch(&state, "/document-types").await
}

#[tauri::command]
pub async fn document_type(
    state: State<'_, AppState>,
    type_id: i64,
) -> BridgeResult<serde_json::Value> {
    fetch(&state, &format!("/document-types/{type_id}")).await
}

#[tauri::command]
pub async fn save_document_type(
    state: State<'_, AppState>,
    document_type: serde_json::Value,
) -> BridgeResult<serde_json::Value> {
    send(&state, "/document-types", document_type).await
}

#[tauri::command]
pub async fn delete_document_type(
    state: State<'_, AppState>,
    type_id: i64,
) -> BridgeResult<serde_json::Value> {
    remove(&state, &format!("/document-types/{type_id}")).await
}

#[tauri::command]
pub async fn close_document(
    state: State<'_, AppState>,
    doc_id: String,
) -> BridgeResult<serde_json::Value> {
    remove(&state, &format!("/documents/{doc_id}")).await
}

/// Raw file bytes for PDF.js.
///
/// PDF.js renders directly from bytes in the frontend, which is smoother than
/// server-rendered images at each zoom level and preserves text selection.
/// The sidecar renders only for OCR in stage 3.
#[tauri::command]
pub async fn document_bytes(
    state: State<'_, AppState>,
    doc_id: String,
) -> BridgeResult<tauri::ipc::Response> {
    let bytes = fetch_bytes(&state, &format!("/documents/{doc_id}/file")).await?;
    Ok(tauri::ipc::Response::new(bytes))
}

/// Render a page as PNG for images and as a fallback.
#[tauri::command]
pub async fn render_page(
    state: State<'_, AppState>,
    doc_id: String,
    page: usize,
    scale: f32,
) -> BridgeResult<tauri::ipc::Response> {
    let bytes = fetch_bytes(
        &state,
        &format!("/documents/{doc_id}/pages/{page}/render?scale={scale}"),
    )
    .await?;
    Ok(tauri::ipc::Response::new(bytes))
}

// --- Inbox -----------------------------------------------------------------

/// List what arrived in the watched folder.
#[tauri::command]
pub async fn inbox_entries(state: State<'_, AppState>) -> BridgeResult<serde_json::Value> {
    fetch(&state, "/inbox/entries").await
}

/// Read the watched folder, the active profile and the profiles to choose from.
#[tauri::command]
pub async fn inbox_settings(state: State<'_, AppState>) -> BridgeResult<serde_json::Value> {
    fetch(&state, "/inbox/settings").await
}

/// List every chosen folder; an entry names its import by id.
#[tauri::command]
pub async fn inbox_imports(state: State<'_, AppState>) -> BridgeResult<serde_json::Value> {
    fetch(&state, "/inbox/imports").await
}

/// Describe a pipeline profile in words. The name comes from the sidecar and is
/// checked here because it becomes part of a path.
#[tauri::command]
pub async fn pipeline_profile(
    state: State<'_, AppState>,
    name: String,
) -> BridgeResult<serde_json::Value> {
    if name.is_empty()
        || !name
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
    {
        return Err(BridgeError::technical(
            "pipeline-profile-unknown",
            "invalid profile name",
        ));
    }
    fetch(&state, &format!("/pipeline-profiles/{name}")).await
}

/// Choose a folder to watch, a profile, a retention period, or several. The sidecar refuses a
/// folder outside the read roots this shell passed at start.
#[tauri::command]
pub async fn choose_inbox_settings(
    state: State<'_, AppState>,
    folder: Option<String>,
    profile: Option<String>,
    retention_days: Option<u32>,
) -> BridgeResult<serde_json::Value> {
    send(
        &state,
        "/inbox/settings",
        serde_json::json!({
            "folder": folder,
            "profile": profile,
            "retention_days": retention_days,
        }),
    )
    .await
}

/// List the kinds of a pipeline profile with the values each one reads, for
/// the review of an inbox entry.
#[tauri::command]
pub async fn profile_kinds(
    state: State<'_, AppState>,
    profile: String,
) -> BridgeResult<serde_json::Value> {
    fetch(
        &state,
        &format!("/pipeline-profiles/{}/kinds", segment(&profile)),
    )
    .await
}

/// List every document kind with the values it reads, for Templates.
#[tauri::command]
pub async fn document_kinds(state: State<'_, AppState>) -> BridgeResult<serde_json::Value> {
    fetch(&state, "/document-kinds").await
}

/// Store the changed values of a kind as an override file; the next document read uses them.
#[tauri::command]
pub async fn change_kind_values(
    state: State<'_, AppState>,
    kind: String,
    values: serde_json::Value,
) -> BridgeResult<serde_json::Value> {
    send(
        &state,
        &format!("/document-kinds/{}/values", segment(&kind)),
        serde_json::json!({ "values": values }),
    )
    .await
}

/// Percent-encode a name for one path segment, so that `/`, `?` or `#` stay part of it.
fn segment(name: &str) -> String {
    name.bytes()
        .map(|b| match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                (b as char).to_string()
            }
            _ => format!("%{b:02X}"),
        })
        .collect()
}

/// Store what a person corrected on an entry: the kind, values, or both.
#[tauri::command]
pub async fn correct_inbox_entry(
    state: State<'_, AppState>,
    entry_id: i64,
    correction: serde_json::Value,
) -> BridgeResult<serde_json::Value> {
    send(
        &state,
        &format!("/inbox/entries/{entry_id}/correction"),
        correction,
    )
    .await
}

/// Store whether a possible duplicate is the same document as the entry it
/// points to, or a new one.
#[tauri::command]
pub async fn decide_duplicate(
    state: State<'_, AppState>,
    entry_id: i64,
    same: bool,
) -> BridgeResult<serde_json::Value> {
    send(
        &state,
        &format!("/inbox/entries/{entry_id}/duplicate-decision"),
        serde_json::json!({ "same": same }),
    )
    .await
}

/// Delete an entry with its values, corrections, job and job file. The
/// scanned file goes only when `delete_file` asks for it.
#[tauri::command]
pub async fn delete_inbox_entry(
    state: State<'_, AppState>,
    entry_id: i64,
    delete_file: bool,
) -> BridgeResult<serde_json::Value> {
    remove(
        &state,
        &format!("/inbox/entries/{entry_id}?delete_file={delete_file}"),
    )
    .await
}

/// Approve an entry. The sidecar refuses while a required value is open and
/// otherwise creates the one job of the entry.
#[tauri::command]
pub async fn approve_inbox_entry(
    state: State<'_, AppState>,
    entry_id: i64,
) -> BridgeResult<serde_json::Value> {
    send(
        &state,
        &format!("/inbox/entries/{entry_id}/approval"),
        serde_json::Value::Null,
    )
    .await
}

/// List the jobs with their states and transitions.
#[tauri::command]
pub async fn jobs(state: State<'_, AppState>) -> BridgeResult<serde_json::Value> {
    fetch(&state, "/jobs").await
}

/// Write the pending jobs of one customer as one hand-over file. Only a
/// person starts this; the sidecar returns the jobs in their new states.
#[tauri::command]
pub async fn run_hand_over(
    state: State<'_, AppState>,
    customer: String,
) -> BridgeResult<serde_json::Value> {
    send(
        &state,
        "/jobs/hand-over",
        serde_json::json!({ "customer": customer }),
    )
    .await
}

/// What a run for one customer would write now; the sidecar writes nothing.
#[tauri::command]
pub async fn preview_hand_over(
    state: State<'_, AppState>,
    customer: String,
) -> BridgeResult<serde_json::Value> {
    send(
        &state,
        "/jobs/hand-over/preview",
        serde_json::json!({ "customer": customer }),
    )
    .await
}

/// A person reports what importing the hand-over of one customer did:
/// imported, or failed with the reason the person typed.
#[tauri::command]
pub async fn report_import(
    state: State<'_, AppState>,
    customer: String,
    imported: bool,
    reason: String,
) -> BridgeResult<serde_json::Value> {
    send(
        &state,
        "/jobs/hand-over/result",
        serde_json::json!({ "customer": customer, "imported": imported, "reason": reason }),
    )
    .await
}

/// Release a failed job again. The id comes from the sidecar and is checked
/// here because it becomes part of a path.
#[tauri::command]
pub async fn release_job(
    state: State<'_, AppState>,
    job_id: String,
) -> BridgeResult<serde_json::Value> {
    if !job_id.chars().all(|c| c.is_ascii_alphanumeric()) {
        return Err(BridgeError::technical("job-unknown", "invalid job id"));
    }
    send(
        &state,
        &format!("/jobs/{job_id}/release"),
        serde_json::Value::Null,
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::{problem, segment};

    #[test]
    fn a_refused_approval_hands_its_items_to_the_frontend() {
        let json = serde_json::json!({
            "type": "https://substrakt.local/problems/approval-refused",
            "title": "Approval is not possible",
            "key": "approval-refused",
            "reason": "hand-over-not-possible",
            "items": ["kind_not_handed_over", "value_fits_field:policy_number"],
        });
        let error = problem(409, &json);
        assert_eq!(error.reason.as_deref(), Some("hand-over-not-possible"));
        assert_eq!(
            error.items,
            ["kind_not_handed_over", "value_fits_field:policy_number"]
        );
        assert!(problem(500, &serde_json::Value::Null).items.is_empty());
    }

    #[test]
    fn profile_name_stays_one_path_segment() {
        assert_eq!(segment("broker_scans-1.0~"), "broker_scans-1.0~");
        assert_eq!(segment("a/../b?c#d"), "a%2F..%2Fb%3Fc%23d");
        assert_eq!(segment("Prüfung"), "Pr%C3%BCfung");
    }
}
