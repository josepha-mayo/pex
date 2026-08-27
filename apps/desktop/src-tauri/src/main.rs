#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;

fn image_for(harness: &str) -> Option<&'static str> {
    match harness {
        "cursor" => Some("cursor.exe"),
        "codex" => Some("chatgpt.exe"),
        "grok_bot" => Some("grok bot.exe"),
        "hermes" => Some("hermes.exe"),
        "devin" => Some("devin.exe"),
        "claude_code" => Some("claude.exe"),
        "opencode" => Some("opencode.exe"),
        "qwen" => Some("qwen.exe"),
        "kimi" => Some("kimi.exe"),
        _ => None,
    }
}

#[tauri::command]
fn focus_harness(harness: String) {
    std::thread::spawn(move || {
        let _ = focus_now(&harness);
    });
}

#[tauri::command]
fn quit_app(app: tauri::AppHandle) {
    app.exit(0);
}

fn focus_now(harness: &str) -> bool {
    let Some(image) = image_for(harness) else {
        return false;
    };
    #[cfg(windows)]
    {
        win_focus(image)
    }
    #[cfg(not(windows))]
    {
        let _ = image;
        false
    }
}

#[cfg(windows)]
fn win_focus(image: &str) -> bool {
    use std::ffi::OsString;
    use std::os::windows::ffi::OsStringExt;

    struct Hunt {
        needle: String,
        hwnd: isize,
    }

    #[link(name = "user32")]
    extern "system" {
        fn EnumWindows(cb: unsafe extern "system" fn(isize, isize) -> i32, lparam: isize) -> i32;
        fn IsWindowVisible(hwnd: isize) -> i32;
        fn GetWindowTextLengthW(hwnd: isize) -> i32;
        fn ShowWindow(hwnd: isize, cmd: i32) -> i32;
        fn SetForegroundWindow(hwnd: isize) -> i32;
        fn GetForegroundWindow() -> isize;
        fn GetWindowThreadProcessId(hwnd: isize, pid: *mut u32) -> u32;
        fn AttachThreadInput(a: u32, b: u32, attach: i32) -> i32;
        fn AllowSetForegroundWindow(pid: u32) -> i32;
    }
    #[link(name = "kernel32")]
    extern "system" {
        fn OpenProcess(access: u32, inherit: i32, pid: u32) -> isize;
        fn QueryFullProcessImageNameW(h: isize, flags: u32, name: *mut u16, size: *mut u32) -> i32;
        fn CloseHandle(h: isize) -> i32;
        fn GetCurrentThreadId() -> u32;
    }

    unsafe extern "system" fn enum_cb(hwnd: isize, lparam: isize) -> i32 {
        let hunt = unsafe { &mut *(lparam as *mut Hunt) };
        unsafe {
            if IsWindowVisible(hwnd) == 0 || GetWindowTextLengthW(hwnd) <= 0 {
                return 1;
            }
            let mut pid = 0u32;
            GetWindowThreadProcessId(hwnd, &mut pid);
            let proc = OpenProcess(0x1000, 0, pid);
            if proc == 0 {
                return 1;
            }
            let mut buf = [0u16; 260];
            let mut size = buf.len() as u32;
            let ok = QueryFullProcessImageNameW(proc, 0, buf.as_mut_ptr(), &mut size);
            CloseHandle(proc);
            if ok == 0 {
                return 1;
            }
            let path = OsString::from_wide(&buf[..size as usize])
                .to_string_lossy()
                .to_lowercase();
            if path.ends_with(&hunt.needle) {
                hunt.hwnd = hwnd;
                return 0;
            }
        }
        1
    }

    let mut hunt = Hunt {
        needle: format!("\\{image}"),
        hwnd: 0,
    };
    unsafe {
        EnumWindows(enum_cb, &mut hunt as *mut Hunt as isize);
        if hunt.hwnd == 0 {
            hunt.needle = format!("/{image}");
            EnumWindows(enum_cb, &mut hunt as *mut Hunt as isize);
        }
        if hunt.hwnd == 0 {
            return false;
        }
        let _ = AllowSetForegroundWindow(u32::MAX);
        ShowWindow(hunt.hwnd, 9);
        let fore = GetForegroundWindow();
        let cur = GetCurrentThreadId();
        let other = GetWindowThreadProcessId(fore, std::ptr::null_mut());
        AttachThreadInput(cur, other, 1);
        SetForegroundWindow(hunt.hwnd);
        AttachThreadInput(cur, other, 0);
    }
    true
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![focus_harness, quit_app])
        .setup(|app| {
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
                window.app_handle().exit(0);
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running PEX desktop");
}
