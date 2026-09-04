#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{ErrorKind, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::sync::Mutex;
use std::time::Duration;

use hmac::{Hmac, Mac};
use rand::{rngs::OsRng, RngCore};
use serde::Deserialize;
use sha2::Sha256;
use tauri::Manager;
use tauri_plugin_shell::{process::CommandChild, ShellExt};

const BRIDGE_HOST: &str = "127.0.0.1";
const BRIDGE_PORT: &str = "7420";
const BRIDGE_ADDRESS: &str = "127.0.0.1:7420";
const BRIDGE_IDENTITY_PATH: &str = "/health/identity";
const MIN_BRIDGE_TOKEN_BYTES: usize = 32;
const MAX_BRIDGE_TOKEN_CHARS: usize = 512;
type HmacSha256 = Hmac<Sha256>;

#[derive(Default)]
struct OwnedBridge(Mutex<Option<CommandChild>>);

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

fn bridge_is_healthy_at(address: &SocketAddr, token: &str) -> bool {
    let mut challenge_bytes = [0_u8; 32];
    if OsRng.try_fill_bytes(&mut challenge_bytes).is_err() {
        return false;
    }
    let challenge = hex::encode(challenge_bytes);
    let Ok(mut stream) = TcpStream::connect_timeout(address, Duration::from_millis(350)) else {
        return false;
    };
    let timeout = Some(Duration::from_millis(750));
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
        match stream.read(&mut chunk) {
            Ok(0) => break,
            Ok(count) => {
                response.extend_from_slice(&chunk[..count]);
                if response.len() > 64 * 1_024 {
                    return false;
                }
            }
            Err(error) if matches!(error.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {
                break;
            }
            Err(_) => return false,
        }
    }
    is_pex_identity_response(&response, &challenge, token)
}

fn bridge_port_state(token: &str) -> Result<BridgePortState, String> {
    let address = bridge_address()?;
    bridge_port_state_at(&address, token)
}

fn bridge_port_state_at(address: &SocketAddr, token: &str) -> Result<BridgePortState, String> {
    match TcpStream::connect_timeout(address, Duration::from_millis(350)) {
        Ok(stream) => {
            drop(stream);
            if bridge_is_healthy_at(address, token) {
                Ok(BridgePortState::Trusted)
            } else {
                Ok(BridgePortState::OccupiedUntrusted)
            }
        }
        Err(error) if error.kind() == ErrorKind::ConnectionRefused => Ok(BridgePortState::Free),
        Err(_) => Err("PEX bridge port state could not be established safely".to_string()),
    }
}

fn bridge_launch_required(state: BridgePortState) -> Result<bool, String> {
    match state {
        BridgePortState::Free => Ok(true),
        BridgePortState::Trusted => Ok(false),
        BridgePortState::OccupiedUntrusted => {
            Err("Port 7420 is occupied by a process that cannot prove PEX identity".to_string())
        }
    }
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
    let Some(state) = app.try_state::<OwnedBridge>() else {
        return;
    };
    let Ok(mut guard) = state.0.lock() else {
        return;
    };
    if let Some(child) = guard.take() {
        let _ = child.kill();
    }
}

#[tauri::command]
async fn bridge_token(auth: tauri::State<'_, BridgeAuth>) -> Result<String, String> {
    let token = auth.operator_token.clone();
    tauri::async_runtime::spawn_blocking(move || {
        if !bridge_is_healthy_with_token(&token) {
            return Err("PEX bridge identity could not be verified".to_string());
        }
        Ok(token)
    })
    .await
    .map_err(|_| "PEX bridge identity check could not complete".to_string())?
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
        .plugin(navigation_guard())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![bridge_token])
        .setup(|app| {
            app.manage(OwnedBridge::default());
            let auth = BridgeAuth::generate()?;
            let operator_token = auth.operator_token.clone();
            app.manage(auth);
            bridge_address()?;
            if bridge_launch_required(bridge_port_state(&operator_token)?)? {
                let (mut events, child) = app
                    .shell()
                    .sidecar("pex-bridge")?
                    // Pin the release sidecar to authenticated loopback operation.
                    // The operator bearer exists only in this Rust process and its
                    // owned bridge child's environment; worker integrations receive
                    // separately scoped ingest credentials.
                    .args(bridge_sidecar_args())
                    .env("PEX_HOST", BRIDGE_HOST)
                    .env("PEX_PORT", BRIDGE_PORT)
                    .env("PEX_REQUIRE_AUTH", "true")
                    .env("PEX_TOKEN", &operator_token)
                    .spawn()?;
                {
                    let state = app.state::<OwnedBridge>();
                    let mut guard = state
                        .0
                        .lock()
                        .map_err(|_| "PEX bridge process state is unavailable")?;
                    *guard = Some(child);
                }
                // The shell plugin uses piped stdout/stderr. Drain all events so a
                // chatty bridge can never block on a full pipe; do not surface logs
                // here because provider diagnostics can contain sensitive context.
                tauri::async_runtime::spawn(async move { while events.recv().await.is_some() {} });

                for _ in 0..200 {
                    if bridge_is_healthy_with_token(&operator_token) {
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(100));
                }
                if !bridge_is_healthy_with_token(&operator_token) {
                    stop_owned_bridge(app.handle());
                    return Err("PEX bridge sidecar did not prove its identity".into());
                }
            }
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.show();
            }
            if let Some(pet) = app.get_webview_window("pet") {
                let _ = pet.set_background_color(Some(tauri::window::Color(0, 0, 0, 0)));
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() != "main" {
                    api.prevent_close();
                    let _ = window.hide();
                    return;
                }
                stop_owned_bridge(window.app_handle());
                window.app_handle().exit(0);
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
    use std::thread;

    use super::{
        bridge_address, bridge_identity_proof, bridge_launch_required, bridge_port_state_at,
        bridge_sidecar_args, is_pex_identity_response, normalize_bridge_token,
        trusted_webview_navigation, BridgeAuth, BridgePortState, MAX_BRIDGE_TOKEN_CHARS,
    };

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
        assert_eq!(bridge_launch_required(BridgePortState::Free), Ok(true));
        assert_eq!(bridge_launch_required(BridgePortState::Trusted), Ok(false));
        assert!(bridge_launch_required(BridgePortState::OccupiedUntrusted)
            .unwrap_err()
            .contains("cannot prove PEX identity"));
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
        assert!(bridge_launch_required(state).is_err());
    }

    #[test]
    fn packaged_windows_are_local_and_csp_denies_remote_navigation_and_scripts() {
        let config: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        let windows = config["app"]["windows"].as_array().unwrap();
        assert!(windows.iter().all(|window| {
            window
                .get("url")
                .and_then(|value| value.as_str())
                .map_or(true, |url| !url.contains("://") && !url.starts_with("//"))
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
