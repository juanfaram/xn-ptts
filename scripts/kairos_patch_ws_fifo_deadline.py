#!/usr/bin/env python3
"""B-high+Q fixed-three admission control patch; applies ONLY to pinned WS handler, never upstream.
Connection cap=134, generation permits from --max-concurrent-requests,
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
const CONNECTION_LIMIT: usize = 134;
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
    let deadline = deadline.unwrap_or_else(|| std::time::Instant::now() + Duration::from_millis(1000));
    let remaining = deadline.saturating_duration_since(std::time::Instant::now());
    let permit = match tokio::time::timeout(remaining, app.requests.clone().acquire_owned()).await {
        Ok(Ok(p)) => p,
        _ => {
            send_error(reply_tx, 429, serde_json::json!({"reason":"deadline_expired","retry_after_ms":80,"retryable":true}).to_string()).await?;
            return Ok(());
        }
    };
    drop(waiting_guard);
    if std::time::Instant::now() >= deadline {
        drop(permit);
        send_error(reply_tx, 429, serde_json::json!({"reason":"deadline_expired","retry_after_ms":80,"retryable":true}).to_string()).await?;
        return Ok(());
    }
    tracing::info!(stream_id, queue_wait_ms = queue_started.elapsed().as_secs_f64() * 1000.0, "KAIROS_BHIGH_Q_GENERATION_ADMITTED");
    let seed = app.seed_base ^ (stream_id as u64).wrapping_mul(0x9E3779B97F4A7C15);""")
replace("TtsRequest::Flush { flush_id },","TtsRequest::Flush { flush_id, deadline_ms, deadline_unix_ms },")
replace("""                flush_buffer(&app, session, text_buffer, stream_id, encoder, reply_tx, cancel)
                    .await?;
                let _ = reply_tx.send(TtsReply::Flushed { flush_id }).await;""","""                let deadline = {
                    let remaining=deadline_unix_ms.map(|ms| {
                        let now=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_millis() as u64;
                        ms.saturating_sub(now)
                    }).unwrap_or(deadline_ms.unwrap_or(1000));
                    std::time::Instant::now() + Duration::from_millis(remaining)
                };
                flush_buffer(&app, session, text_buffer, stream_id, encoder, reply_tx, cancel, Some(deadline))
                    .await?;
                let _ = reply_tx.send(TtsReply::Flushed { flush_id }).await;""")
replace("""                flush_buffer(&app, session, text_buffer, stream_id, encoder, reply_tx, cancel)
                    .await?;
                let _ = reply_tx.send(TtsReply::EndOfStream).await;""","""                flush_buffer(&app, session, text_buffer, stream_id, encoder, reply_tx, cancel, None)
                    .await?;
                let _ = reply_tx.send(TtsReply::EndOfStream).await;""")
replace("    cancel: &mut watch::Receiver<bool>,\n) -> Result<()> {", "    cancel: &mut watch::Receiver<bool>,\n) -> Result<()> {") # no-op
replace("""async fn flush_buffer(
    app: &AppState,
    session: &Session,
    text_buffer: &mut String,
    stream_id: &mut u32,
    encoder: &mut Encoder,
    reply_tx: &mpsc::Sender<TtsReply>,
    cancel: &mut watch::Receiver<bool>,
) -> Result<()> {""","""async fn flush_buffer(
    app: &AppState,
    session: &Session,
    text_buffer: &mut String,
    stream_id: &mut u32,
    encoder: &mut Encoder,
    reply_tx: &mpsc::Sender<TtsReply>,
    cancel: &mut watch::Receiver<bool>,
    deadline: Option<std::time::Instant>,
) -> Result<()> {""")
replace("generate_one(app, session, &text, stream_id_now, encoder, reply_tx, cancel).await","generate_one(app, session, &text, stream_id_now, encoder, reply_tx, cancel, deadline).await")
replace("""async fn generate_one(
    app: &AppState,
    session: &Session,
    text: &str,
    stream_id: u32,
    encoder: &mut Encoder,
    reply_tx: &mpsc::Sender<TtsReply>,
    cancel: &mut watch::Receiver<bool>,
) -> Result<()> {""","""async fn generate_one(
    app: &AppState,
    session: &Session,
    text: &str,
    stream_id: u32,
    encoder: &mut Encoder,
    reply_tx: &mpsc::Sender<TtsReply>,
    cancel: &mut watch::Receiver<bool>,
    deadline: Option<std::time::Instant>,
) -> Result<()> {""")
replace("    outcome.and(generated)\n}", "    drop(permit);\n    outcome.and(generated)\n}")
s += """
#[cfg(test)]
mod kairos_fifo_tests {
    #[tokio::test]
    async fn earlier_long_deadline_is_admitted_before_later_short() {
        use std::sync::Arc;
        use tokio::sync::Semaphore;
        use std::time::Duration;
        let sem=Arc::new(Semaphore::new(1));
        let blocker=sem.clone().acquire_owned().await.unwrap();
        let (tx,mut rx)=tokio::sync::mpsc::channel(2);
        let first=sem.clone();let a=tx.clone();
        let long=tokio::spawn(async move {
            let permit=first.acquire_owned().await.unwrap();
            a.send("long").await.unwrap();
            tokio::time::sleep(Duration::from_millis(20)).await;
            drop(permit);
        });
        tokio::time::sleep(Duration::from_millis(20)).await;
        let second=sem.clone();
        let short=tokio::spawn(async move {
            let _permit=second.acquire_owned().await.unwrap();
            tx.send("short").await.unwrap();
        });
        tokio::time::sleep(Duration::from_millis(20)).await;
        drop(blocker);
        assert_eq!(tokio::time::timeout(Duration::from_secs(1),rx.recv()).await.unwrap(),Some("long"));
        long.await.unwrap();short.await.unwrap();
        assert_eq!(sem.available_permits(),1);
    }
}
"""
p.write_text(s)
print("FIFO+deadline discard applied: 134 connections, fixed generation permits configured as 3, FIFO queue 64, 80ms deadline")

proto=Path("ptts-ws-server/src/protocol.rs")
ptext=proto.read_text()
assert ptext.count("    Flush {\n        flush_id: u64,\n    },")==1
ptext=ptext.replace("    Flush {\n        flush_id: u64,\n    },","    Flush {\n        flush_id: u64,\n        #[serde(default)]\n        deadline_ms: Option<u64>,\n        #[serde(default)]\n        deadline_unix_ms: Option<u64>,\n    },")
proto.write_text(ptext)
