#!/usr/bin/env python3
"""Patch the pinned official Phonon bench for independent concurrent stream timing.
Fails closed if source anchors are different."""
from pathlib import Path
p=Path("ptts/examples/bench.rs")
s=p.read_text()
def once(old,new):
 global s
 assert s.count(old)==1, (old,s.count(old))
 s=s.replace(old,new,1)
once("    /// Measured iterations.",'''    /// Concurrent independent streaming requests.
    #[arg(long, default_value_t = 1)]
    concurrency: usize,

    /// CSV output of consumer-side chunk events.
    #[arg(long)]
    events_csv: Option<std::path::PathBuf>,

    /// Measured concurrent waves.
    #[arg(long, default_value_t = 3)]
    repeats: usize,

    /// Measured iterations.''')
once("fn bench_synth(args: &Args, normalize: Normalize, quant: Quant) -> Result<()> {",'''fn kairos_concurrent(tts: &Synth, args: &Args) -> Result<()> {
    use std::io::Write;
    use std::sync::{Arc, Barrier};
    use sha2::{Digest, Sha256};
    anyhow::ensure!(args.concurrency >= 1 && args.repeats >= 1, "invalid k/repeats");
    let path = args.events_csv.as_ref().context("--events-csv required")?;
    let mut out = std::io::BufWriter::new(std::fs::File::create(path)?);
    writeln!(out, "wave,phase,k,flow,chunk,arrival_ns,interval_ns,samples,ttfa_ns,sha256")?;
    let opts = SpeechOptions::default().seed(args.seed);
    for wave in 0..(args.warmup + args.repeats) {
        let barrier = Arc::new(Barrier::new(args.concurrency + 1));
        let mut results = Vec::new();
        std::thread::scope(|scope| -> Result<()> {
            let mut handles = Vec::new();
            for flow in 0..args.concurrency {
                let gate = Arc::clone(&barrier);
                let options = &opts;
                handles.push(scope.spawn(move || -> Result<_> {
                    gate.wait();
                    let start = Instant::now();
                    let mut chunks = Vec::new();
                    let mut hasher = Sha256::new();
                    for pcm in tts.stream_with(&args.input, options)? {
                        let pcm = pcm?;
                        if pcm.is_empty() { continue; }
                        let at = start.elapsed().as_nanos();
                        for x in &pcm { hasher.update(x.to_bits().to_le_bytes()); }
                        chunks.push((at, pcm.len()));
                    }
                    anyhow::ensure!(!chunks.is_empty(), "empty stream");
                    Ok((flow, chunks, format!("{:x}", hasher.finalize())))
                }));
            }
            barrier.wait();
            for handle in handles {
                results.push(handle.join().map_err(|_| anyhow::anyhow!("worker panic"))??);
            }
            Ok(())
        })?;
        for (flow, chunks, hash) in results {
            let ttfa = chunks[0].0;
            for (i, (at, samples)) in chunks.iter().enumerate() {
                let interval = if i == 0 { String::new() } else {
                    (at - chunks[i-1].0).to_string()
                };
                writeln!(out, "{},{},{},{},{},{},{},{},{},{}",
                    wave, if wave < args.warmup {"warmup"} else {"measured"},
                    args.concurrency, flow, i, at, interval, samples, ttfa, hash)?;
            }
        }
    }
    out.flush()?;
    Ok(())
}

fn bench_synth(args: &Args, normalize: Normalize, quant: Quant) -> Result<()> {''')
once("    let runs = measure(args, || one_synth(&tts, &opts, args))?;",'''    if args.events_csv.is_some() || args.concurrency > 1 {
        return kairos_concurrent(&tts, args);
    }
    let runs = measure(args, || one_synth(&tts, &opts, args))?;''')
p.write_text(s)
print("Applied KAIROS concurrent bench patch")
