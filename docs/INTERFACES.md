# Interfaces

See `detection.schema.json` for canonical Detection JSON Schema.

Wire frame: 12-byte header `>BBHBBHI` + payload + 2-byte CRC16-CCITT-FALSE.

Profiles: `niem_mo_observation`, `spotrep_style_text`, `json`, `cbor`.

## Text report

`detection_to_text_report(det, lang="en"|"fr")` writes the slash-delimited report.
English tokens are the historical labels. French tokens and the validate/replay/metrics help and validation strings live in `tvgw.messages`.
The French strings are an unreviewed machine-assisted draft and need qualified human review before any use.
Domain, service, and priority codes are data and are not relabeled.

## Metrics HTTP

`tvgw metrics serve` binds a stdlib HTTP server and exposes Prometheus text exposition at `/metrics`.
Values come from one in-process simulated scenario: queue depth, maximum queue depth, delivery latency by priority, ARQ retries, failures by priority, profile validation rejects, and link state `down` / `idle` / `busy`.
`results/metrics.prom` and `results/splunk_hec_events.jsonl` remain file exports written by the benchmark driver.
No external collector is included.

## Cross-source association

`tvgw.associate.associate_for_transmission` merges records whose `source_sensor` values differ when they are inside the configured distance and time of the cluster anchor and share an object class (`association.allow_cross_class` overrides the class check).
The anchor is the highest-confidence member; equal confidence keeps the smallest `detection_id`.
A candidate is compared with that anchor, not with every member.
The kept record uses the anchor's position, class, and priority. `attributes["contributing_source_ids"]` lists contributor detection ids.
The M3 delivery grid does not call this function.
Benchmark command from the repository root: `.venv/bin/python scripts/bench_association.py`.
