use crate::{fail, parse};
use craftlink_core::{Change, Error, Id, Object, Result, Store, Transaction};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{Ipv4Addr, SocketAddrV4, TcpStream};
use std::path::{Path, PathBuf};
use std::time::Duration;
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Binding {
    pub id: Id,
    pub object: Id,
    pub profile: String,
    pub port: u16,
    pub path: PathBuf,
    pub node: u64,
    pub baseline: Value,
    pub applied: u64,
    #[serde(default)]
    pub observed_hash: String,
    #[serde(default = "enabled")]
    pub enabled: bool,
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub pending: Option<Value>,
    #[serde(default)]
    pub detail: Option<String>,
    #[serde(default)]
    pub fidelity: String,
    #[serde(default)]
    pub placement: Option<Id>,
    #[serde(default)]
    pub live: bool,
    #[serde(default)]
    pub native_document: Option<u64>,
    #[serde(default)]
    pub token_file: Option<PathBuf>,
}
#[derive(Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct PlaceLink {
    pub id: Id,
    pub source_binding: Id,
    pub profile: String,
    pub port: u16,
    pub path: PathBuf,
    pub document: Id,
    pub placement: Id,
    pub link: Id,
    pub operation: Id,
}
fn enabled() -> bool {
    true
}
pub struct Runtime {
    pub store: Store,
    pub root: PathBuf,
}
pub fn call(port: u16, method: &str, params: Value) -> Result<Value> {
    call_with_token(port, None, method, params)
}
fn call_with_token(port: u16, token: Option<&str>, method: &str, params: Value) -> Result<Value> {
    let mut s = TcpStream::connect_timeout(
        &SocketAddrV4::new(Ipv4Addr::LOCALHOST, port).into(),
        Duration::from_secs(2),
    )
    .map_err(|e| Error::Missing(format!("application unavailable: {e}")))?;
    s.set_read_timeout(Some(Duration::from_secs(65)))
        .map_err(fail)?;
    s.set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(fail)?;
    let mut reader = BufReader::new(s.try_clone().map_err(fail)?);
    if let Some(token) = token {
        s.write_all(
            format!(
                "{}\n",
                json!({"id":0,"method":"auth","params":{"token":token}})
            )
            .as_bytes(),
        )
        .map_err(fail)?;
        let mut auth = String::new();
        reader
            .by_ref()
            .take(4097)
            .read_line(&mut auth)
            .map_err(fail)?;
        let auth: Value = serde_json::from_str(&auth)
            .map_err(|_| Error::Capability("native authentication failed".into()))?;
        if auth.get("ok").and_then(Value::as_bool) != Some(true) {
            return Err(Error::Capability("native authentication rejected".into()));
        }
    }
    s.write_all(format!("{}\n", json!({"id":1,"method":method,"params":params})).as_bytes())
        .map_err(fail)?;
    let mut line = String::new();
    reader
        .take(8 * 1024 * 1024 + 1)
        .read_line(&mut line)
        .map_err(fail)?;
    if line.len() > 8 * 1024 * 1024 || !line.ends_with('\n') {
        return Err(fail(
            "native reply exceeds limit or disconnected; inspect before retry",
        ));
    }
    let v: Value = serde_json::from_str(&line).map_err(fail)?;
    if v.get("ok").and_then(Value::as_bool) != Some(true) {
        let error = v
            .get("error")
            .and_then(Value::as_str)
            .unwrap_or("native request failed")
            .to_string();
        return Err(if error.contains("conflict:") {
            Error::Conflict(error)
        } else {
            Error::Capability(error)
        });
    }
    Ok(v.get("result").cloned().unwrap_or(Value::Null))
}
fn command(b: &Binding, id: &str, p: Value) -> Result<Value> {
    bound_call(b, "engine.execute", json!({"command":id,"params":p}))
}
pub fn bound_call(b: &Binding, method: &str, mut p: Value) -> Result<Value> {
    if let Some(document) = b.native_document
        && matches!(method, "engine.execute" | "document.inspect" | "node.get")
    {
        p["document"] = json!(document);
    }
    let token = b
        .token_file
        .as_ref()
        .map(|p| {
            let mut text = String::new();
            std::fs::File::open(p)
                .map_err(fail)?
                .take(4097)
                .read_to_string(&mut text)
                .map_err(fail)?;
            if text.len() > 4096 {
                return Err(fail("native credential file exceeds limit"));
            }
            Ok(text.trim().to_string())
        })
        .transpose()?;
    call_with_token(b.port, token.as_deref(), method, p)
}
fn find(v: &Value, id: u64) -> Option<&Value> {
    match v {
        Value::Object(m) => {
            if m.get("id").and_then(Value::as_u64) == Some(id)
                && (m.contains_key("kind") || m.contains_key("type"))
            {
                return Some(v);
            }
            m.values().find_map(|v| find(v, id))
        }
        Value::Array(a) => a.iter().find_map(|v| find(v, id)),
        _ => None,
    }
}
fn same(a: &Value, b: &Value) -> bool {
    a.get("name") == b.get("name")
        && match (
            a.get("opacity").and_then(Value::as_f64),
            b.get("opacity").and_then(Value::as_f64),
        ) {
            (Some(a), Some(b)) => (a - b).abs() < 0.00001,
            _ => false,
        }
}
pub fn read(b: &Binding) -> Result<Value> {
    Ok(read_state(b)?.0)
}
fn read_state(b: &Binding) -> Result<(Value, Option<(u64, u64)>)> {
    if !["vectorcraft", "figcraft"].contains(&b.profile.as_str()) {
        return Err(Error::Capability(
            "unknown native profile; third-party apps use the SDK".into(),
        ));
    }
    let doc = bound_call(b, "document.inspect", json!({}))?;
    let path = doc
        .get("path")
        .and_then(Value::as_str)
        .ok_or_else(|| Error::Missing("native document has no saved path".into()))?;
    if std::fs::canonicalize(path).map_err(|e| Error::Missing(e.to_string()))? != b.path {
        return Err(Error::Conflict(
            "active document differs from binding; select/reconnect explicitly".into(),
        ));
    }
    let node =
        find(&doc, b.node).ok_or_else(|| Error::Missing(format!("native node {}", b.node)))?;
    let kind = node
        .get("kind")
        .or_else(|| node.get("type"))
        .and_then(Value::as_str)
        .unwrap_or("");
    if !["Rectangle", "RECTANGLE"].contains(&kind) {
        return Err(Error::Capability(format!(
            "only native rectangles verified, got {kind}"
        )));
    }
    let token = doc
        .get("id")
        .or_else(|| doc.get("uid"))
        .and_then(Value::as_u64)
        .zip(doc.get("revision").and_then(Value::as_u64));
    if b.live
        && (!["figcraft", "vectorcraft"].contains(&b.profile.as_str())
            || token.is_none()
            || doc
                .pointer("/capabilities/conditionalExecute")
                .and_then(Value::as_u64)
                != Some(1)
            || doc
                .pointer("/capabilities/documentChangeEvents")
                .and_then(Value::as_u64)
                != Some(1))
    {
        return Err(Error::Capability(
            "live mode requires verified document events and revision guards".into(),
        ));
    }
    Ok((
        json!({"name":node.get("name").and_then(Value::as_str).unwrap_or(""),"opacity":node.get("opacity").and_then(Value::as_f64).unwrap_or(1.0)}),
        token,
    ))
}
pub fn validate(value: &Value) -> Result<()> {
    let props = value
        .as_object()
        .ok_or_else(|| fail("properties required"))?;
    if props
        .keys()
        .any(|k| !matches!(k.as_str(), "name" | "opacity"))
    {
        return Err(Error::Capability("only name and opacity editable".into()));
    }
    value
        .get("opacity")
        .and_then(Value::as_f64)
        .filter(|v| (0.0..=1.0).contains(v))
        .ok_or_else(|| fail("opacity must be 0..1"))?;
    value
        .get("name")
        .and_then(Value::as_str)
        .filter(|s| s.len() <= 4096)
        .ok_or_else(|| fail("name required, at most 4096 bytes"))?;
    Ok(())
}
fn write(b: &Binding, value: &Value, expected: Option<(u64, u64)>) -> Result<()> {
    validate(value)?;
    let opacity = value
        .get("opacity")
        .and_then(Value::as_f64)
        .ok_or_else(|| fail("opacity required"))?;
    let name = value
        .get("name")
        .and_then(Value::as_str)
        .ok_or_else(|| fail("name required"))?;
    let mut params = match b.profile.as_str() {
        "vectorcraft" => {
            json!({"command":"object.setProps","params":{"ids":[b.node],"name":name,"opacity":opacity*100.0}})
        }
        "figcraft" => {
            json!({"command":"node.set","params":{"ids":[b.node],"props":{"name":name,"opacity":opacity}}})
        }
        _ => return Err(Error::Capability("native profile".into())),
    };
    if b.live {
        let (document, revision) = expected
            .ok_or_else(|| Error::Capability("conditional native token required".into()))?;
        params["expected"] = json!({"document":document,"revision":revision});
    }
    bound_call(b, "engine.execute", params)?;
    Ok(())
}
impl Runtime {
    pub fn initialize_binding(&self, b: &mut Binding) -> Result<()> {
        if b.live && b.token_file.is_none() {
            return Err(Error::Capability(
                "live native modification requires an authenticated control endpoint".into(),
            ));
        }
        b.path = self.confined(&b.path)?;
        if let Some(path) = &b.token_file {
            let path = std::fs::canonicalize(path).map_err(fail)?;
            if !path.starts_with(&self.root)
                || !path.is_file()
                || std::fs::metadata(&path).map_err(fail)?.len() > 4096
            {
                return Err(Error::Capability(
                    "native credential must be a small file inside the explicit project root"
                        .into(),
                ));
            }
            b.token_file = Some(path);
        }
        b.native_document = None;
        let (_, token) = read_state(b)?;
        if b.live {
            b.native_document = token.map(|t| t.0);
        }
        Ok(())
    }
    /// A durable creation intent plus an atomic native batch with a unique marker
    /// makes a lost create reply discoverable before retrying. Only after native
    /// save do we publish the binding; crashes leave a resumable creating intent.
    pub fn place_link(&mut self, mut intent: PlaceLink) -> Result<Value> {
        intent.path = self.confined(&intent.path)?;
        let marker = format!("CraftLink staging {}", intent.id);
        let prior = self.store.binding(intent.id);
        let (source, initial, geometry) = if let Ok(saved) = prior {
            if saved.get("phase").and_then(Value::as_str) == Some("creating") {
                let old: PlaceLink = parse(
                    saved
                        .get("intent")
                        .cloned()
                        .ok_or_else(|| fail("creation intent"))?,
                )?;
                if old != intent {
                    return Err(Error::Conflict("placement id reused".into()));
                }
                (
                    parse::<Id>(
                        saved
                            .get("source")
                            .cloned()
                            .ok_or_else(|| fail("creation source"))?,
                    )?,
                    saved
                        .get("initial")
                        .cloned()
                        .ok_or_else(|| fail("creation properties"))?,
                    saved
                        .get("geometry")
                        .cloned()
                        .ok_or_else(|| fail("creation geometry"))?,
                )
            } else {
                let binding: Binding = parse(saved.clone())?;
                if binding.placement != Some(intent.placement)
                    || binding.profile != intent.profile
                    || binding.path != intent.path
                {
                    return Err(Error::Conflict("placement id reused".into()));
                }
                return Ok(saved);
            }
        } else {
            if !["figcraft", "vectorcraft"].contains(&intent.profile.as_str()) {
                return Err(Error::Capability("native placement profile".into()));
            }
            let source: Binding = parse(self.store.binding(intent.source_binding)?)?;
            let head = self.store.object(source.object)?;
            validate(&head.value)?;
            read(&source)?;
            let doc = call(source.port, "document.inspect", json!({}))?;
            let node =
                find(&doc, source.node).ok_or_else(|| Error::Missing("source rectangle".into()))?;
            let geo = node
                .get("bounds")
                .or_else(|| node.get("absoluteBounds"))
                .unwrap_or(node);
            let mut geometry = serde_json::Map::new();
            for key in ["x", "y", "width", "height"] {
                let n = geo
                    .get(key)
                    .and_then(Value::as_f64)
                    .filter(|n| n.is_finite() && n.abs() < 1e7)
                    .ok_or_else(|| Error::Capability("source rectangle geometry".into()))?;
                geometry.insert(key.into(), json!(n));
            }
            self.store.set_binding(intent.id,&json!({"phase":"creating","intent":intent,"source":source.object,"initial":head.value,"geometry":geometry}))?;
            (source.object, head.value, Value::Object(geometry))
        };
        let doc = call(intent.port, "document.inspect", json!({}))?;
        let active = doc
            .get("path")
            .and_then(Value::as_str)
            .ok_or_else(|| fail("target must be saved"))?;
        if std::fs::canonicalize(active).map_err(fail)? != intent.path {
            return Err(Error::Conflict(
                "active target differs from placement file".into(),
            ));
        }
        fn marked(v: &Value, name: &str, ids: &mut Vec<u64>) {
            match v {
                Value::Object(m) => {
                    if m.get("name").and_then(Value::as_str) == Some(name)
                        && let Some(id) = m.get("id").and_then(Value::as_u64)
                    {
                        ids.push(id);
                    }
                    for v in m.values() {
                        marked(v, name, ids);
                    }
                }
                Value::Array(a) => {
                    for v in a {
                        marked(v, name, ids);
                    }
                }
                _ => {}
            }
        }
        let mut ids = Vec::new();
        marked(&doc, &marker, &mut ids);
        if ids.is_empty() {
            let (cmd, props) = if intent.profile == "vectorcraft" {
                (
                    "object.setProps",
                    json!({"name":marker,"opacity":initial["opacity"].as_f64().unwrap_or(1.0)*100.0}),
                )
            } else {
                (
                    "node.set",
                    json!({"props":{"name":marker,"opacity":initial["opacity"]}}),
                )
            };
            call(
                intent.port,
                "engine.execute",
                json!({"command":"command.batch","params":{"label":"Place CraftLink rectangle","commands":[{"command":"shape.rectangle","params":geometry},{"command":cmd,"params":props}]}}),
            )?;
            marked(
                &call(intent.port, "document.inspect", json!({}))?,
                &marker,
                &mut ids,
            );
        }
        if ids.len() != 1 {
            return Err(Error::Conflict(
                "placement marker missing or ambiguous; no duplicate created".into(),
            ));
        }
        call(
            intent.port,
            "engine.execute",
            json!({"command":"file.save","params":{"path":intent.path}}),
        )?;
        self.store.commit(Transaction {
            operation: intent.operation,
            changes: vec![Change {
                object: intent.placement,
                document: intent.document,
                application: intent.profile.clone(),
                kind: "rectangle".into(),
                expected: 0,
                value: initial,
                native: None,
            }],
        })?;
        self.store
            .link(intent.link, source, intent.placement, "semantic")?;
        let mut b = Binding {
            id: intent.id,
            object: source,
            profile: intent.profile,
            port: intent.port,
            path: intent.path,
            node: *ids.first().ok_or_else(|| fail("placement node"))?,
            baseline: json!({"name":marker,"opacity":1.0}),
            applied: 0,
            observed_hash: String::new(),
            enabled: true,
            status: "stale".into(),
            pending: None,
            detail: None,
            placement: Some(intent.placement),
            live:false,native_document:None,token_file:None,
            fidelity:"semantic properties: name/opacity only; placement uses axis-aligned bounds; paints/effects remain in opaque source snapshots".into(),
        };
        b.baseline = read(&b)?;
        self.store.set_binding(b.id, &json!(b))?;
        self.reconcile(b.id)?;
        self.store.binding(b.id)
    }
    pub fn confined(&self, path: &Path) -> Result<PathBuf> {
        let path = std::fs::canonicalize(path).map_err(|e| Error::Missing(e.to_string()))?;
        if !path.starts_with(&self.root)
            || !path.is_file()
            || path.starts_with(self.root.join(".craftlink"))
        {
            return Err(Error::Capability(
                "native file outside project or in private store".into(),
            ));
        }
        if !matches!(
            path.extension().and_then(|s| s.to_str()),
            Some("figcraft" | "vectorcraft")
        ) {
            return Err(Error::Capability("native extension".into()));
        }
        Ok(path)
    }
    fn saved_snapshot(&self, b: &Binding) -> Result<String> {
        let path = self.confined(&b.path)?;
        if std::fs::metadata(&path).map_err(fail)?.len() > 128 * 1024 * 1024 {
            return Err(fail("native snapshot exceeds 128 MiB"));
        }
        self.store.put_blob(&std::fs::read(path).map_err(fail)?)
    }
    fn live_snapshot(&self, b: &Binding, expected: Option<(u64, u64)>) -> Result<String> {
        // Conflict snapshots retain unsaved native features too, using the apps' copy APIs.
        use base64::Engine;
        let mut request = match b.profile.as_str() {
            "vectorcraft" => json!({"command":"file.saveCopy","params":{}}),
            "figcraft" => json!({"command":"file.saveAs","params":{"data":true}}),
            _ => return Err(Error::Capability("native snapshot profile".into())),
        };
        if b.live {
            let (document, revision) = expected
                .ok_or_else(|| Error::Capability("snapshot requires native revision".into()))?;
            request["expected"] = json!({"document":document,"revision":revision});
        }
        let exported = bound_call(b, "engine.execute", request)?;
        let encoded = exported
            .get("dataBase64")
            .or_else(|| exported.get("data"))
            .and_then(Value::as_str)
            .ok_or_else(|| {
                fail("native snapshot returned no bytes; preserving live app without overwriting")
            })?;
        self.store.put_blob(
            &base64::engine::general_purpose::STANDARD
                .decode(encoded)
                .map_err(fail)?,
        )
    }
    fn conflict(&mut self, b: &mut Binding, live: &Value, head: &Object) -> Result<()> {
        let native = self.saved_snapshot(b)?;
        let live_native = self.live_snapshot(b, read_state(b)?.1)?;
        self.store.record_conflict(&json!({"binding":b,"local":live,"committed":head,"last_saved_native":native,"live_native":live_native}),"native properties differ from baseline and committed revision")?;
        b.status = "conflicted".into();
        b.detail = Some(
            "local intent and last saved native bytes retained; explicit resolution required"
                .into(),
        );
        self.store.set_binding(b.id, &json!(b))?;
        Err(Error::Conflict("native edit retained".into()))
    }
    pub fn ingest(&mut self, id: Id) -> Result<()> {
        self.ingest_observation(id, false)
    }
    pub fn ingest_live(&mut self, id: Id) -> Result<()> {
        self.ingest_observation(id, true)
    }
    fn ingest_observation(&mut self, id: Id, unsaved: bool) -> Result<()> {
        let mut b: Binding = parse(self.store.binding(id)?)?;
        if !b.enabled || b.status == "conflicted" {
            return Ok(());
        }
        // Saved-file notifications for live bindings must capture the current
        // unsaved native state too, rather than pair it with an older saved blob.
        let unsaved = unsaved || b.live;
        let hash = self.saved_snapshot(&b)?;
        if !unsaved && hash == b.observed_hash {
            return Ok(());
        }
        let (live, observed_revision) = read_state(&b)?;
        let head = self.store.object(b.object)?;
        if same(&live, &head.value) {
            b.baseline = head.value;
            b.applied = head.revision;
            b.observed_hash = hash;
            b.pending = None;
            b.status = "current".into();
        } else if b
            .pending
            .as_ref()
            .is_some_and(|pending| same(pending, &live))
        {
            // The process stopped after applying our durable intent but before
            // recording its receipt. This is an acknowledged old projection,
            // not a new edit competing with a newer committed/offline source.
            b.baseline = live;
            b.pending = None;
            b.status = "stale".into();
            b.detail = None;
        } else if same(&live, &b.baseline) {
            b.observed_hash = hash;
        } else if same(&head.value, &b.baseline) {
            let payload = if unsaved {
                let payload = self.live_snapshot(&b, observed_revision)?;
                let (after, captured_revision) = read_state(&b)?;
                // FigCraft v1 command bookkeeping advances even for its byte-only
                // copy. The expected guard pins export to the observed document;
                // any additional revision movement still rejects A->B->A capture.
                let expected_after = if b.profile == "figcraft" {
                    observed_revision
                        .and_then(|(doc, revision)| revision.checked_add(1).map(|r| (doc, r)))
                } else {
                    observed_revision
                };
                if !same(&after, &live)
                    || expected_after.is_none()
                    || expected_after != captured_revision
                {
                    self.store.record_conflict(
                        &json!({"binding":b.id,"observed":live,"live_native":payload}),
                        "native document/revision changed while capturing its unsaved snapshot",
                    )?;
                    return Err(Error::Conflict(
                        "native edit changed during snapshot capture; intent retained".into(),
                    ));
                }
                payload
            } else {
                hash.clone()
            };
            self.store.commit(Transaction {
                operation: Id::new_v4(),
                changes: vec![Change {
                    object: head.object,
                    document: head.document,
                    application: head.application,
                    kind: head.kind,
                    expected: head.revision,
                    value: live.clone(),
                    native: Some(craftlink_core::NativePayload {
                        hash: payload,
                        format: format!("application/x-{}", b.profile),
                        application: b.profile.clone(),
                    }),
                }],
            })?;
            b.baseline = live;
            b.applied = head.revision + 1;
            b.observed_hash = hash;
            b.pending = None;
            b.status = "current".into();
        } else {
            return self.conflict(&mut b, &live, &head);
        }
        self.store.set_binding(id, &json!(b))
    }
    pub fn reconcile(&mut self, id: Id) -> Result<()> {
        let mut b: Binding = parse(self.store.binding(id)?)?;
        if !b.enabled || b.status == "conflicted" {
            return Ok(());
        }
        self.confined(&b.path)?;
        let head = self.store.object(b.object)?;
        let (live, expected) = read_state(&b)?;
        // A native edit while no newer committed revision exists is local work,
        // not a conflict. Ingest it only on its save event. In particular a late
        // notification from our previous projection must not freeze a new edit.
        if b.applied == head.revision && same(&head.value, &b.baseline) && !same(&live, &head.value)
        {
            b.status = "locally-modified".into();
            self.store.set_binding(id, &json!(b))?;
            return Ok(());
        }
        if !same(&live, &head.value)
            && !same(&live, &b.baseline)
            && !b.pending.as_ref().is_some_and(|p| same(p, &live))
        {
            return self.conflict(&mut b, &live, &head);
        }
        if b.applied == head.revision && same(&live, &head.value) && b.status == "current" {
            return Ok(());
        }
        let before = self.saved_snapshot(&b)?;
        b.status = "applying".into();
        b.pending = Some(head.value.clone());
        b.detail = Some(format!("pre-update native {before}"));
        self.store.set_binding(id, &json!(b))?;
        if !same(&live, &head.value)
            && let Err(e) = write(&b, &head.value, expected)
        {
            if matches!(e, Error::Conflict(_)) {
                let current = read(&b)?;
                return self.conflict(&mut b, &current, &head);
            }
            return Err(e);
        }
        if !same(&read(&b)?, &head.value) {
            return Err(Error::Conflict("native verification failed".into()));
        }
        if !b.live {
            command(&b, "file.save", json!({"path":b.path}))?;
        }
        b.observed_hash = self.saved_snapshot(&b)?;
        b.baseline = head.value;
        b.applied = head.revision;
        b.pending = None;
        b.status = "current".into();
        b.detail = None;
        self.store.set_binding(id, &json!(b))
    }
    pub fn mark_error(&mut self, id: Id, e: &Error) {
        if let Ok(value) = self.store.binding(id)
            && let Ok(mut b) = parse::<Binding>(value)
        {
            if b.status != "conflicted" {
                b.status = match e {
                    Error::Missing(_) => "missing",
                    Error::Conflict(_) => "conflicted",
                    _ => "stale",
                }
                .into();
            }
            b.detail = Some(e.to_string());
            if let Err(e) = self.store.set_binding(id, &json!(b)) {
                eprintln!("binding persistence: {e}");
            }
        }
    }
    pub fn reconcile_all(&mut self) {
        match self.store.bindings() {
            Ok(values) => {
                for value in values {
                    if let Ok(b) = parse::<Binding>(value)
                        && let Err(e) = self.reconcile(b.id)
                    {
                        self.mark_error(b.id, &e);
                    }
                }
            }
            Err(e) => eprintln!("bindings: {e}"),
        }
    }
    pub fn recover(&mut self) {
        match self.store.bindings() {
            Ok(values) => {
                for value in values {
                    if let Ok(b) = parse::<Binding>(value)
                        && let Err(e) = if b.live {
                            self.ingest_live(b.id)
                        } else {
                            self.ingest(b.id)
                        }
                    {
                        self.mark_error(b.id, &e);
                    }
                }
            }
            Err(e) => eprintln!("recover bindings: {e}"),
        }
        self.reconcile_all();
    }
}
