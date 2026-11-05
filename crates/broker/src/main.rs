#![forbid(unsafe_code)]
#![deny(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::unimplemented,
    clippy::todo,
    clippy::unreachable
)]
mod native;
use craftlink_core::{Error, Id, Manifest, Store, Transaction};
use native::{Binding, Runtime};
use serde_json::{Value, json};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::{Arc, Condvar, Mutex};
use std::time::Duration;
type Shared = Arc<(Mutex<Runtime>, Condvar)>;
enum NativeJob {
    Wake,
    Live(Id),
    Paths(std::collections::BTreeSet<PathBuf>),
    Command(
        String,
        Value,
        std::sync::mpsc::Sender<craftlink_core::Result<Value>>,
    ),
}
fn native_method(method: &str) -> bool {
    matches!(
        method,
        "bind_native"
            | "place_link"
            | "reconnect"
            | "native_changed"
            | "open_in_source_application"
            | "resolve_conflict"
    )
}
fn fail(e: impl std::fmt::Display) -> Error {
    Error::Invalid(e.to_string())
}
fn parse<T: serde::de::DeserializeOwned>(v: Value) -> craftlink_core::Result<T> {
    serde_json::from_value(v).map_err(fail)
}
fn field(v: &Value, k: &str) -> craftlink_core::Result<Value> {
    v.get(k)
        .cloned()
        .ok_or_else(|| fail(format!("missing {k}")))
}
fn dispatch(r: &mut Runtime, method: &str, p: Value) -> craftlink_core::Result<Value> {
    match method {
        "register_application" => {
            r.store.register(parse::<Manifest>(p)?)?;
            Ok(json!({"schema":1}))
        }
        "negotiate_capabilities" => {
            let app: String = parse(field(&p, "application")?)?;
            let m = r
                .store
                .manifests()?
                .into_iter()
                .find(|m| m.application == app)
                .ok_or(Error::Missing(app))?;
            m.negotiate(
                &parse::<String>(field(&p, "kind")?)?,
                &parse::<Vec<String>>(field(&p, "properties")?)?,
                p.get("write").and_then(Value::as_bool).unwrap_or(false),
            )?;
            Ok(json!(m))
        }
        "applications" => Ok(json!(r.store.manifests()?)),
        "enumerate_objects" | "search_assets" => {
            let query = p
                .get("query")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_lowercase();
            Ok(json!(
                r.store
                    .objects()?
                    .into_iter()
                    .filter(|o| o.value.to_string().to_lowercase().contains(&query))
                    .collect::<Vec<_>>()
            ))
        }
        "resolve_link" => Ok(json!(r.store.object(parse(field(&p, "object")?)?)?)),
        "apply_changes" | "commit_transaction" => {
            let request = parse::<Transaction>(p)?;
            for c in &request.changes {
                for value in r.store.bindings()? {
                    if value.get("phase").and_then(Value::as_str) == Some("creating") {
                        continue;
                    }
                    let b: Binding = parse(value)?;
                    if b.object == c.object {
                        native::validate(&c.value)?;
                    }
                }
            }
            let receipt = r.store.commit(request)?;
            Ok(json!(receipt))
        }
        "begin_transaction" => Ok(
            json!({"operation":Id::new_v4(),"staging":"client-side; durable only at commit_transaction"}),
        ),
        "rollback_transaction" => Ok(json!({"discard_staged_changes":true})),
        "create_link" => {
            r.store.link(
                parse(field(&p, "id")?)?,
                parse(field(&p, "source")?)?,
                parse(field(&p, "target")?)?,
                p.get("mode").and_then(Value::as_str).unwrap_or("semantic"),
            )?;
            Ok(json!({"linked":true}))
        }
        "dependencies" => Ok(json!(r.store.edges()?)),
        "undo" | "redo" => {
            let receipt = r.store.history(
                parse(field(&p, "operation")?)?,
                parse(field(&p, "object")?)?,
                parse(field(&p, "expected")?)?,
                method == "redo",
            )?;
            Ok(json!(receipt))
        }
        "conflicts" => Ok(json!(r.store.conflicts()?)),
        "bind_native" => {
            let mut b: Binding = parse(p)?;
            b.fidelity="semantic properties: name/opacity only; other native features remain in their source documents".into();
            r.initialize_binding(&mut b)?;
            let head = r.store.object(b.object)?;
            if head.kind != "rectangle" {
                return Err(Error::Capability(
                    "native adapters require rectangle properties".into(),
                ));
            }
            native::validate(&head.value)?;
            r.store.set_binding(b.id, &json!(b))?;
            r.reconcile(b.id)?;
            Ok(r.store.binding(b.id)?)
        }
        "place_link" => r.place_link(parse(p)?),
        "reconnect" => {
            let id: Id = parse(field(&p, "binding")?)?;
            let mut b: Binding = parse(r.store.binding(id)?)?;
            if let Some(port) = p.get("port") {
                b.port = parse(port.clone())?;
            }
            if let Some(path) = p.get("path") {
                b.path = r.confined(&parse::<PathBuf>(path.clone())?)?;
            }
            if let Some(node) = p.get("node") {
                b.node = parse(node.clone())?;
            }
            if let Some(live) = p.get("live") {
                b.live = parse(live.clone())?;
            }
            if let Some(token) = p.get("token_file") {
                b.token_file = parse(token.clone())?;
            }
            r.initialize_binding(&mut b)?;
            r.store.set_binding(id, &json!(b))?;
            r.reconcile(id)?;
            Ok(r.store.binding(id)?)
        }
        "native_changed" => {
            let id = parse(field(&p, "binding")?)?;
            r.ingest(id)?;
            r.reconcile_all();
            Ok(r.store.binding(id)?)
        }
        "bindings" => Ok(json!(r.store.bindings()?)),
        "detach" | "freeze" => {
            let id: Id = parse(field(&p, "binding")?)?;
            let mut b: Binding = parse(r.store.binding(id)?)?;
            b.enabled = false;
            b.status = "frozen".into();
            r.store.set_binding(id, &json!(b))?;
            Ok(json!(b))
        }
        "open_in_source_application" => {
            let id: Id = parse(field(&p, "binding")?)?;
            let b: Binding = parse(r.store.binding(id)?)?;
            native::bound_call(
                &b,
                "engine.execute",
                json!({"command":"selection.set","params":{"ids":[b.node]}}),
            )?;
            Ok(json!({"application":b.profile,"path":b.path,"node":b.node}))
        }
        "resolve_conflict" => {
            let id: Id = parse(field(&p, "binding")?)?;
            let mut b: Binding = parse(r.store.binding(id)?)?;
            if p.get("choice").and_then(Value::as_str) != Some("committed") {
                return Err(Error::Capability(
                    "choose committed explicitly; retain local intent in a new guarded transaction"
                        .into(),
                ));
            }
            b.baseline = native::read(&b)?;
            b.status = "stale".into();
            r.store.set_binding(id, &json!(b))?;
            r.reconcile(id)?;
            Ok(r.store.binding(id)?)
        }
        _ => Err(Error::Capability(format!("unknown method {method}"))),
    }
}
fn handle(
    mut stream: TcpStream,
    shared: Shared,
    token: Arc<String>,
    jobs: std::sync::mpsc::SyncSender<NativeJob>,
    dirty: Arc<std::sync::atomic::AtomicBool>,
) -> craftlink_core::Result<()> {
    stream
        .set_read_timeout(Some(Duration::from_secs(10)))
        .map_err(fail)?;
    stream
        .set_write_timeout(Some(Duration::from_secs(10)))
        .map_err(fail)?;
    let mut line = String::new();
    BufReader::new(stream.try_clone().map_err(fail)?)
        .take(1024 * 1024 + 1)
        .read_line(&mut line)
        .map_err(fail)?;
    if line.len() > 1024 * 1024 || !line.ends_with('\n') {
        return Err(fail("frame limit or incomplete frame"));
    }
    let req: Value = serde_json::from_str(&line).map_err(fail)?;
    use sha2::{Digest, Sha256};
    let given = req.get("token").and_then(Value::as_str).unwrap_or("");
    let a = Sha256::digest(given.as_bytes());
    let b = Sha256::digest(token.as_bytes());
    let diff = a.iter().zip(b.iter()).fold(0u8, |d, (a, b)| d | (a ^ b));
    let response = if diff != 0 {
        json!({"ok":false,"error":"authentication required","code":"authentication"})
    } else {
        let method = req.get("method").and_then(Value::as_str).unwrap_or("");
        let p = req.get("params").cloned().unwrap_or(json!({}));
        let (mutex, changed) = &*shared;
        let result = if native_method(method) {
            let (sender, receiver) = std::sync::mpsc::channel();
            match jobs.try_send(NativeJob::Command(method.into(),p,sender)){
                Ok(())=>receiver.recv_timeout(Duration::from_secs(80)).map_err(|_|Error::Missing("native request timed out; inspect binding before retrying, outcome may be unknown".into()))?,
                Err(_)=>Err(Error::Invalid("native queue is busy; request was not sent".into())),
            }
        } else {
            let mut r = mutex.lock().map_err(fail)?;
            if method == "subscribe_to_changes" {
                let after = p.get("after").and_then(Value::as_u64).unwrap_or(0);
                let wait = p
                    .get("timeout_ms")
                    .and_then(Value::as_u64)
                    .unwrap_or(20000)
                    .min(30000);
                let deadline = std::time::Instant::now() + Duration::from_millis(wait);
                let mut events = r.store.events(after)?;
                while events.is_empty() && std::time::Instant::now() < deadline {
                    r = changed
                        .wait_timeout(
                            r,
                            deadline.saturating_duration_since(std::time::Instant::now()),
                        )
                        .map_err(fail)?
                        .0;
                    events = r.store.events(after)?;
                }
                Ok(json!(events))
            } else {
                dispatch(&mut r, method, p)
            }
        };
        if result.is_ok()
            && matches!(
                method,
                "apply_changes" | "commit_transaction" | "undo" | "redo"
            )
        {
            dirty.store(true, std::sync::atomic::Ordering::SeqCst);
            // A full queue already has work to wake the native owner. The dirty
            // bit survives coalescing so committed heads are never dropped.
            let _ = jobs.try_send(NativeJob::Wake);
        }
        changed.notify_all();
        match result {
            Ok(v) => json!({"ok":true,"result":v}),
            Err(e) => {
                let code = match &e {
                    Error::Conflict(_) => "conflict",
                    Error::Capability(_) => "capability",
                    Error::Missing(_) => "missing",
                    Error::Storage(_) => "storage",
                    Error::Invalid(_) => "invalid",
                };
                json!({"ok":false,"error":e.to_string(),"code":code})
            }
        }
    };
    stream
        .write_all(format!("{response}\n").as_bytes())
        .map_err(fail)
}
fn run() -> craftlink_core::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let root = PathBuf::from(
        args.get(1)
            .ok_or_else(|| fail("usage: craftlink-broker PROJECT_ROOT [PORT]; token on stdin"))?,
    );
    std::fs::create_dir_all(&root).map_err(fail)?;
    let root = std::fs::canonicalize(root).map_err(fail)?;
    let store_path = root.join(".craftlink");
    std::fs::create_dir_all(&store_path).map_err(fail)?;
    let store_path = std::fs::canonicalize(store_path).map_err(fail)?;
    if !store_path.starts_with(&root) || store_path == root {
        return Err(fail("private store redirected outside project"));
    }
    let mut token = String::new();
    std::io::stdin()
        .lock()
        .take(4097)
        .read_line(&mut token)
        .map_err(fail)?;
    let token = token.trim().to_string();
    if token.len() < 32 || token.len() > 4096 {
        return Err(fail("provide a random >=32 byte token on stdin"));
    }
    let port: u16 = args
        .get(2)
        .map(|s| s.parse().map_err(fail))
        .transpose()?
        .unwrap_or(0);
    let listener = TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, port)).map_err(fail)?;
    let shared: Shared = Arc::new((
        Mutex::new(Runtime {
            store: Store::open(&store_path)?,
            root: root.clone(),
        }),
        Condvar::new(),
    ));
    let (jobs, native_jobs) = std::sync::mpsc::sync_channel::<NativeJob>(64);
    let dirty = Arc::new(std::sync::atomic::AtomicBool::new(true));
    let work = shared.clone();
    let needs_recovery = dirty.clone();
    let mut native = Runtime {
        store: Store::open(&store_path)?,
        root: root.clone(),
    };
    let feed_jobs = jobs.clone();
    let feed_dirty = dirty.clone();
    std::thread::spawn(move || {
        let mut feeds = std::collections::BTreeMap::<
            Id,
            (u16, Option<u64>, Arc<std::sync::atomic::AtomicBool>),
        >::new();
        while let Ok(job) = native_jobs.recv() {
            match job {
                NativeJob::Wake => {}
                NativeJob::Live(id) => {
                    if let Err(e) = native.ingest_live(id) {
                        native.mark_error(id, &e);
                    }
                    native.reconcile_all();
                }
                NativeJob::Command(method, p, reply) => {
                    // Retire the previous reader even when the app reuses its port/UID.
                    // Otherwise a still-unwinding old poll can hide the new subscription.
                    if method == "reconnect"
                        && let Some(id) = p
                            .get("binding")
                            .and_then(Value::as_str)
                            .and_then(|id| Id::parse_str(id).ok())
                        && let Some((_, _, cancel)) = feeds.remove(&id)
                    {
                        cancel.store(false, std::sync::atomic::Ordering::SeqCst);
                    }
                    let _ = reply.send(dispatch(&mut native, &method, p));
                }
                NativeJob::Paths(paths) => {
                    let mut relevant = false;
                    if let Ok(values) = native.store.bindings() {
                        for value in values {
                            if let Ok(b) = parse::<Binding>(value)
                                && b.enabled
                                && paths.iter().any(|p| {
                                    std::fs::canonicalize(p).unwrap_or_else(|_| p.clone()) == b.path
                                })
                            {
                                relevant = true;
                                if let Err(e) = native.ingest(b.id) {
                                    native.mark_error(b.id, &e);
                                }
                            }
                        }
                    }
                    if relevant {
                        native.reconcile_all();
                    }
                }
            }
            if needs_recovery.swap(false, std::sync::atomic::Ordering::SeqCst) {
                native.recover();
            }
            if let Ok(values) = native.store.bindings() {
                let mut enabled = std::collections::BTreeSet::new();
                for value in values {
                    if let Ok(b) = parse::<Binding>(value)
                        && b.enabled
                        && b.live
                    {
                        enabled.insert(b.id);
                        if feeds.get(&b.id).is_some_and(|(port, document, active)| {
                            *port == b.port
                                && *document == b.native_document
                                && active.load(std::sync::atomic::Ordering::SeqCst)
                        }) {
                            continue;
                        }
                        if let Some((_, _, cancel)) = feeds.remove(&b.id) {
                            cancel.store(false, std::sync::atomic::Ordering::SeqCst);
                        }
                        let active = Arc::new(std::sync::atomic::AtomicBool::new(true));
                        feeds.insert(b.id, (b.port, b.native_document, active.clone()));
                        let sender = feed_jobs.clone();
                        let dirty = feed_dirty.clone();
                        std::thread::spawn(move || {
                            let mut cursor = 0;
                            while active.load(std::sync::atomic::Ordering::SeqCst) {
                                let result = match native::bound_call(
                                    &b,
                                    "events.poll",
                                    json!({"after":cursor,"topics":["document"],"timeoutMs":20000,"limit":256}),
                                ) {
                                    Ok(v) => v,
                                    Err(_) => break,
                                };
                                cursor = result.get("cursor").and_then(Value::as_u64).unwrap_or(0);
                                let changed = result
                                    .get("reset")
                                    .and_then(Value::as_bool)
                                    .unwrap_or(false)
                                    || result.get("dropped").and_then(Value::as_u64).unwrap_or(0)
                                        > 0
                                    || result.get("events").and_then(Value::as_array).is_some_and(
                                        |events| {
                                            events.iter().any(|e| {
                                                e.pointer("/data/documentId")
                                                    .and_then(Value::as_u64)
                                                    == b.native_document
                                            })
                                        },
                                    );
                                if changed && sender.try_send(NativeJob::Live(b.id)).is_err() {
                                    dirty.store(true, std::sync::atomic::Ordering::SeqCst);
                                }
                            }
                            // A reconnect command may reuse the same port and native UID.
                            // Retire the dead reader so that wake can subscribe again.
                            active.store(false, std::sync::atomic::Ordering::SeqCst);
                        });
                    }
                }
                feeds.retain(|id, (_, _, cancel)| {
                    if enabled.contains(id) {
                        true
                    } else {
                        cancel.store(false, std::sync::atomic::Ordering::SeqCst);
                        false
                    }
                });
            }
            if let Ok(_guard) = work.0.lock() {
                work.1.notify_all();
            }
        }
    });
    jobs.send(NativeJob::Wake).map_err(fail)?;
    let (sender, receiver) = std::sync::mpsc::channel();
    use notify::Watcher;
    let mut watcher = notify::recommended_watcher(move |event| {
        let _ = sender.send(event);
    })
    .map_err(fail)?;
    watcher
        .watch(&root, notify::RecursiveMode::Recursive)
        .map_err(fail)?;
    let watcher_jobs = jobs.clone();
    let watcher_dirty = dirty.clone();
    std::thread::spawn(move || {
        while let Ok(event) = receiver.recv() {
            let mut paths = std::collections::BTreeSet::new();
            if let Ok(e) = event {
                paths.extend(e.paths);
            }
            while let Ok(Ok(e)) = receiver.recv_timeout(Duration::from_millis(70)) {
                paths.extend(e.paths);
            }
            paths.retain(|p| {
                matches!(
                    p.extension().and_then(|s| s.to_str()),
                    Some("figcraft" | "vectorcraft")
                )
            });
            if !paths.is_empty() && watcher_jobs.try_send(NativeJob::Paths(paths)).is_err() {
                watcher_dirty.store(true, std::sync::atomic::Ordering::SeqCst);
            }
        }
    });
    println!(
        "{}",
        json!({"address":listener.local_addr().map_err(fail)?.to_string(),"schema":1})
    );
    std::io::stdout().flush().map_err(fail)?;
    let token = Arc::new(token);
    let active = Arc::new(std::sync::atomic::AtomicUsize::new(0));
    for stream in listener.incoming() {
        let stream = stream.map_err(fail)?;
        use std::sync::atomic::Ordering;
        if active.fetch_add(1, Ordering::SeqCst) >= 16 {
            active.fetch_sub(1, Ordering::SeqCst);
            continue;
        }
        let work = shared.clone();
        let credential = token.clone();
        let active = active.clone();
        let native_jobs = jobs.clone();
        let dirty = dirty.clone();
        std::thread::spawn(move || {
            if let Err(e) = handle(stream, work, credential, native_jobs, dirty) {
                eprintln!("{e}");
            }
            active.fetch_sub(1, Ordering::SeqCst);
        });
    }
    Ok(())
}
fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
