#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{ErrorKind, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use hmac::{Hmac, Mac};
use rand::{rngs::OsRng, RngCore};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use tauri::{Emitter, Manager};
use tauri_plugin_shell::{process::CommandChild, process::CommandEvent, ShellExt};

const BRIDGE_HOST: &str = "127.0.0.1";
const BRIDGE_PORT: &str = "7420";
const BRIDGE_ADDRESS: &str = "127.0.0.1:7420";
const BRIDGE_IDENTITY_PATH: &str = "/health/identity";
const MIN_BRIDGE_TOKEN_BYTES: usize = 32;
const MAX_BRIDGE_TOKEN_CHARS: usize = 512;
// This includes cold one-file extraction, imports and authenticated readiness.
// A measured Windows restart spent ~13s extracting before Python started;
// 20s incorrectly rejected a healthy payload before it could bind. Keep a
// bounded cold-start allowance without relaxing identity or port ownership.
const BRIDGE_STARTUP_TIMEOUT: Duration = Duration::from_secs(60);
const BRIDGE_PROBE_TIMEOUT: Duration = Duration::from_millis(1_500);
const BRIDGE_RETRY_INTERVAL: Duration = Duration::from_millis(100);
const BRIDGE_IDENTITY_RETRY_ATTEMPTS: usize = 6;
const BRIDGE_IDENTITY_MISS_LIMIT: u8 = 10;
const PET_NATIVE_DISMISSED_EVENT: &str = "pex-pet-native-dismissed";
type HmacSha256 = Hmac<Sha256>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum WindowCloseAction {
    ExitApplication,
    PersistAndHidePet,
    HideAuxiliary,
}

fn window_close_action(label: &str) -> WindowCloseAction {
    match label {
        "main" => WindowCloseAction::ExitApplication,
        "pet" => WindowCloseAction::PersistAndHidePet,
        _ => WindowCloseAction::HideAuxiliary,
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
enum BridgeBootstrapPhase {
    Starting,
    Ready,
    Failed,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
enum BridgeSource {
    NotReady,
    OwnedSidecar,
    UnverifiedPortOwner,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct BridgeBootstrapStatus {
    phase: BridgeBootstrapPhase,
    code: Option<String>,
    message: String,
    retryable: bool,
    source: BridgeSource,
    attempt: u64,
}

impl BridgeBootstrapStatus {
    fn starting(attempt: u64) -> Self {
        Self {
            phase: BridgeBootstrapPhase::Starting,
            code: None,
            message: "Starting the authenticated local PEX bridge.".to_string(),
            retryable: false,
            source: BridgeSource::NotReady,
            attempt,
        }
    }

    fn ready(attempt: u64) -> Self {
        Self {
            phase: BridgeBootstrapPhase::Ready,
            code: None,
            message: "The authenticated local PEX bridge is ready.".to_string(),
            retryable: false,
            source: BridgeSource::OwnedSidecar,
            attempt,
        }
    }

    fn failed(
        attempt: u64,
        code: &str,
        message: &str,
        retryable: bool,
        source: BridgeSource,
    ) -> Self {
        Self {
            phase: BridgeBootstrapPhase::Failed,
            code: Some(code.to_string()),
            message: message.to_string(),
            retryable,
            source,
            attempt,
        }
    }

    fn unavailable() -> Self {
        Self::failed(
            0,
            "desktop_state_unavailable",
            "PEX could not read its local bridge startup state.",
            false,
            BridgeSource::NotReady,
        )
    }
}

struct BridgeRuntimeInner {
    status: BridgeBootstrapStatus,
    operator_token: Option<String>,
    child: Option<CommandChild>,
}

struct BridgeRuntime(Mutex<BridgeRuntimeInner>, tokio::sync::Mutex<()>);

impl Default for BridgeRuntime {
    fn default() -> Self {
        Self(
            Mutex::new(BridgeRuntimeInner {
                status: BridgeBootstrapStatus::failed(
                    0,
                    "not_started",
                    "The local PEX bridge has not started yet.",
                    true,
                    BridgeSource::NotReady,
                ),
                operator_token: None,
                child: None,
            }),
            tokio::sync::Mutex::new(()),
        )
    }
}

impl BridgeRuntime {
    fn status(&self) -> BridgeBootstrapStatus {
        self.0
            .lock()
            .map(|inner| inner.status.clone())
            .unwrap_or_else(|_| BridgeBootstrapStatus::unavailable())
    }

    fn begin_attempt(&self) -> Option<u64> {
        let mut inner = self.0.lock().ok()?;
        if matches!(
            inner.status.phase,
            BridgeBootstrapPhase::Starting | BridgeBootstrapPhase::Ready
        ) {
            return None;
        }
        if !inner.status.retryable {
            return None;
        }
        let attempt = inner.status.attempt.saturating_add(1);
        inner.status = BridgeBootstrapStatus::starting(attempt);
        Some(attempt)
    }

    fn token_for_attempt(&self, attempt: u64) -> Result<String, String> {
        let mut inner = self
            .0
            .lock()
            .map_err(|_| "PEX bridge process state is unavailable".to_string())?;
        if inner.status.attempt != attempt || inner.status.phase != BridgeBootstrapPhase::Starting {
            return Err("PEX bridge startup attempt is no longer current".to_string());
        }
        if let Some(token) = &inner.operator_token {
            return Ok(token.clone());
        }
        let auth = BridgeAuth::generate()?;
        inner.operator_token = Some(auth.operator_token.clone());
        Ok(auth.operator_token)
    }

    fn set_owned_child(&self, attempt: u64, child: CommandChild) -> Result<(), CommandChild> {
        let Ok(mut inner) = self.0.lock() else {
            return Err(child);
        };
        if inner.status.attempt != attempt
            || inner.status.phase != BridgeBootstrapPhase::Starting
            || inner.child.is_some()
        {
            return Err(child);
        }
        inner.child = Some(child);
        Ok(())
    }

    fn finish_ready(&self, attempt: u64) {
        if let Ok(mut inner) = self.0.lock() {
            if inner.status.attempt == attempt
                && inner.status.phase == BridgeBootstrapPhase::Starting
            {
                inner.status = BridgeBootstrapStatus::ready(attempt);
            }
        }
    }

    fn finish_failed(
        &self,
        attempt: u64,
        code: &str,
        message: &str,
        retryable: bool,
        source: BridgeSource,
    ) -> Option<CommandChild> {
        let mut inner = self.0.lock().ok()?;
        if inner.status.attempt != attempt
            || !matches!(
                inner.status.phase,
                BridgeBootstrapPhase::Starting | BridgeBootstrapPhase::Ready
            )
        {
            return None;
        }
        inner.status = BridgeBootstrapStatus::failed(attempt, code, message, retryable, source);
        inner.child.take()
    }

    fn ready_token(&self) -> Option<(u64, String)> {
        let inner = self.0.lock().ok()?;
        if inner.status.phase != BridgeBootstrapPhase::Ready {
            return None;
        }
        Some((inner.status.attempt, inner.operator_token.clone()?))
    }

    fn take_child(&self) -> Option<CommandChild> {
        self.0.lock().ok()?.child.take()
    }
}

struct BridgeAuth {
    operator_token: String,
}

impl BridgeAuth {
    fn generate() -> Result<Self, String> {
        let mut token_bytes = [0_u8; 48];
        OsRng
            .try_fill_bytes(&mut token_bytes)
            .map_err(|_| "PEX operator token generation failed".to_string())?;
        let operator_token = normalize_bridge_token(&hex::encode(token_bytes))?;
        Ok(Self { operator_token })
    }
}

#[derive(Debug, PartialEq, Eq)]
enum BridgePortState {
    Free,
    Trusted,
    OccupiedUntrusted,
}

#[cfg(test)]
fn bridge_identity_proof(token: &str, challenge: &str) -> Result<String, String> {
    let mut mac = HmacSha256::new_from_slice(token.as_bytes())
        .map_err(|_| "PEX bridge token is invalid".to_string())?;
    mac.update(challenge.as_bytes());
    Ok(hex::encode(mac.finalize().into_bytes()))
}

fn bridge_identity_proof_matches(token: &str, challenge: &str, proof: &str) -> bool {
    if proof.len() != 64
        || !proof
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return false;
    }
    let Ok(decoded) = hex::decode(proof) else {
        return false;
    };
    let Ok(mut mac) = HmacSha256::new_from_slice(token.as_bytes()) else {
        return false;
    };
    mac.update(challenge.as_bytes());
    mac.verify_slice(&decoded).is_ok()
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct BridgeIdentityResponse {
    ok: bool,
    service: String,
    challenge: String,
    proof: String,
}

fn is_pex_identity_response(response: &[u8], challenge: &str, token: &str) -> bool {
    let Ok(response) = std::str::from_utf8(response) else {
        return false;
    };
    let Some((headers, body)) = response.split_once("\r\n\r\n") else {
        return false;
    };
    let mut header_lines = headers.split("\r\n");
    let Some(status) = header_lines.next() else {
        return false;
    };
    if status != "HTTP/1.1 200 OK" {
        return false;
    }
    let mut content_length = None;
    let mut content_type = None;
    for line in header_lines {
        if line.is_empty()
            || line.starts_with([' ', '\t'])
            || line.contains(['\r', '\n'])
            || line
                .bytes()
                .any(|byte| (byte < 0x20 && byte != b'\t') || byte == 0x7f)
        {
            return false;
        }
        let Some((name, value)) = line.split_once(':') else {
            return false;
        };
        if name.is_empty() || name.trim() != name {
            return false;
        }
        if name.eq_ignore_ascii_case("transfer-encoding") {
            return false;
        }
        if name.eq_ignore_ascii_case("content-length") {
            if content_length.is_some() {
                return false;
            }
            let Ok(parsed) = value.trim().parse::<usize>() else {
                return false;
            };
            content_length = Some(parsed);
        }
        if name.eq_ignore_ascii_case("content-type") {
            if content_type.is_some() {
                return false;
            }
            content_type = Some(value.trim());
        }
    }
    if content_length != Some(body.len())
        || !content_type.is_some_and(|value| value.eq_ignore_ascii_case("application/json"))
    {
        return false;
    }
    serde_json::from_str::<BridgeIdentityResponse>(body)
        .ok()
        .is_some_and(|payload| {
            payload.ok
                && payload.service == "pex-bridge"
                && payload.challenge == challenge
                && bridge_identity_proof_matches(token, challenge, &payload.proof)
        })
}

fn bridge_is_healthy_with_token(token: &str) -> bool {
    let Ok(address) = bridge_address() else {
        return false;
    };
    bridge_is_healthy_at(&address, token)
}

fn bridge_identity_survives_transient_io(token: &str) -> bool {
    for attempt in 0..BRIDGE_IDENTITY_RETRY_ATTEMPTS {
        if bridge_is_healthy_with_token(token) {
            return true;
        }
        if attempt + 1 < BRIDGE_IDENTITY_RETRY_ATTEMPTS {
            std::thread::sleep(BRIDGE_RETRY_INTERVAL);
        }
    }
    false
}

fn bridge_is_healthy_at(address: &SocketAddr, token: &str) -> bool {
    bridge_is_healthy_at_until(address, token, Instant::now() + BRIDGE_PROBE_TIMEOUT)
}

fn remaining_timeout(deadline: Instant, maximum: Duration) -> Option<Duration> {
    let remaining = deadline.checked_duration_since(Instant::now())?;
    if remaining.is_zero() {
        return None;
    }
    Some(remaining.min(maximum))
}

fn bridge_is_healthy_at_until(address: &SocketAddr, token: &str, deadline: Instant) -> bool {
    let mut challenge_bytes = [0_u8; 32];
    if OsRng.try_fill_bytes(&mut challenge_bytes).is_err() {
        return false;
    }
    let challenge = hex::encode(challenge_bytes);
    let Some(connect_timeout) = remaining_timeout(deadline, Duration::from_millis(350)) else {
        return false;
    };
    let Ok(mut stream) = TcpStream::connect_timeout(address, connect_timeout) else {
        return false;
    };
    let Some(io_timeout) = remaining_timeout(deadline, Duration::from_millis(750)) else {
        return false;
    };
    let timeout = Some(io_timeout);
    if stream.set_read_timeout(timeout).is_err() || stream.set_write_timeout(timeout).is_err() {
        return false;
    }
    let request = format!(
        "GET {BRIDGE_IDENTITY_PATH}?challenge={challenge} HTTP/1.1\r\nHost: {address}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }

    let mut response = Vec::with_capacity(1_024);
    let mut chunk = [0_u8; 4_096];
    loop {
        let Some(read_timeout) = remaining_timeout(deadline, Duration::from_millis(750)) else {
            return false;
        };
        if stream.set_read_timeout(Some(read_timeout)).is_err() {
            return false;
        }
        match stream.read(&mut chunk) {
            Ok(0) => break,
            Ok(count) => {
                response.extend_from_slice(&chunk[..count]);
                if response.len() > 64 * 1_024 {
                    return false;
                }
                // A complete, strictly parsed, token-bound response is enough;
                // do not make correctness depend on when an HTTP server closes
                // the connection after sending the declared body.
                if is_pex_identity_response(&response, &challenge, token) {
                    return true;
                }
            }
            Err(error) if matches!(error.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {
                break;
            }
            Err(_) => return false,
        }
    }
    false
}

fn bridge_port_state_at(address: &SocketAddr, token: &str) -> Result<BridgePortState, String> {
    bridge_port_state_at_until(address, token, Instant::now() + BRIDGE_PROBE_TIMEOUT)
}

fn bridge_port_state_at_until(
    address: &SocketAddr,
    token: &str,
    deadline: Instant,
) -> Result<BridgePortState, String> {
    // Establish an availability candidate by binding first. On some Windows hosts a connect to
    // an unused loopback port is silently dropped until timeout instead of
    // returning WSAECONNREFUSED. Windows uses SO_EXCLUSIVEADDRUSE so a
    // reuse-enabled or untrusted listener cannot be mistaken for an available
    // candidate. The spawned bridge must still prove token-bound identity.
    match bind_bridge_probe(address) {
        Ok(()) => {
            return Ok(BridgePortState::Free);
        }
        Err(error) if error.kind() == ErrorKind::AddrInUse => {}
        Err(_) => {
            return Err("PEX bridge port could not be bound safely".to_string());
        }
    }
    let timeout = remaining_timeout(deadline, Duration::from_millis(350))
        .ok_or_else(|| "PEX bridge port state check timed out".to_string())?;
    match TcpStream::connect_timeout(address, timeout) {
        Ok(stream) => {
            drop(stream);
            if bridge_is_healthy_at_until(address, token, deadline) {
                Ok(BridgePortState::Trusted)
            } else {
                Ok(BridgePortState::OccupiedUntrusted)
            }
        }
        Err(error) if error.kind() == ErrorKind::ConnectionRefused => Ok(BridgePortState::Free),
        Err(_) => Err("PEX bridge port state could not be established safely".to_string()),
    }
}

#[cfg(windows)]
fn bind_bridge_probe(address: &SocketAddr) -> std::io::Result<()> {
    use socket2::{Domain, Protocol, Socket, Type};
    use std::os::windows::io::AsRawSocket;
    use windows_sys::Win32::Networking::WinSock::{
        setsockopt, SOCKET_ERROR, SOL_SOCKET, SO_EXCLUSIVEADDRUSE,
    };

    let socket = Socket::new(
        Domain::for_address(*address),
        Type::STREAM,
        Some(Protocol::TCP),
    )?;
    let exclusive: i32 = 1;
    let result = unsafe {
        setsockopt(
            socket.as_raw_socket() as usize,
            SOL_SOCKET,
            SO_EXCLUSIVEADDRUSE,
            (&exclusive as *const i32).cast(),
            std::mem::size_of::<i32>() as i32,
        )
    };
    if result == SOCKET_ERROR {
        return Err(std::io::Error::last_os_error());
    }
    socket.bind(&(*address).into())?;
    socket.listen(1)?;
    Ok(())
}

#[cfg(not(windows))]
fn bind_bridge_probe(address: &SocketAddr) -> std::io::Result<()> {
    let listener = std::net::TcpListener::bind(address)?;
    drop(listener);
    Ok(())
}

fn bridge_port_is_free_for_owned_launch(state: &BridgePortState) -> bool {
    matches!(state, BridgePortState::Free)
}

fn command_event_is_terminal(event: &CommandEvent) -> bool {
    matches!(event, CommandEvent::Terminated(_) | CommandEvent::Error(_))
}

fn bridge_address() -> Result<SocketAddr, String> {
    let address = BRIDGE_ADDRESS
        .parse::<SocketAddr>()
        .map_err(|_| "PEX bridge address is invalid".to_string())?;
    if !address.ip().is_loopback() {
        return Err("PEX bridge sidecar must use a loopback address".to_string());
    }
    Ok(address)
}

fn bridge_sidecar_args() -> [&'static str; 4] {
    ["--host", BRIDGE_HOST, "--port", BRIDGE_PORT]
}

fn stop_owned_bridge(app: &tauri::AppHandle) {
    let Some(state) = app.try_state::<BridgeRuntime>() else {
        return;
    };
    if let Some(child) = state.take_child() {
        let _ = child.kill();
    }
}

#[tauri::command]
async fn bridge_token(
    app: tauri::AppHandle,
    runtime: tauri::State<'_, BridgeRuntime>,
) -> Result<String, String> {
    // The UI can start several authenticated reads at once. Serialize their
    // pre-send identity proofs so a healthy single-process bridge is not
    // rejected because a burst of raw probes races its small listen backlog.
    let _verification = runtime.1.lock().await;
    let (attempt, token) = runtime
        .ready_token()
        .ok_or_else(|| "PEX bridge is not ready".to_string())?;
    let token_for_probe = token.clone();
    let verified = tauri::async_runtime::spawn_blocking(move || {
        bridge_identity_survives_transient_io(&token_for_probe)
    })
    .await
    .map_err(|_| "PEX bridge identity check could not complete".to_string())?;
    if verified {
        if runtime
            .ready_token()
            .is_some_and(|(current_attempt, current_token)| {
                current_attempt == attempt && current_token == token
            })
        {
            return Ok(token);
        }
        return Err(
            "PEX bridge startup generation changed during identity verification".to_string(),
        );
    }
    fail_bridge_attempt(
        &app,
        attempt,
        "bridge_identity_lost",
        "The owned PEX bridge stopped proving its identity.",
        true,
        BridgeSource::OwnedSidecar,
    );
    Err("PEX bridge identity could not be verified".to_string())
}

#[tauri::command]
fn bridge_bootstrap_status(runtime: tauri::State<'_, BridgeRuntime>) -> BridgeBootstrapStatus {
    runtime.status()
}

#[tauri::command]
fn retry_bridge(app: tauri::AppHandle) -> BridgeBootstrapStatus {
    schedule_bridge_bootstrap(&app)
}

fn fail_bridge_attempt(
    app: &tauri::AppHandle,
    attempt: u64,
    code: &str,
    message: &str,
    retryable: bool,
    source: BridgeSource,
) {
    let runtime = app.state::<BridgeRuntime>();
    if let Some(child) = runtime.finish_failed(attempt, code, message, retryable, source) {
        let _ = child.kill();
    }
    let current = runtime.status();
    if current.attempt == attempt && current.phase == BridgeBootstrapPhase::Failed {
        if let Some(pet) = app.get_webview_window("pet") {
            let _ = pet.hide();
        }
    }
}

fn monitor_owned_bridge(
    app: tauri::AppHandle,
    attempt: u64,
    token: String,
    mut events: tauri::async_runtime::Receiver<CommandEvent>,
) {
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            if command_event_is_terminal(&event) {
                break;
            }
            // Stdout and stderr are intentionally discarded. Bridge output can
            // contain private workspace or provider diagnostics.
        }
        // PyInstaller's one-file bootloader can hand execution to its extracted
        // payload before the shell plugin reports either a terminal event or
        // channel EOF. Keep authority only when that payload proves the token.
        let token_for_probe = token.clone();
        let verified = tauri::async_runtime::spawn_blocking(move || {
            bridge_identity_survives_transient_io(&token_for_probe)
        })
        .await
        .unwrap_or(false);
        if verified {
            tauri::async_runtime::spawn_blocking(move || {
                monitor_verified_bridge_identity(app, attempt, token)
            });
            return;
        }
        fail_bridge_attempt(
            &app,
            attempt,
            "bridge_process_stopped",
            "The owned PEX bridge event channel closed.",
            true,
            BridgeSource::OwnedSidecar,
        );
    });
}

fn monitor_verified_bridge_identity(app: tauri::AppHandle, attempt: u64, token: String) {
    let mut consecutive_misses = 0_u8;
    loop {
        std::thread::sleep(Duration::from_secs(1));
        let current = app.state::<BridgeRuntime>().status();
        if current.attempt != attempt || current.phase != BridgeBootstrapPhase::Ready {
            return;
        }
        if bridge_is_healthy_with_token(&token) {
            consecutive_misses = 0;
            continue;
        }
        consecutive_misses = consecutive_misses.saturating_add(1);
        if consecutive_misses < BRIDGE_IDENTITY_MISS_LIMIT {
            continue;
        }
        fail_bridge_attempt(
            &app,
            attempt,
            "bridge_process_stopped",
            "The owned PEX bridge stopped proving its identity.",
            true,
            BridgeSource::OwnedSidecar,
        );
        return;
    }
}

fn run_bridge_bootstrap(app: tauri::AppHandle, attempt: u64) {
    let deadline = Instant::now() + BRIDGE_STARTUP_TIMEOUT;
    let token = match app.state::<BridgeRuntime>().token_for_attempt(attempt) {
        Ok(token) => token,
        Err(_) => {
            fail_bridge_attempt(
                &app,
                attempt,
                "token_generation_failed",
                "PEX could not create its in-memory bridge credential.",
                true,
                BridgeSource::NotReady,
            );
            return;
        }
    };
    let address = match bridge_address() {
        Ok(address) => address,
        Err(_) => {
            fail_bridge_attempt(
                &app,
                attempt,
                "bridge_address_invalid",
                "PEX could not validate its loopback bridge address.",
                false,
                BridgeSource::NotReady,
            );
            return;
        }
    };

    let port_state = bridge_port_state_at_until(&address, &token, deadline);
    match port_state {
        Ok(state) if !bridge_port_is_free_for_owned_launch(&state) => {
            // A fresh desktop credential is known only by a child this process
            // owns. Before spawn there is no owned child, so every occupied port
            // is an unverified owner and must never be reused or killed.
            fail_bridge_attempt(
                &app,
                attempt,
                "port_occupied_untrusted",
                "Port 7420 is in use by a process that cannot be verified as this PEX bridge.",
                true,
                BridgeSource::UnverifiedPortOwner,
            );
            return;
        }
        Err(_) => {
            fail_bridge_attempt(
                &app,
                attempt,
                "port_check_failed",
                "PEX could not safely establish whether its loopback bridge port is available.",
                true,
                BridgeSource::NotReady,
            );
            return;
        }
        Ok(_) => {}
    }

    // Recheck immediately before launch. The single-instance plugin serializes
    // PEX desktop launches; this second check also fails closed if another local
    // process claimed the fixed port during preparation.
    match bridge_port_state_at_until(&address, &token, deadline) {
        Ok(state) if bridge_port_is_free_for_owned_launch(&state) => {}
        Ok(_) => {
            fail_bridge_attempt(
                &app,
                attempt,
                "port_occupied_untrusted",
                "Port 7420 was claimed by a process that cannot be verified as this PEX bridge.",
                true,
                BridgeSource::UnverifiedPortOwner,
            );
            return;
        }
        Err(_) => {
            fail_bridge_attempt(
                &app,
                attempt,
                "port_check_failed",
                "PEX could not safely recheck its loopback bridge port.",
                true,
                BridgeSource::NotReady,
            );
            return;
        }
    }

    let command = match app.shell().sidecar("pex-bridge") {
        Ok(command) => command,
        Err(_) => {
            fail_bridge_attempt(
                &app,
                attempt,
                "sidecar_missing",
                "The packaged PEX bridge executable is unavailable.",
                false,
                BridgeSource::NotReady,
            );
            return;
        }
    };
    let spawned = command
        // Pin the release sidecar to authenticated loopback operation. The
        // bearer remains only in this process and its owned child environment.
        .args(bridge_sidecar_args())
        .env("PEX_HOST", BRIDGE_HOST)
        .env("PEX_PORT", BRIDGE_PORT)
        .env("PEX_REQUIRE_AUTH", "true")
        .env("PEX_TOKEN", &token)
        .env("PEX_DESKTOP_PARENT_PID", std::process::id().to_string())
        .spawn();
    let (mut events, child) = match spawned {
        Ok(spawned) => spawned,
        Err(_) => {
            fail_bridge_attempt(
                &app,
                attempt,
                "sidecar_spawn_failed",
                "PEX could not start its packaged local bridge.",
                true,
                BridgeSource::NotReady,
            );
            return;
        }
    };
    if let Err(child) = app.state::<BridgeRuntime>().set_owned_child(attempt, child) {
        let _ = child.kill();
        return;
    }

    loop {
        for _ in 0..64 {
            if Instant::now() >= deadline {
                fail_bridge_attempt(
                    &app,
                    attempt,
                    "identity_timeout",
                    "The owned PEX bridge did not prove its identity before the startup deadline.",
                    true,
                    BridgeSource::OwnedSidecar,
                );
                return;
            }
            match events.try_recv() {
                Ok(event) if command_event_is_terminal(&event) => {
                    fail_bridge_attempt(
                        &app,
                        attempt,
                        "sidecar_exited_early",
                        "The owned PEX bridge exited before it became ready.",
                        true,
                        BridgeSource::OwnedSidecar,
                    );
                    return;
                }
                Ok(CommandEvent::Stdout(_) | CommandEvent::Stderr(_)) => {
                    // Drain a bounded batch without exposing private diagnostics.
                }
                Ok(_) => {}
                Err(_) if events.is_closed() => {
                    fail_bridge_attempt(
                        &app,
                        attempt,
                        "sidecar_exited_early",
                        "The owned PEX bridge event channel closed before startup completed.",
                        true,
                        BridgeSource::OwnedSidecar,
                    );
                    return;
                }
                Err(_) => break,
            }
        }
        if bridge_is_healthy_at_until(&address, &token, deadline) {
            app.state::<BridgeRuntime>().finish_ready(attempt);
            monitor_owned_bridge(app, attempt, token, events);
            return;
        }
        let Some(remaining) = deadline.checked_duration_since(Instant::now()) else {
            fail_bridge_attempt(
                &app,
                attempt,
                "identity_timeout",
                "The owned PEX bridge did not prove its identity before the startup deadline.",
                true,
                BridgeSource::OwnedSidecar,
            );
            return;
        };
        if remaining.is_zero() {
            fail_bridge_attempt(
                &app,
                attempt,
                "identity_timeout",
                "The owned PEX bridge did not prove its identity before the startup deadline.",
                true,
                BridgeSource::OwnedSidecar,
            );
            return;
        }
        std::thread::sleep(remaining.min(BRIDGE_RETRY_INTERVAL));
    }
}

fn schedule_bridge_bootstrap(app: &tauri::AppHandle) -> BridgeBootstrapStatus {
    let runtime = app.state::<BridgeRuntime>();
    if let Some(attempt) = runtime.begin_attempt() {
        if let Some(pet) = app.get_webview_window("pet") {
            let _ = pet.hide();
        }
        let handle = app.clone();
        tauri::async_runtime::spawn_blocking(move || run_bridge_bootstrap(handle, attempt));
    }
    runtime.status()
}

fn normalize_bridge_token(raw: &str) -> Result<String, String> {
    let token = raw.trim();
    if token.is_empty() {
        return Err("PEX bridge token is empty; restart the bridge".to_string());
    }
    if !(MIN_BRIDGE_TOKEN_BYTES..=MAX_BRIDGE_TOKEN_CHARS).contains(&token.len())
        || !token.bytes().all(|byte| (0x21..=0x7e).contains(&byte))
    {
        return Err("PEX bridge token is invalid; restart the bridge".to_string());
    }
    Ok(token.to_string())
}

fn trusted_webview_navigation(url: &tauri::Url) -> bool {
    if url.query().is_some() || !url.username().is_empty() || url.password().is_some() {
        return false;
    }
    match (url.scheme(), url.host_str(), url.port_or_known_default()) {
        ("tauri", Some("localhost"), _) if url.port().is_none() => true,
        ("http", Some("tauri.localhost"), Some(80)) => true,
        ("https", Some("tauri.localhost"), Some(443)) => true,
        ("http", Some("localhost" | "127.0.0.1"), Some(1420)) if cfg!(debug_assertions) => true,
        _ => false,
    }
}

fn navigation_guard<R: tauri::Runtime>() -> tauri::plugin::TauriPlugin<R> {
    tauri::plugin::Builder::new("pex-navigation-guard")
        .on_navigation(|_, url| trusted_webview_navigation(url))
        .build()
}

fn main() {
    tauri::Builder::default()
        // This plugin must remain first: a second desktop activation focuses the
        // existing command surface and exits before it can probe or spawn a bridge.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(navigation_guard())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            bridge_token,
            bridge_bootstrap_status,
            retry_bridge
        ])
        .setup(|app| {
            app.manage(BridgeRuntime::default());
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.show();
            }
            if let Some(pet) = app.get_webview_window("pet") {
                let _ = pet.set_background_color(Some(tauri::window::Color(0, 0, 0, 0)));
            }
            // Startup is deliberately off the setup/UI thread. Expected bridge
            // failures become visible typed state instead of aborting hidden setup.
            schedule_bridge_bootstrap(app.handle());
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                match window_close_action(window.label()) {
                    WindowCloseAction::PersistAndHidePet => {
                        api.prevent_close();
                        let _ = window.app_handle().emit(PET_NATIVE_DISMISSED_EVENT, ());
                        let _ = window.hide();
                    }
                    WindowCloseAction::HideAuxiliary => {
                        api.prevent_close();
                        let _ = window.hide();
                    }
                    WindowCloseAction::ExitApplication => {
                        stop_owned_bridge(window.app_handle());
                        window.app_handle().exit(0);
                    }
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building PEX desktop")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                stop_owned_bridge(app);
            }
        });
}

#[cfg(test)]
mod tests {
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::sync::Arc;
    use std::thread;
    use std::time::{Duration, Instant};

    use super::{
        bridge_address, bridge_identity_proof, bridge_port_is_free_for_owned_launch,
        bridge_port_state_at, bridge_sidecar_args, command_event_is_terminal,
        is_pex_identity_response, normalize_bridge_token, remaining_timeout,
        trusted_webview_navigation, window_close_action, BridgeAuth, BridgeBootstrapPhase,
        BridgePortState, BridgeRuntime, BridgeSource, WindowCloseAction, MAX_BRIDGE_TOKEN_CHARS,
    };

    #[test]
    fn pet_native_close_persists_dismissal_without_changing_main_exit() {
        assert_eq!(
            window_close_action("pet"),
            WindowCloseAction::PersistAndHidePet
        );
        assert_eq!(
            window_close_action("main"),
            WindowCloseAction::ExitApplication
        );
        assert_eq!(
            window_close_action("other"),
            WindowCloseAction::HideAuxiliary
        );
    }
    use tauri_plugin_shell::process::CommandEvent;

    fn identity_response(body: &str, extra_headers: &str) -> Vec<u8> {
        format!(
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\n{extra_headers}\r\n{body}",
            body.len()
        )
        .into_bytes()
    }

    #[test]
    fn accepts_only_the_nonce_bound_pex_identity_contract() {
        let challenge = "ab".repeat(32);
        let token = "local-test-token-that-is-at-least-32";
        let proof = bridge_identity_proof(token, &challenge).unwrap();
        let body = format!(
            "{{\"ok\":true,\"service\":\"pex-bridge\",\"challenge\":\"{challenge}\",\"proof\":\"{proof}\"}}"
        );
        let response = identity_response(&body, "");
        assert!(is_pex_identity_response(&response, &challenge, token));
        assert!(!is_pex_identity_response(
            &response,
            &"cd".repeat(32),
            token
        ));
        assert!(!is_pex_identity_response(
            &response,
            &challenge,
            "different-token-that-is-also-long-enough"
        ));
        assert!(!is_pex_identity_response(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 34\r\n\r\n{\"ok\":true,\"service\":\"pex-bridge\"}",
            &challenge,
            token
        ));

        let unknown = body.replacen("{", "{\"extra\":1,", 1);
        assert!(!is_pex_identity_response(
            &identity_response(&unknown, ""),
            &challenge,
            token
        ));
        let duplicate = body.replacen("{", "{\"ok\":true,", 1);
        assert!(!is_pex_identity_response(
            &identity_response(&duplicate, ""),
            &challenge,
            token
        ));
        assert!(!is_pex_identity_response(
            &identity_response(&body, "Content-Length: 1\r\n"),
            &challenge,
            token
        ));
        assert!(!is_pex_identity_response(
            &identity_response(&body, "Transfer-Encoding: chunked\r\n"),
            &challenge,
            token
        ));
        assert!(!is_pex_identity_response(
            &identity_response(&body, "Content-Type: application/json\r\n"),
            &challenge,
            token
        ));
        let no_content_type = format!(
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\n\r\n{body}",
            body.len()
        );
        assert!(!is_pex_identity_response(
            no_content_type.as_bytes(),
            &challenge,
            token
        ));
        let http_10 = String::from_utf8(identity_response(&body, ""))
            .unwrap()
            .replacen("HTTP/1.1", "HTTP/1.0", 1);
        assert!(!is_pex_identity_response(
            http_10.as_bytes(),
            &challenge,
            token
        ));
        let mut trailing = response;
        trailing.push(b'x');
        assert!(!is_pex_identity_response(&trailing, &challenge, token));
    }

    #[test]
    fn sidecar_launch_is_pinned_to_loopback() {
        let address = bridge_address().expect("fixed bridge address should parse");
        assert!(address.ip().is_loopback());
        assert_eq!(
            bridge_sidecar_args(),
            ["--host", "127.0.0.1", "--port", "7420"]
        );
        assert!(bridge_sidecar_args()
            .iter()
            .all(|argument| !argument.contains("token")));
    }

    #[test]
    fn live_identity_probe_accepts_fragmented_proof_without_waiting_for_eof() {
        let token = "local-test-token-that-is-at-least-32";
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let (release, released) = std::sync::mpsc::channel();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(2)))
                .unwrap();
            stream
                .set_write_timeout(Some(Duration::from_secs(2)))
                .unwrap();
            let mut request = Vec::new();
            while !request.ends_with(b"\r\n\r\n") {
                assert!(request.len() < 4096);
                let mut byte = [0_u8; 1];
                stream.read_exact(&mut byte).unwrap();
                request.push(byte[0]);
            }
            let request = String::from_utf8(request).unwrap();
            assert!(!request.contains(token));
            let challenge = request
                .split("challenge=")
                .nth(1)
                .unwrap()
                .split_whitespace()
                .next()
                .unwrap();
            let proof = bridge_identity_proof(token, challenge).unwrap();
            let body = format!(
                "{{\"ok\":true,\"service\":\"pex-bridge\",\"challenge\":\"{challenge}\",\"proof\":\"{proof}\"}}"
            );
            let response = identity_response(&body, "");
            let split = response.len() - 1;
            stream.write_all(&response[..split]).unwrap();
            thread::sleep(Duration::from_millis(20));
            stream.write_all(&response[split..]).unwrap();
            // Keep the connection alive until the caller has returned. The
            // authenticated Content-Length body, not EOF, must establish ready.
            let _ = released.recv_timeout(Duration::from_secs(3));
        });
        let healthy = super::bridge_is_healthy_at(&address, token);
        let _ = release.send(());
        server.join().unwrap();
        assert!(healthy);
    }

    #[test]
    fn bridge_tokens_are_bounded_and_single_line() {
        let valid = "v".repeat(32);
        assert_eq!(
            normalize_bridge_token(&format!("  {valid}\r\n")).unwrap(),
            valid
        );
        assert!(normalize_bridge_token("").is_err());
        assert!(normalize_bridge_token("valid\ntoken").is_err());
        assert!(normalize_bridge_token("short-token").is_err());
        assert!(normalize_bridge_token(&format!("{}é", "x".repeat(31))).is_err());
        assert!(normalize_bridge_token(&"x".repeat(MAX_BRIDGE_TOKEN_CHARS + 1)).is_err());
    }

    #[test]
    fn operator_tokens_are_generated_in_memory_and_are_unique() {
        let first = BridgeAuth::generate().expect("operator token generation should succeed");
        let second = BridgeAuth::generate().expect("operator token generation should succeed");
        assert_eq!(first.operator_token.len(), 96);
        assert!(first
            .operator_token
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit()));
        assert_ne!(first.operator_token, second.operator_token);
    }

    #[test]
    fn occupied_untrusted_port_is_never_a_spawn_candidate() {
        assert!(bridge_port_is_free_for_owned_launch(&BridgePortState::Free));
        assert!(!bridge_port_is_free_for_owned_launch(
            &BridgePortState::Trusted
        ));
        assert!(!bridge_port_is_free_for_owned_launch(
            &BridgePortState::OccupiedUntrusted
        ));
    }

    #[test]
    fn released_loopback_port_is_an_available_spawn_candidate() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        drop(listener);
        let state =
            bridge_port_state_at(&address, "test-operator-token-that-is-long-enough").unwrap();
        assert_eq!(state, BridgePortState::Free);
    }

    #[test]
    fn bootstrap_attempts_are_serialized_and_retry_increments_generation() {
        let runtime = Arc::new(BridgeRuntime::default());
        let mut workers = Vec::new();
        for _ in 0..16 {
            let runtime = Arc::clone(&runtime);
            workers.push(thread::spawn(move || runtime.begin_attempt()));
        }
        let attempts: Vec<u64> = workers
            .into_iter()
            .filter_map(|worker| worker.join().unwrap())
            .collect();
        assert_eq!(attempts, vec![1]);
        assert_eq!(runtime.status().phase, BridgeBootstrapPhase::Starting);

        assert!(runtime
            .finish_failed(
                1,
                "identity_timeout",
                "safe failure",
                true,
                BridgeSource::OwnedSidecar,
            )
            .is_none());
        assert_eq!(runtime.begin_attempt(), Some(2));
        assert_eq!(runtime.begin_attempt(), None);
    }

    #[test]
    fn first_same_generation_failure_survives_a_later_terminal_event() {
        let runtime = BridgeRuntime::default();
        let attempt = runtime.begin_attempt().unwrap();
        runtime.finish_ready(attempt);
        assert!(runtime
            .finish_failed(
                attempt,
                "bridge_identity_lost",
                "identity proof failed",
                true,
                BridgeSource::OwnedSidecar,
            )
            .is_none());
        assert!(runtime
            .finish_failed(
                attempt,
                "bridge_process_stopped",
                "later terminal event",
                true,
                BridgeSource::OwnedSidecar,
            )
            .is_none());
        assert_eq!(
            runtime.status().code.as_deref(),
            Some("bridge_identity_lost")
        );
        assert_eq!(runtime.begin_attempt(), Some(2));
        assert_eq!(runtime.status().phase, BridgeBootstrapPhase::Starting);
    }

    #[test]
    fn token_is_available_only_after_the_current_attempt_is_ready() {
        let runtime = BridgeRuntime::default();
        assert!(runtime.ready_token().is_none());
        let attempt = runtime.begin_attempt().unwrap();
        let token = runtime.token_for_attempt(attempt).unwrap();
        assert!(runtime.ready_token().is_none());
        runtime.finish_ready(attempt);
        assert_eq!(runtime.ready_token(), Some((attempt, token)));
        assert!(runtime.begin_attempt().is_none());
    }

    #[test]
    fn non_retryable_failure_cannot_be_restarted_through_ipc_state() {
        let runtime = BridgeRuntime::default();
        let attempt = runtime.begin_attempt().unwrap();
        runtime.finish_failed(
            attempt,
            "sidecar_missing",
            "safe failure",
            false,
            BridgeSource::NotReady,
        );
        assert_eq!(runtime.begin_attempt(), None);
        assert_eq!(runtime.status().code.as_deref(), Some("sidecar_missing"));
    }

    #[test]
    fn deadlines_and_terminal_events_fail_closed_without_a_live_process() {
        assert!(remaining_timeout(
            Instant::now() - Duration::from_millis(1),
            Duration::from_secs(1)
        )
        .is_none());
        assert!(command_event_is_terminal(&CommandEvent::Error(
            "synthetic wait failure".to_string()
        )));
        assert!(!command_event_is_terminal(&CommandEvent::Stdout(
            b"private output is discarded".to_vec()
        )));
    }

    #[test]
    fn an_actual_untrusted_listener_is_classified_occupied_without_using_7420() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("ephemeral listener should bind");
        let address = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            for connection_index in 0..2 {
                let (mut stream, _) = listener.accept().expect("probe should connect");
                if connection_index == 0 {
                    continue;
                }
                let mut request = [0_u8; 4096];
                let _ = stream.read(&mut request);
                let body = b"{\"ok\":true,\"service\":\"not-pex\"}";
                let response = format!(
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n",
                    body.len()
                );
                stream.write_all(response.as_bytes()).unwrap();
                stream.write_all(body).unwrap();
            }
        });
        let state =
            bridge_port_state_at(&address, "test-operator-token-that-is-long-enough").unwrap();
        server.join().unwrap();
        assert_eq!(state, BridgePortState::OccupiedUntrusted);
        assert!(!bridge_port_is_free_for_owned_launch(&state));
    }

    #[test]
    fn packaged_windows_are_local_and_csp_denies_remote_navigation_and_scripts() {
        let config: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        let windows = config["app"]["windows"].as_array().unwrap();
        let main = windows
            .iter()
            .find(|window| window["label"] == "main")
            .unwrap();
        let pet = windows
            .iter()
            .find(|window| window["label"] == "pet")
            .unwrap();
        assert_eq!(main["visible"], true);
        assert_eq!(pet["visible"], false);
        assert!(windows.iter().all(|window| {
            window
                .get("url")
                .and_then(|value| value.as_str())
                .is_none_or(|url| !url.contains("://") && !url.starts_with("//"))
        }));
        let csp = config["app"]["security"]["csp"].as_object().unwrap();
        let default_src = csp["default-src"].as_str().unwrap();
        let script_src = csp["script-src"].as_str().unwrap();
        let connect_src = csp["connect-src"].as_str().unwrap();
        assert!(!default_src.contains("http://") && !default_src.contains("https://"));
        assert!(!script_src.contains("http://") && !script_src.contains("https://"));
        assert!(!connect_src.contains("https://"));
        assert!(connect_src.split_whitespace().all(|source| {
            !source.starts_with("http://")
                || source == "http://ipc.localhost"
                || source == "http://127.0.0.1:7420"
        }));
    }

    #[test]
    fn navigation_guard_rejects_remote_and_token_bearing_top_level_urls() {
        for allowed in [
            "tauri://localhost/",
            "tauri://localhost/pet.html#pet",
            "http://tauri.localhost/",
            "https://tauri.localhost/pet.html",
        ] {
            assert!(
                trusted_webview_navigation(&tauri::Url::parse(allowed).unwrap()),
                "expected local packaged URL to be allowed: {allowed}"
            );
        }
        for denied in [
            "https://evil.example/",
            "https://evil.example/#stolen-token",
            "data:text/html,remote",
            "javascript:location='https://evil.example/'",
            "http://tauri.localhost/?token=secret",
            "tauri://localhost:7420/",
            "https://tauri.localhost@evil.example/",
            "http://127.0.0.1:7420/",
        ] {
            assert!(
                !trusted_webview_navigation(&tauri::Url::parse(denied).unwrap()),
                "expected navigation to be denied: {denied}"
            );
        }
        let dev = tauri::Url::parse("http://localhost:1420/").unwrap();
        assert_eq!(trusted_webview_navigation(&dev), cfg!(debug_assertions));
    }
}
