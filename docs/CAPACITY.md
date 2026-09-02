# Capacity ledger

**Status:** Proposed · **Owner:** Lours

The measured capacity of this deployment shape, one row per instance type and version pair. Rows are produced by the runs in [`LOAD_TEST.md`](LOAD_TEST.md).

**This file is the only source of a participant number.** Nothing published anywhere — a page, a README sentence, an answer to a question — may state a capacity figure that is not a published cap in the table below. Absent a measured row, the value permitted today (§2) stands.

---

## 1. Ledger

Empty until measured. The date column is filled in when a row is produced, and stays empty for a row that has not been measured; a row without a date has not been measured and cannot be quoted.

| Instance type | LiveKit version | Meet version | Scenario | Measured max participants | Headroom | Published cap | Knee (diagnostic) | Real browsers (LT-6) | Date measured |
|---|---|---|---|---|---|---|---|---|---|
| POP2-2C-8G | | | LT-1 | | 20 % | | n/a | | |
| POP2-2C-8G | | | LT-2 | | 20 % | | n/a | | |
| POP2-4C-16G | | | LT-1 | | 20 % | | n/a | | |
| POP2-4C-16G | | | LT-2 | | 20 % | | n/a | | |
| POP2-4C-16G | | | LT-3 | — | — | diagnostic — no cap | n/a | | |
| POP2-4C-16G | | | LT-4 | — | — | diagnostic — no cap | | | |
| POP2-8C-32G | | | LT-1 | | 20 % | | n/a | | |
| POP2-8C-32G | | | LT-2 | | 20 % | | n/a | | |
| POP2-8C-32G | | | LT-3 | — | — | diagnostic — no cap | n/a | | |
| POP2-8C-32G | | | LT-4 | — | — | diagnostic — no cap | | | |
| POP2-8C-32G | | | LT-5 | — | — | diagnostic — no cap | n/a | | |
| POP2-16C-64G | | | LT-1 | | 20 % | | n/a | | |
| POP2-16C-64G | | | LT-2 | | 20 % | | n/a | | |
| POP2-16C-64G | | | LT-4 | — | — | diagnostic — no cap | | | |

**The published cap is the measured max reduced by the headroom percentage, rounded down. The measured max is the highest participant count at which a scenario passed every pass threshold that applies to it. The knee is never an input to the cap.** The pass thresholds are in [`LOAD_TEST.md`](LOAD_TEST.md) §4 and the headroom is 20 % unless a row carries a written reason for another value, stated once with its reasoning in the same section. The published cap is the value written into `room.max_participants` in `livekit-server.yaml` and asserted by `scripts/preflight.sh config`. The two must agree; preflight is what proves they do.

**Which scenarios produce a cap**: LT-1 and LT-2 only, and only on a class where LT-6 and LT-7 also passed ([`LOAD_TEST.md`](LOAD_TEST.md) §4). LT-3, LT-4 and LT-5 carry no cap: LT-3 and LT-5 have no pass threshold, and LT-4 exists to locate the knee. They inform the cap and the configuration; none of them sets one.

**Knee (diagnostic)**: filled on an LT-4 row where LT-4 ran, and `n/a` on every other row. It records the count at which degradation began, and it is a diagnostic only — a knee sitting close to that class's measured max is a reason to widen the headroom on the LT-1 and LT-2 rows, with the reason written into those rows. A class with no LT-4 row — the 2 vCPU class runs none ([`LOAD_TEST.md`](LOAD_TEST.md) §5) — still has a measured max and therefore a cap.

**Real browsers (LT-6)**: `pass` / `fail` / blank. A row whose LT-6 result is blank or `fail` **cannot become a published cap**, whatever the synthetic numbers say — the load tester publishes H.264 and VP8 while the client publishes VP9, so a synthetic-only row is an unverified row ([`LOAD_TEST.md`](LOAD_TEST.md) §2.3).

### 1.1 Failed runs

Recorded here, not discarded. A ledger that contains only successes is a marketing document.

| Instance type | LiveKit version | Scenario | Count attempted | Which threshold failed | Date measured |
|---|---|---|---|---|---|
| | | | | | |

---

## 2. The value permitted today

**30 participants per room**, on the current deployment.

That is `room.max_participants: 30` in `livekit-server.yaml`, asserted by `preflight.sh config`. It is **not a measured number**: it is a deliberately conservative placeholder chosen because LiveKit's default of `0` means unlimited, and unlimited is not a capacity decision. It sits well below what LiveKit's own published benchmark suggests a single node can carry — LiveKit documentation, [*Benchmarking*](https://docs.livekit.io/home/self-hosting/benchmark/) — and that is on purpose: those results are another operator's machine, version pair and workload, so under the publication rule above they may not be quoted here and may not raise this number. Only a run and a row can.

Until a ledger row exists for the deployed instance type and version pair:

- **30 is the number.** It is the number in the configuration, the number preflight asserts, and the only number that may be stated publicly.
- It may not be raised because a benchmark elsewhere suggests a larger one, because a call once worked with more people, or because a particular event would like it to be larger. It is raised by a run and a row, or not at all.
- Lowering it needs no measurement. A cap can always go down.

---

## 3. Per-room caps versus node-level caps

The distinction matters, because the two are often conflated and only one of them is enforceable.

### 3.1 What binds a room

`room.max_participants` is a **per-room** setting. Meet never calls `CreateRoom` — every room is auto-created when its first token holder connects — so the server-level default applies to every room on the node. The 31st participant of a room with a cap of 30 is rejected at join.

It does **not** limit the node. Ten rooms of 30 is 300 participants on one host, and nothing in this configuration prevents that.

### 3.2 What binds a node

**There is no node-level participant cap in LiveKit.** A promise of "N concurrent participants across all rooms" cannot be enforced by this configuration and must not be written into any commitment.

What actually binds a node, in the order the ceiling is usually reached:

| Ceiling | Mechanism | Enforced by |
|---|---|---|
| **Host bandwidth** | The instance type's published NIC cap. Physical, unconfigurable | the platform |
| **Bytes per second** | LiveKit's `limit.bytes_per_sec` | configuration, if set |
| **Track count** | LiveKit's `limit.num_tracks` | configuration, if set |
| **CPU** | Packet forwarding work, which scales with subscriptions rather than with participants | nothing; it degrades rather than rejecting |

The `limit:` block is therefore the closest thing to a node-level cap that exists, and it rejects or throttles rather than counting participants. Its values belong in the ledger too, once measured, because a limit set below the measured knee — the diagnostic recorded in §1, not a cap input — is what turns a saturation event into a rejection instead of a degradation for everybody.

### 3.3 The consequence for capacity claims

A capacity claim has to name what it is about:

- **"Up to N participants in a meeting"** — supportable from a published cap in §1, per instance type and version pair.
- **"N participants across the whole host"** — not enforceable, not measured by these scenarios, and not to be claimed.
- **Concurrent meetings** — a separate measurement that these scenarios do not make. LT-1 to LT-7 all run a single room; a multi-room measurement is a future addition to the specification and, until it exists, no statement about concurrent meetings is supportable.

### 3.4 Sizing assumptions

Turning a headcount into a peak concurrent load takes an assumption — what share of the people counted are in a meeting at the same moment. That is an assumption and not a measurement, and **this repository carries none.** Nothing here converts a headcount into concurrency, and nothing here may be read as implying a conversion: the ledger measures one room on one instance type and version pair, and §3.3 has already said which claims that supports.

The peak-concurrency assumption used when sizing a deployment lives in the private deployment sizing specification, with its band and its reasoning. Its figures are not reproduced here, and they cannot be inferred from a published cap. If such an assumption is ever carried in this repository, it is written as an assumption, with its band and its reasoning, and never as a ledger row or a measured number.

---

## 4. When a row expires

A row is a property of a version pair, not of the hardware.

- A row whose LiveKit or Meet version is **older than what is deployed** is marked stale and may not be used to raise a cap. It may continue to support the cap already published, since the risk of an unchanged number is bounded.
- A change to the codec configuration — enabling AV1, or moving off VP9 — **invalidates every synthetic row** for that configuration. The load tester cannot publish AV1 at all, so those rows are re-measured, never extrapolated.
- A change to the RTC port configuration (single multiplexed UDP port versus a port range) makes a row apply only to the configuration it was measured under. LT-5 exists to quantify that difference.
- A change of instance type is a new row. Nothing transfers between types, and nothing measured on bare-metal hardware transfers to a virtual instance.

---

## Changelog

| Rev | Change |
|---|---|
| 1 | Initial ledger: empty table skeleton keyed on instance type, version pair and scenario, with headroom and real-browser corroboration columns; the currently permitted value recorded as an unmeasured conservative placeholder; per-room versus node-level cap explanation and the claims each one supports; row expiry rules. |
| 2 | Cap rule restated in the same words as the load-test specification: measured max less headroom, with the knee excluded from it. Ledger given a diagnostic knee column and its LT-3, LT-4 and LT-5 rows marked as carrying no cap, so the columns match the rule. Benchmark comparison behind the permitted value cited by name and source. Sizing assumptions recorded as absent from this repository, with a pointer to where a peak-concurrency assumption lives instead. |
