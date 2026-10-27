# Empirical summary (generated)

<!-- NOT-CLAIMED:BEGIN -->
## What Is Not Claimed (Scope & Limitations)

1. No USMTF / MIL-STD-6040 / NATO APP-11 / ADatP-3 Conformance.
2. No NATO NCDF (ADatP-5653) Conformance or Alignment Claim.
3. No Tactical Waveform or On-Air Radio Interoperability (Link 16, STANAG 4539, STANAG 5066).
4. No Hardware-in-the-Loop RF or Kernel Netem Testing.
5. No Waveform/Ionospheric Multipath Simulation or ITU-R F.1487 Calibration.
6. Public/Simulated Datasets & Synthetic Geolocation Only (HIT-UAV under CC BY 4.0 attribution).
7. Task-Specific Information Selection, Not Lossless Image Compression.
8. No Novel Computer Vision Model Claims or GUI.
9. Evidence Relevant to TRL 4 Only — not certified, not TRL > 4.
10. No learned detection model. Cross-source association is a deterministic distance, time, class, and sensor rule. It does not score whether a detection was correct.
11. French operator strings are an unreviewed machine-assisted draft and need qualified human review before any use. This is not a fully bilingual interface.
12. No Prometheus server, live Splunk deployment, or other monitoring product has been run against the laboratory `/metrics` text or the Splunk-HEC-shaped file.
<!-- NOT-CLAIMED:END -->


## Simulated link model (M3)
All M3 metrics are from the in-process half-duplex link emulator (`linkemu.py`) with Gilbert–Elliot frame impairment, return-path 18-byte bitmap ACK airtime (same loss model), RTO backoff from `config/default.yaml`, and gateway dispatch blocked until the medium is idle. This is a **simulated link model**, not on-air RF.

## Measured M1
- Held-out combined validation: 100.0000% (5000 detections)
- Mutation controls (50 HIT-UAV + 50 FIRMS samples per class): combined reject 100% for all 12 classes

## M2 payload sizes (held-out, median bytes)
HIT-UAV positions in NIEM XML are tagged `[SYNTH-GPS]` in the object name; XML carries fewer fields than JSON/CBOR/text.

| variant | median_bytes | mean_bytes | p95_bytes |
|---|---:|---:|---:|
| xml_raw | 834.0 | 833.7302 | 836.0 |
| xml_gzip | 330.0 | 329.6322 | 332.0 |
| xml_zstd | 339.0 | 338.7568 | 341.0 |
| xml_zstd_dict | 107.0 | 105.2958 | 123.0 |
| json_raw | 416.0 | 412.4898 | 418.0 |
| json_zstd_dict | 391.0 | 386.9284 | 394.0 |
| cbor_raw | 366.0 | 363.4208 | 369.0 |
| text_raw | 298.0 | 294.5194 | 301.0 |
| uncompressed_640x512_8bit | 327680 | 327680 | 327680 |

The zstd dictionary was trained on 500 NASA FIRMS records only while the held-out set is 4,780 HIT-UAV and 220 FIRMS records, so the xml_zstd_dict figure depends on that training choice.

**Assumption (reference only):** a 2 Mbps 1080p H.264 video stream (~2×10⁶ bps) is orders of magnitude larger than the measured detection payloads; payload tables compare structured detection encodings, not video transport.

## M3 delivery grid (cbor profile excerpt; full grid in `m3_delivery_cells.csv`)
Grid: `rates=[300, 600, 1200, 2400, 4800, 9600] loss=[0.0, 0.05, 0.1, 0.2, 0.3] profiles=['xml_raw', 'xml_zstd_dict', 'cbor', 'text', 'json'] sched=['priority', 'fifo'] seeds=20`

| rate_bps | loss | profile | sched | mean_P0 | n_seeds |
|---:|---:|---|---|---:|---:|
| 300 | 0.0 | cbor | fifo | 0.0701 | 20 |
| 300 | 0.0 | cbor | priority | 0.4025 | 20 |
| 300 | 0.05 | cbor | fifo | 0.0558 | 20 |
| 300 | 0.05 | cbor | priority | 0.3482 | 20 |
| 300 | 0.1 | cbor | fifo | 0.0419 | 20 |
| 300 | 0.1 | cbor | priority | 0.3065 | 20 |
| 300 | 0.2 | cbor | fifo | 0.0369 | 20 |
| 300 | 0.2 | cbor | priority | 0.2322 | 20 |
| 300 | 0.3 | cbor | fifo | 0.0282 | 20 |
| 300 | 0.3 | cbor | priority | 0.1362 | 20 |
| 600 | 0.0 | cbor | fifo | 0.2315 | 20 |
| 600 | 0.0 | cbor | priority | 0.8748 | 20 |
| 600 | 0.05 | cbor | fifo | 0.1790 | 20 |
| 600 | 0.05 | cbor | priority | 0.8002 | 20 |
| 600 | 0.1 | cbor | fifo | 0.1356 | 20 |
| 600 | 0.1 | cbor | priority | 0.7263 | 20 |
| 600 | 0.2 | cbor | fifo | 0.1041 | 20 |
| 600 | 0.2 | cbor | priority | 0.5902 | 20 |
| 600 | 0.3 | cbor | fifo | 0.0626 | 20 |
| 600 | 0.3 | cbor | priority | 0.4376 | 20 |

## Priority vs FIFO (paired seeds; excerpt: 16 of 150 rate×loss×profile rows — full table in `m3_delivery_cells.csv`)

| rate_bps | loss | profile | mean_P0_priority | mean_P0_fifo | paired_diff_CI_low | paired_diff_CI_high |
|---:|---:|---|---:|---:|---:|---:|
| 300 | 0.0 | cbor | 0.4025 | 0.0701 | 0.2733 | 0.3898 |
| 300 | 0.0 | json | 0.3231 | 0.0566 | 0.2127 | 0.3153 |
| 300 | 0.0 | text | 0.5266 | 0.0927 | 0.3733 | 0.4898 |
| 300 | 0.0 | xml_raw | 0.0619 | 0.0156 | 0.0334 | 0.0586 |
| 300 | 0.0 | xml_zstd_dict | 0.9907 | 0.6198 | 0.3268 | 0.4151 |
| 300 | 0.05 | cbor | 0.3482 | 0.0558 | 0.2440 | 0.3458 |
| 300 | 0.05 | json | 0.2797 | 0.0426 | 0.1952 | 0.2750 |
| 300 | 0.05 | text | 0.4382 | 0.0762 | 0.3111 | 0.4188 |
| 300 | 0.05 | xml_raw | 0.0544 | 0.0108 | 0.0292 | 0.0567 |
| 300 | 0.05 | xml_zstd_dict | 0.9452 | 0.4718 | 0.4254 | 0.5229 |
| 300 | 0.1 | cbor | 0.3065 | 0.0419 | 0.2154 | 0.3180 |
| 300 | 0.1 | json | 0.2549 | 0.0359 | 0.1772 | 0.2599 |
| 300 | 0.1 | text | 0.3850 | 0.0541 | 0.2665 | 0.4033 |
| 300 | 0.1 | xml_raw | 0.0437 | 0.0108 | 0.0212 | 0.0456 |
| 300 | 0.1 | xml_zstd_dict | 0.9016 | 0.3352 | 0.4986 | 0.6332 |
| 300 | 0.2 | cbor | 0.2322 | 0.0369 | 0.1590 | 0.2369 |

The zstd dictionary was trained on 500 NASA FIRMS records only while the held-out set is 4,780 HIT-UAV and 220 FIRMS records, so the xml_zstd_dict figure depends on that training choice.

## Outage scenario (60 s link down 120–180 s)

| rate_bps | max_retries | mean_p0_failed | ci_low | ci_high | n_seeds |
|---:|---:|---:|---:|---:|---:|
| 600 | 5 | 0.0516 | 0.0456 | 0.0580 | 20 |
| 600 | 8 | 0.0158 | 0.0105 | 0.0212 | 20 |
| 1200 | 5 | 0.0501 | 0.0406 | 0.0599 | 20 |
| 1200 | 8 | 0.0122 | 0.0071 | 0.0182 | 20 |

## Findings That Went Against Expectations

- At ≥4800 bps and 0% loss, mean P0 within-deadline delta (priority−FIFO) across profiles shows no difference between priority and FIFO scheduling (half-duplex dispatch waits for medium idle; priority mainly reorders the gateway queue, not the air interface backlog).
- `xml_raw` at 300 bps / 0% loss: mean P0 within-deadline ≈ 0.062 (multi-fragment airtime exceeds 60 s P0 deadline for typical payloads).
- XSD-only rejection for missing name/time/location remains 0% because `mo:ObservationType` children are minOccurs=0; required fields are enforced by the TVGW application profile layer.
- W3C EXI encoding was not measured (`EXI not measured`).
- NIEM XML omits several fields present in JSON/CBOR/text (confidence, priority, sensor id); M2 byte counts are not a like-for-like field comparison across encodings.

## SHA-256 hashes (inputs)
- niem_zip: `2b899067b5312333935329e6e7665e1eb295f392a51d4a56bc9800dbcc42fcfa`
- niem_zstd_dict: `39b73b339960a296d2246209c6d1099b532d1dc0fcfaa3f36ea2035c06f4691e`
- held_out_corpus: `863f7c7a7dab2bba67c70fdabe07d40d6deaf48dc299edb5e2d798e540130bfd`
- config_default_yaml: `c6ecd6e2639dd2a5f199fd3eee3a2e55ef36ec8c595fcf84b593690ab9030e31`

## SHA-256 hashes (scientific outputs)
- m1_validation_summary.json: `9a501155d5df8b78db337c67281c9a103d26b7abb792d5af5d1d8b8d8085d05d`
- m1_mutation_breakdown.csv: `4e73d48bb33d21eb5af69fa1e8e34ac963ad75f823a9beb4cd8247f1fe6a0282`
- m2_size_comparison.csv: `cf19560d7dd95efca27ac47beee7d02dc26262526a3b5cb121564ee87bf325bc`
- m3_delivery_sweep.csv.gz: `db2f5b0891360257f86cd643708103d7136d25e4cac8b93c6a223d97ee818b69`
- m3_delivery_cells.csv: `051ef30a503827ae9863988941f0c28d17e18a488481a914073effcb2bae218d`
- m3_outage_scenario.csv: `b2f40ded3535c26ee311cf067a317eb94b2bee00a7b78c229229165f156983ed`

Full benchmark wall-clock (last full/slice run): 728.3162274360657 s

Benchmark mode: `full` (CI sweep is a reduced grid, not equivalent to full `make all`).

Provenance: source code content SHA-256 `f7f7828b904936a8d05db7faa4a0b10830fcad52e9bbff79920bfa9f24d11185`; M1/M2/M3 measured under `a3b748dcb5fe3429b1e155aa7572d3f9835053b71732deadbac2b42f09a791a6`; M1, M2, and M3 tables and their scientific-output hashes were not recomputed by summary-only or by later laboratory increments. source_code_content_sha256 is the src/, scripts/, and config/default.yaml tree that wrote this file.

## M4 cross-source association (rule-based)
Optional step in `tvgw.associate`. It is not used by the M1, M2, or M3 measurement paths. Command: `.venv/bin/python scripts/bench_association.py`.

| input_messages | output_messages | messages_saved | bytes_in_cbor | bytes_out_cbor | bytes_saved | merged_detections | same_sensor_pairs_within_window |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 720 | 720 | 0 | 210191 | 210191 | 0 | 0 | 850 |

The committed FIRMS Canada snapshot has one satellite id, so the cross-source rule saves no messages. Pairs inside the window that share a sensor are counted and left unmerged.

## Transport honesty
- Return-path ACK frames are transmitted on the emulated reverse channel with turnaround and loss; sender state advances only when an ACK is delivered.
- W3C EXI was not measured.
- Evidence supports at most TRL-4 for the measured laboratory behaviors.
