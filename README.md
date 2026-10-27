# tvgw — Edge-AI-to-C2 RF Message Gateway (targets TRL-4 evidence; laboratory prototype)

[![CI](https://github.com/applycoding/tvgw-edge-c2-prototype/actions/workflows/ci.yml/badge.svg)](https://github.com/applycoding/tvgw-edge-c2-prototype/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/applycoding/tvgw-edge-c2-prototype)](https://github.com/applycoding/tvgw-edge-c2-prototype/blob/main/LICENSE)

Public repository: [github.com/applycoding/tvgw-edge-c2-prototype](https://github.com/applycoding/tvgw-edge-c2-prototype)

**What this is:** A Python prototype that ingests openly licensed public edge detections (HIT-UAV thermal annotations under **CC BY 4.0**, and a NASA FIRMS fire hotspot snapshot), maps them to NIEM 6.0 `mo:Observation` XML plus alternate wire profiles, and benchmarks delivery over a **simulated** half-duplex narrowband link (`linkemu.py`).

**What was measured:** Empirical tables and plots are in [`results/SUMMARY.md`](results/SUMMARY.md) and CSV/PNG artifacts under `results/`, produced by `make bench` / `make all` on the committed code.

<!-- NOT-CLAIMED:BEGIN -->
## What Is Not Claimed (Scope & Limitations)

1. No USMTF / MIL-STD-6040 / NATO APP-11 / ADatP-3 conformance.
2. No NATO NCDF (ADatP-5653) alignment or certification.
3. No on-air tactical waveform interoperability (Link 16, STANAG 4539/5066, etc.).
4. No hardware RF or kernel `netem` testing — pure in-process discrete-event emulation.
5. No ITU-R F.1487 ionospheric calibration.
6. HIT-UAV is used under **CC BY 4.0** (GitHub); GPS for HIT-UAV is **synthetic** and tagged `[SYNTH-GPS]` in NIEM XML names.
7. Payload size comparisons vs JPEG are **task-specific information selection**, not image compression.
8. No novel CV models or operational GUI.
9. **Evidence relevant to TRL 4 only** — not TRL 5+ and not certified.
10. No learned detection model. Cross-source association is a deterministic distance, time, class, and sensor rule. It does not score whether a detection was correct.
11. French operator strings are an unreviewed machine-assisted draft and need qualified human review before any use. This is not a fully bilingual interface.
12. No Prometheus server, live Splunk deployment, or other monitoring product has been run against the laboratory `/metrics` text or the Splunk-HEC-shaped file.
<!-- NOT-CLAIMED:END -->

## Validation layers

1. **NIEM 6.0 XSD** (`mo.xsd` + `niem-core.xsd`) via offline `lxml` resolver — note an empty `<mo:Observation/>` is XSD-valid because child elements are optional.
2. **TVGW application profile** — enforces non-empty name, lat/lon, UTC timestamp, NCName id, sibling uniqueness, and rejects `xsi:nil` on required fields.

## Data sources & licences

| Source | Use | Licence / notice |
|---|---|---|
| OASIS NIEMOpen 6.0 | XSD validation | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — see `NOTICE.md` |
| HIT-UAV | Annotation replay | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (GitHub); see `NOTICE.md` |
| NASA FIRMS Canada 24h CSV | Fire hotspots snapshot in `data/sample/` | NASA open data policy |
| This repository | Code | Apache-2.0 (`LICENSE`) |

Pinned SHA-256 checksums are listed in `data/README.md`. Downloads use commit-pinned HIT-UAV URLs and fail on mismatch (`scripts/download_datasets.py`, `scripts/download_niem.py`).

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e .
make download-data          # NIEM + HIT-UAV + builds held-out corpus locally
make test                   # pytest (includes CI determinism on decompressed M3 CSV)
make ci                     # reduced sweep → results/ci/ (GitHub Actions uses this)
make all                    # long local run: full M3 + plots + audit
.venv/bin/python scripts/bench_association.py
```

**CI vs full sweep:** `make ci` runs a **reduced** grid (`config/default.yaml` → `sweep.ci`) and writes to `results/ci/`. It is **not** equivalent to the full `make all` grid committed as `results/m3_delivery_sweep.csv.gz` plus `results/m3_delivery_cells.csv` (regenerate per-seed rows with `make bench`). The association table is separate: `.venv/bin/python scripts/bench_association.py` writes `results/m4_association.csv` and `results/m4_association.json`.

## Operator text (`--lang en` and `--lang fr`)

`tvgw validate`, `tvgw replay`, and `tvgw metrics serve` take `--lang`. English keeps the historical slash-report tokens (`MSGID`, `DTG`, `ENDAT`, and the others in `src/tvgw/messages.py`). French renders a second set of tokens and the CLI help and validation messages from the same catalog. The French strings are an unreviewed machine-assisted draft and need qualified human review before any use. Domain, service, and priority values stay as stored codes.

## Laboratory metrics

`tvgw metrics serve` runs one simulated scenario, then serves Prometheus text exposition on `/metrics` from a stdlib HTTP server (default bind `127.0.0.1`). The series are queue depth, delivery latency by priority, ARQ retries, failures, TVGW profile validation rejects, and link state (`down`, `idle`, or `busy`). `results/metrics.prom` and `results/splunk_hec_events.jsonl` are still the benchmark file exports. No external collector is part of this repository.

## Cross-source association

`associate_for_transmission` can merge detections from different `source_sensor` values before a caller transmits them, inside `association.max_distance_m` and `association.max_time_s` (`config/default.yaml`). The same object class is required unless `allow_cross_class` is true. The kept record is the highest-confidence contributor (ties: smallest `detection_id`), plus `contributing_source_ids`. The M3 grid does not call this step. On the committed FIRMS Canada snapshot every row is satellite `N20`, so the benchmark saves no messages; same-sensor pairs inside the window are counted and left unmerged.

## Simulated link model (M3)

- **Simulated link only** — Gilbert–Elliot frame impairment and outages in `linkemu.py`; not calibrated to any radio.
- **Half-duplex:** gateway dispatch starts a new message only when the emulated medium is idle; priority reorders the bounded gateway queue (`max_queue_messages`), not an unbounded air backlog.
- **ARQ:** per-message fragment bursts, **18-byte bitmap ACK** on the return path (airtime + turnaround + same loss model), RTO backoff from `config/default.yaml` (`rto_margin_s`, `rto_cap_s`, `receiver_ack_gap_factor`).
- **W3C EXI:** not measured (`EXI not measured` in SUMMARY).
- **NIEM XML** carries fewer fields than JSON/CBOR/text; M2 comparisons are not like-for-like across encodings.

## Architecture (short)

`Detection` → codecs (`encode.py`) → priority queue → wire fragments → `linkemu` + ACK/retry → metrics/plots.

See `docs/INTERFACES.md` and `docs/ADDING_A_PROFILE.md`.
