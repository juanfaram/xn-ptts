#!/usr/bin/env python3
"""EDF-only C patch on pinned Phonon; Q remains Tokio FIFO."""
from pathlib import Path
p=Path("ptts-ws-server/src/handler.rs")
s=p.read_text()
def change(a,b):
    global s
    assert s.count(a)==1,(a,s.count(a))
    s=s.replace(a,b,1)

change("use std::time::Duration;",'''use std::time::{Duration, Instant};
use std::sync::{Arc, Mutex, OnceLock};
use std::sync::atomic::{AtomicU64, Ordering};
use tokio::sync::{Notify, OwnedSemaphorePermit};
struct EdfState { queue: Mutex<Vec<(u64, Instant)>>, notify: Notify, next: AtomicU64 }
static EDF: OnceLock<Arc<EdfState>> = OnceLock::new();
fn edf() -> Arc<EdfState> {
    EDF.get_or_init(|| Arc::new(EdfState {
        queue: Mutex::new(Vec::new()), notify: Notify::new(), next: AtomicU64::new(0)
    })).clone()
}
struct EdfLease { permit: Option<OwnedSemaphorePermit>, state: Arc<EdfState> }
impl Drop for EdfLease {
    fn drop(&mut self) {
        self.permit.take(); // release BEFORE notifying next waiter
        self.state.notify.notify_waiters();
    }
}
struct EdfWaiting { id: u64, state: Arc<EdfState> }
impl Drop for EdfWaiting {
    fn drop(&mut self) {
        self.state.queue.lock().unwrap().retain(|(id,_)| *id != self.id);
        self.state.notify.notify_waiters();
    }
}
async fn acquire_edf(app: &AppState, deadline: Instant) -> Option<EdfLease> {
    let state=edf();
    let id=state.next.fetch_add(1, Ordering::SeqCst);
    {
        let mut q=state.queue.lock().unwrap();
        if q.len()>=64 { return None; }
        q.push((id,deadline));
    }
    let waiting=EdfWaiting { id, state: state.clone() };
    loop {
        let notified=state.notify.notified();
        tokio::pin!(notified);
        notified.as_mut().enable(); // register before checking queue
        if Instant::now()>=deadline { return None; }
        let permit={
            let q=state.queue.lock().unwrap();
            let first=q.iter().min_by_key(|(seq,d)| (*d,*seq)).map(|(seq,_)| *seq);
            if first==Some(id) { app.requests.clone().try_acquire_owned().ok() } else { None }
        };
        if let Some(permit)=permit {
            drop(waiting);
            return Some(EdfLease { permit:Some(permit), state });
        }
        tokio::select! {
            _ = &mut notified => {},
            _ = tokio::time::sleep_until(tokio::time::Instant::from_std(deadline)) => return None,
        }
    }
}
''')
change("    let permit = match app.requests.clone().try_acquire_owned() {",'''    let connections = CONNECTIONS.get_or_init(|| Arc::new(tokio::sync::Semaphore::new(134)));
    let permit = match connections.clone().try_acquire_owned() {''')
change("const REPLY_QUEUE: usize = 16;",'''static CONNECTIONS: OnceLock<Arc<tokio::sync::Semaphore>> = OnceLock::new();
const REPLY_QUEUE: usize = 16;''')
change("TtsRequest::Flush { flush_id },","TtsRequest::Flush { flush_id, deadline_ms },")
change('''                flush_buffer(&app, session, text_buffer, stream_id, encoder, reply_tx, cancel)
                    .await?;
                let _ = reply_tx.send(TtsReply::Flushed { flush_id }).await;''','''                let deadline = Instant::now() + Duration::from_millis(deadline_ms.unwrap_or(1000));
                flush_buffer(&app, session, text_buffer, stream_id, encoder, reply_tx, cancel, Some(deadline))
                    .await?;
                let _ = reply_tx.send(TtsReply::Flushed { flush_id }).await;''')
change('''                flush_buffer(&app, session, text_buffer, stream_id, encoder, reply_tx, cancel)
                    .await?;
                let _ = reply_tx.send(TtsReply::EndOfStream).await;''','''                flush_buffer(&app, session, text_buffer, stream_id, encoder, reply_tx, cancel, None)
                    .await?;
                let _ = reply_tx.send(TtsReply::EndOfStream).await;''')
change('''async fn flush_buffer(
    app: &AppState,
    session: &Session,
    text_buffer: &mut String,
    stream_id: &mut u32,
    encoder: &mut Encoder,
    reply_tx: &mpsc::Sender<TtsReply>,
    cancel: &mut watch::Receiver<bool>,
) -> Result<()> {''','''async fn flush_buffer(
    app: &AppState,
    session: &Session,
    text_buffer: &mut String,
    stream_id: &mut u32,
    encoder: &mut Encoder,
    reply_tx: &mpsc::Sender<TtsReply>,
    cancel: &mut watch::Receiver<bool>,
    deadline: Option<Instant>,
) -> Result<()> {''')
change("generate_one(app, session, &text, stream_id_now, encoder, reply_tx, cancel).await",
       "generate_one(app, session, &text, stream_id_now, encoder, reply_tx, cancel, deadline).await")
change('''async fn generate_one(
    app: &AppState,
    session: &Session,
    text: &str,
    stream_id: u32,
    encoder: &mut Encoder,
    reply_tx: &mpsc::Sender<TtsReply>,
    cancel: &mut watch::Receiver<bool>,
) -> Result<()> {''','''async fn generate_one(
    app: &AppState,
    session: &Session,
    text: &str,
    stream_id: u32,
    encoder: &mut Encoder,
    reply_tx: &mpsc::Sender<TtsReply>,
    cancel: &mut watch::Receiver<bool>,
    deadline: Option<Instant>,
) -> Result<()> {''')
change("    let seed = app.seed_base ^ (stream_id as u64).wrapping_mul(0x9E3779B97F4A7C15);",'''    let started=Instant::now();
    let Some(lease)=acquire_edf(app,deadline.unwrap_or_else(|| Instant::now()+Duration::from_millis(1000))).await else {
        send_error(reply_tx,429,serde_json::json!({"reason":"deadline_expired_or_queue_full",
            "retry_after_ms":80,"retryable":true}).to_string()).await?;
        return Ok(());
    };
    tracing::info!(stream_id,wait_ms=started.elapsed().as_secs_f64()*1000.0,"KAIROS_C_EDF_ADMITTED");
    let seed = app.seed_base ^ (stream_id as u64).wrapping_mul(0x9E3779B97F4A7C15);''')
change("    outcome.and(generated)\n}", "    drop(lease);\n    outcome.and(generated)\n}")
p.write_text(s)
proto=Path("ptts-ws-server/src/protocol.rs")
t=proto.read_text()
assert t.count("    Flush {\n        flush_id: u64,\n    },")==1
t=t.replace("    Flush {\n        flush_id: u64,\n    },","    Flush {\n        flush_id: u64,\n        #[serde(default)]\n        deadline_ms: Option<u64>,\n    },")
proto.write_text(t)
print("C EDF applied; deadline from Flush; queue 64; connection cap 134")
