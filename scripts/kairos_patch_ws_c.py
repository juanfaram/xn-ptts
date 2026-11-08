#!/usr/bin/env python3
"""Experimental C admission patch; applies ONLY to pinned WS handler, never upstream.
Connection cap=200, generation permits from --max-concurrent-requests,
bounded waiting=64, timeout=80ms (one initial 80ms audio chunk on 31m).
NO deadline-priority scheduler; FIFO Tokio semaphore. Do not claim otherwise.
429 cannot be sent after WebSocket upgrade: send protocol Error{code:429}.
"""
from pathlib import Path
p=Path("ptts-ws-server/src/handler.rs")
s=p.read_text()
def replace(old,new):
 global s
 assert s.count(old)==1,(old,s.count(old))
 s=s.replace(old,new,1)
replace("use std::time::Duration;", """use std::time::Duration;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::OnceLock;
static CONNECTIONS: OnceLock<std::sync::Arc<tokio::sync::Semaphore>> = OnceLock::new();
static WAITING: AtomicUsize = AtomicUsize::new(0);
const CONNECTION_LIMIT: usize = 200;
const MAX_WAITING: usize = 64;
const ADMISSION_TIMEOUT: Duration = Duration::from_millis(80);
struct WaitingGuard;
impl Drop for WaitingGuard {
    fn drop(&mut self) { WAITING.fetch_sub(1, Ordering::SeqCst); }
}
""")
replace("    let permit = match app.requests.clone().try_acquire_owned() {",
"""    let connections = CONNECTIONS.get_or_init(|| std::sync::Arc::new(tokio::sync::Semaphore::new(CONNECTION_LIMIT)));
    let permit = match connections.clone().try_acquire_owned() {""")
replace('                "the server is busy; retry after an active WebSocket session closes",',
'                "connection cap reached; retry after a session closes",')
replace("    let seed = app.seed_base ^ (stream_id as u64).wrapping_mul(0x9E3779B97F4A7C15);",
"""    // Generation-only admission. 429 is a WS protocol error, not HTTP after upgrade.
    let old = WAITING.fetch_add(1, Ordering::SeqCst);
    if old >= MAX_WAITING {
        WAITING.fetch_sub(1, Ordering::SeqCst);
        send_error(reply_tx, 429, serde_json::json!({"reason":"generation_queue_full","retry_after_ms":80,"retryable":true}).to_string()).await?;
        return Ok(());
    }
    let waiting_guard = WaitingGuard;
    let queue_started = std::time::Instant::now();
    let permit = match tokio::time::timeout(ADMISSION_TIMEOUT, app.requests.clone().acquire_owned()).await {
        Ok(Ok(p)) => p,
        _ => {
            send_error(reply_tx, 429, serde_json::json!({"reason":"generation_admission_timeout","retry_after_ms":80,"retryable":true}).to_string()).await?;
            return Ok(());
        }
    };
    drop(waiting_guard);
    tracing::info!(stream_id, queue_wait_ms = queue_started.elapsed().as_secs_f64() * 1000.0, "KAIROS_C_GENERATION_ADMITTED");
    let seed = app.seed_base ^ (stream_id as u64).wrapping_mul(0x9E3779B97F4A7C15);""")
replace("    outcome.and(generated)\n}", "    drop(permit);\n    outcome.and(generated)\n}")
p.write_text(s)
print("Experimental C applied: 200 connections, generation permits, queue 64, 80ms deadline, FIFO")
