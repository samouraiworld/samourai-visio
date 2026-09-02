# Load test specification

**Status:** Proposed · **Owner:** Lours

How the capacity of this deployment shape — La Suite Meet plus a LiveKit SFU on a single host — is measured, so that the participant cap we configure and the numbers we state are measurements rather than estimates.

Results go to [`CAPACITY.md`](CAPACITY.md). **A number that is not in that ledger may not be published anywhere**, and the ledger is the only place a cap comes from.

---

## 1. Why this exists

The stack has exactly one participant cap: `room.max_participants` in `livekit-server.yaml`, asserted by `scripts/preflight.sh config`. Meet exposes none of its own and never calls `CreateRoom`, so that server-level value binds every room. LiveKit's default is `0`, meaning unlimited. Choosing the number is therefore the whole capacity decision, and it is currently a conservative guess (see [`CAPACITY.md`](CAPACITY.md)).

Two things must be measured before it moves:

1. **The measured max** — the highest participant count that passes every threshold in §4 on a given instance type and LiveKit version. The published cap is derived from it and from nothing else.
2. **The real per-subscriber egress in Meet's own layouts.** A browser's adaptive layer selection differs from a synthetic subscriber's, and the host's network cap is a hard ceiling that arrives before CPU on most instance types.

Everything else in this document exists to make those two numbers trustworthy. The **knee** — the count at which quality actually degrades — is a third number, measured only where LT-4 runs, and it is a diagnostic: it says how much room sits above the measured max, and it never enters the cap (§6).

---

## 2. Rig

### 2.1 Target

A throwaway deployment of **this repository's configuration**, byte-identical to the reference deploy, on the instance type under test. Never the live public instance: a load test on a running service is an outage with extra steps.

The target must be freshly deployed and green on `scripts/preflight.sh all` before the first run, and green again after the last — a run that leaves the target broken invalidates the numbers it produced.

Recorded for every run, on the target:

| Signal | Source |
|---|---|
| Host NIC egress and ingress | host metrics (`node_exporter`) |
| `livekit` container CPU and memory | container metrics |
| LiveKit internals: participants, tracks, published/subscribed bitrate, packet loss, ICE candidate types | the LiveKit Prometheus endpoint (`prometheus.port` in `livekit-server.yaml`) |
| Backend request latency (p95) | reverse-proxy access logs |
| Relay share | proportion of connections whose selected ICE candidate is `relay` |
| Errors | container logs for `livekit` and the Meet backend |

### 2.2 Generators

**Two generator VMs**, each of a class whose published bandwidth is at least that of the target (a 4 vCPU / 16 GB class at 800 Mbps is the working baseline). Two, not one, for three reasons: a single generator saturates its own NIC before the target's, one generator process cannot both publish and subscribe convincingly at scale, and a source spread across two addresses is closer to reality than a single address.

On each generator:

- `ulimit -n 65535` before starting anything. The default file-descriptor limit is the most common cause of a "the server fell over" result that was in fact the generator falling over.
- The generator's own CPU and NIC are recorded alongside the target's. **A run in which a generator exceeded 70 % CPU or 70 % of its NIC cap is void** and is repeated on more generators. This check is not optional: it is the difference between measuring the target and measuring the test rig.

### 2.3 Tool

The LiveKit CLI load tester (`lk perf load-test`; the sub-command was previously `lk load-test`, and older documentation still uses the old form).

**The codec caveat, which changes how every synthetic number must be read.** The load tester publishes **H.264 and VP8 only**. Meet's client publishes **VP9** with simulcast and dynacast enabled. VP9 at equal perceived quality uses materially less bitrate than VP8 and costs the SFU slightly more in packet handling; an SFU forwards rather than transcodes, so the difference lands in bytes and packet counts, not in encode cost. Therefore:

- Synthetic **egress** figures are an upper bound for the same visual quality, not a like-for-like measurement.
- Synthetic **CPU** figures are a reasonable proxy, since forwarding work scales with packets and subscriptions rather than with codec.
- **Layer selection is the part that does not transfer at all.** Real browsers drop and raise simulcast layers according to their own bandwidth estimation; synthetic subscribers do not behave the same way, and adaptive stream plus dynacast is precisely what makes real gallery layouts cheaper than they look on paper.

The consequence is a rule, not a footnote: **every capacity figure entering the ledger must be corroborated by at least one run containing real browsers** (LT-6 carries them). A synthetic-only figure is recorded as synthetic and is not eligible to become a published cap.

The same caveat applies with more force to **AV1**: the load tester cannot publish it at all, so if AV1 is ever enabled in the client, every synthetic number in the ledger is invalidated for that configuration and the ledger row must be re-measured, not extrapolated.

### 2.4 Network conditions

The default rig is generators and target in the same region: sub-millisecond latency and effectively no loss. That is the best case and it is not what participants experience.

- **LT-1 to LT-5 and LT-7** run on the clean path. They measure the host's ceiling, which is what the cap is derived from.
- **One variant of LT-1** is repeated with impairment applied on the generators (`tc netem`: 40 ms of latency, 10 ms of jitter, 0.5 % loss) to observe how retransmission and layer adaptation change host CPU and egress. It is a sanity check on the headroom margin, not a source of a cap.
- **LT-6** is the restrictive-network run and is described below; it is the only run that exercises the relay path, and it is mandatory before any cap is published.

---

## 3. Scenarios

Seven runs. LT-1 and LT-2 are the ones a cap comes from; the rest exist to make the cap safe.

Participant counts below are written for a **100-participant target shape**, which is the reference shape and is what the 8 vCPU class runs (§5). Every other class runs at its own **target count**: the reference shape scaled to that class, with the publisher-to-subscriber ratio and the layout unchanged, so that rows in the ledger remain comparable across instance types. A class's target count is fixed before its first run on that class and is recorded with every row it produces.

Two counts written below as absolute numbers scale with it by a stated factor, on every class, rather than staying fixed:

- **LT-4's knee steps are 1.5× and 2× the class's target count** — 150 and 200 on the reference shape.
- **LT-7's storm is one request per participant of the class's target count, within 60 seconds** — 100 requests on the reference shape.

A count that stayed fixed while the others scaled would measure a different thing on each class, which is the one thing the ledger cannot absorb.

### LT-1 — Baseline

The shape of a large community call: a handful of cameras, everyone else listening.

| Parameter | Value |
|---|---|
| Participants | 100 total |
| Video publishers | 8 |
| Audio publishers | 8 |
| Subscribers | 92 |
| Video resolution | high |
| Layout | speaker |
| Speaker simulation | on |
| Ramp | 5 participants per second |
| Duration | 10 min sustained |

Sketch: `lk perf load-test --url wss://<media-host> --api-key meet --api-secret <secret> --room lt1 --video-publishers 8 --audio-publishers 8 --subscribers 92 --video-resolution high --layout speaker --simulate-speakers --num-per-second 5 --duration 10m`

The ramp rate matters: joining 100 participants instantly is a different test (that is LT-7's job) and produces a connection-storm artefact that has nothing to do with steady-state capacity.

### LT-2 — Screen share

LT-1 plus a second process in the same room publishing **one 1080p non-simulcast video track and subscribing to nothing**. Every participant then subscribes to a full-resolution stream with no lower layer to fall back to, which is the single most expensive thing a real meeting does.

Sketch: LT-1, plus `--video-publishers 1 --video-resolution high --no-simulcast --subscribers 0` in the same room.

**LT-2 is the binding run for egress.** A cap derived from LT-1 alone is a cap that fails the first time somebody shares a slide deck.

### LT-3 — Camera-heavy gallery

| Parameter | Value |
|---|---|
| Video publishers | 25 |
| Subscribers | 75 |
| Layout | 5×5 gallery |

Many-to-many subscription, which is where subscription count — not participant count — becomes the cost driver. Establishes whether the cap should be expressed differently for camera-heavy usage.

**LT-3 is diagnostic.** It changes the shape the cap is defined on rather than the count, so it carries no pass threshold and produces no measured max and no cap (§4). Its finding can change how a later LT-1 or LT-2 run is shaped, and the cap then comes from that run.

### LT-4 — Knee

LT-1's shape at **1.5× the class's target count**, then at **2×** — 150 then 200 on the reference shape (§3). Run until a threshold in §4 is crossed or the target refuses joins.

The purpose is to find where degradation starts, not to pass. A knee that is not found because the run stopped at the target number is not a knee.

**LT-4 is diagnostic.** The knee it finds is recorded in the ledger as a diagnostic and is never an input to a cap; the cap comes from LT-1 and LT-2 (§6). What the knee buys is judgement: a knee sitting close to the measured max is a reason to widen that row's headroom, and a class with no knee run still has a measured max and therefore a cap.

### LT-5 — UDP port range

LT-1 against a target configured with a **UDP port range** instead of the single multiplexed `udp_port`. `udp_port` and `port_range_start`/`port_range_end` are mutually exclusive, and a range widens the firewall surface, so this run exists to decide whether the change is justified by measurement rather than by upstream's general advice. Compare CPU, packet rate and loss against the LT-1 baseline on the same instance type and version.

**LT-5 is diagnostic.** It compares two configurations against each other, so it carries no pass threshold of its own and produces no measured max and no cap (§4); what it produces is a decision about the RTC port configuration a later run measures under.

### LT-6 — Restrictive network, TURN/TLS-only

The run that reflects venue and corporate reality, and the only one that proves the relay path.

- LT-1's synthetic load as background, **plus five real browsers** on a machine whose local firewall **drops all UDP and all TCP except 443**.
- Two sub-cases, because they fail differently:
  - **UDP/443 permitted** — the relay works over QUIC-friendly UDP.
  - **TCP/443 only, with TLS inspection** — requires a TURN listener with TLS on the media address. Without one, a participant joins the room interface and gets no media at all, which reads to them as a broken product rather than as a blocked network.
- Recorded: whether each browser establishes media, time to first frame, relay share, and the additional host CPU and egress the relayed sessions cost.

**LT-6 also supplies the real-browser corroboration required by §2.3.** No cap is published from a test suite in which LT-6 did not run and pass.

### LT-7 — Join storm

**One HTTP request per participant of the class's target count, within 60 seconds** — 100 requests on the reference shape (§3) — against the room endpoint (`/api/v1.0/rooms/<slug>`), from **many source addresses** rather than one — a real audience arriving at a scheduled start time comes from many addresses, and testing from one address measures the rate limiter instead of the application.

Two things are being checked at once: backend and application-server headroom under a join storm, and that the edge's flood brake does **not** throttle a legitimate burst. Authenticated sessions are exempt from the brake; the anonymous path is the one to watch. A run that trips the brake for legitimate traffic is a failure of the edge configuration, recorded as such, and it blocks the cap just as a media failure would.

---

## 4. Pass thresholds

Evaluated over the sustained portion of a run, ignoring ramp-up and ramp-down.

### At the target count (LT-1 and LT-2, 10 min sustained)

| Signal | Threshold |
|---|---|
| `livekit` container CPU | ≤ **50 %** of the host's vCPU total |
| Host egress | ≤ **50 %** of the instance type's published bandwidth cap |
| Packet loss reported by the load tester | < **0.5 %** |
| p95 end-to-end latency reported by the load tester | < **200 ms** |
| Subscriber disconnects | **zero** |
| Backend p95 request latency | < **500 ms** |
| Errors in `livekit` or backend logs | none attributable to load |

The 50 % thresholds are deliberate: they are not the point of failure, they are the point beyond which there is no room for the thing we did not test.

**Headroom, stated once.** On top of those thresholds, every published cap keeps **20 % headroom below the measured max**, unless the row carries a written reason for another value. The margin exists for what the rig cannot reproduce: real browsers' layer selection against synthetic subscribers, relayed sessions, impaired paths, and the drift between the version pair a row was measured on and the pair running on the day the cap is relied on. It is a margin below the measured max, never below the knee — §6 is the only place the cap is computed.

### At the knee run (LT-4, diagnostic)

| Signal | Threshold |
|---|---|
| Packet loss | < **2 %** |
| Subscriber disconnects | **zero** |
| Joins rejected | only at the configured cap, never through failure |

Crossing one of these locates the knee. It neither lowers nor raises a cap: the knee is recorded as a diagnostic (§6).

### LT-6

| Signal | Threshold |
|---|---|
| Real browsers establishing media in the UDP/443 sub-case | **5 of 5** |
| Real browsers establishing media in the TCP/443-only sub-case | **5 of 5**, or the run is recorded as a documented limitation of the tested configuration |
| Time to first frame over the relay | < **10 s** |
| Additional host CPU from the relayed sessions | recorded; no threshold, this is a cost input |

### LT-7

| Signal | Threshold |
|---|---|
| Backend p95 | < **500 ms** |
| HTTP 5xx | **zero** |
| Legitimate requests rejected by the flood brake | **zero** |

### Scenarios with no pass threshold

**LT-3 and LT-5 have none, deliberately, and neither produces a cap.** LT-3 changes the shape the cap is defined on — a 25-publisher gallery is a different subscription profile, not a larger count of the LT-1 shape — so what it produces is a finding about how the cap should be expressed, not a pass. LT-5 compares two RTC port configurations against each other, and a comparison has no bar of its own. Both are recorded in the ledger as diagnostic rows, with no measured max and no published cap.

### Verdict rules

- **All of LT-1, LT-2, LT-6 and LT-7 pass at count *N*** → *N* is the measured maximum for that instance type and version, and the cap is derived from it by §6.
- **LT-2 fails while LT-1 passes** → the instance type is not viable at *N* for meetings with screen sharing; the measured maximum is the lower count that passes LT-2, and the cap is derived from that.
- **LT-4 crosses a threshold at a step** → the knee is at or below that step. It is recorded as a diagnostic and changes no cap: the cap stays what §6 derives from the measured max. A knee close to the measured max is a reason to widen that row's headroom, and the reason is written into the row.
- **LT-3 or LT-5** → diagnostic. Neither produces a measured maximum and neither produces a cap; a finding from either changes how a later run is shaped or configured, and the cap comes from that run.
- **Any generator exceeded its own limits** → the run is void and does not enter the ledger.

---

## 5. What is measured on which instance type

The host's NIC cap is per instance type and is usually the binding constraint before CPU, so every row in the ledger is per instance type — a number measured on one type transfers to no other, and a number measured on bare-metal hardware transfers to no virtual instance at all.

| Instance class under test | Scenarios | Why |
|---|---|---|
| 2 vCPU / 8 GB | LT-1, LT-2, LT-6, LT-7 at this class's target count | Establishes the floor. No knee run: the NIC cap binds long before CPU does, and since the knee is a diagnostic its absence costs this class nothing — the class still has a measured max and therefore a cap (§6) |
| 4 vCPU / 16 GB | LT-1, LT-2, LT-3, LT-4, LT-6, LT-7 at this class's target count | The mid class, and the one where screen sharing is most likely to be the deciding factor |
| 8 vCPU / 32 GB | **All seven**, at the full 100-participant reference shape | The reference measurement; LT-5 decides the RTC port configuration for this class |
| 16 vCPU / 64 GB | LT-1, LT-2, LT-4, LT-6 at this class's target count | Only the upper bound is interesting here; the lower scenarios are already answered by the smaller classes |

Every class runs at its own target count, and the two counts written as absolute numbers in §3 scale with it: LT-4's steps at 1.5× and 2× that count, LT-7's storm at one request per participant of it. On the 8 vCPU class the target count is the 100-participant reference shape, which is where the absolute numbers in §3 come from.

Every ledger row also names the **LiveKit version** and the **Meet version**, because a capacity number is a property of a version pair and not of the hardware alone. A minor upgrade to either does not invalidate a row automatically, but a row older than the currently deployed version pair is marked as such and is re-measured before it is used to raise a cap.

---

## 6. Recording results

For each run, archive: the exact command line, the raw load-tester output, the metric series for the run window, the versions of everything (Meet, LiveKit, the CLI, the instance type), the preflight verdict before and after, and the generator's own utilisation.

Then, and only then, add or update a row in [`CAPACITY.md`](CAPACITY.md):

1. One row per **instance type × LiveKit version × scenario**.
2. **Measured max participants** is defined by the rule in item 4. A scenario that carries no pass threshold in §4 — LT-3 and LT-5 — has no measured max at all, and its row is recorded as diagnostic.
3. **Headroom** is the margin below the measured max that the published cap keeps: 20 % unless the row carries a written reason for another value, and then the reason goes in the row. §4 states once why the margin exists.
4. **The published cap is the measured max reduced by the headroom percentage, rounded down. The measured max is the highest participant count at which a scenario passed every pass threshold that applies to it. The knee is never an input to the cap.** The result is what goes into `room.max_participants` and into the `preflight.sh config` assertion. The two must agree; preflight is what proves they do.
5. **The knee** is recorded, where LT-4 ran, in the ledger's diagnostic column. It says how much room sits above the measured max, and it can widen a row's headroom — written as the reason on that row. It never appears in the arithmetic of item 4. A class with no knee run, such as the 2 vCPU class (§5), still has a measured max and therefore a cap.
6. Only LT-1 and LT-2 produce a cap, and only when LT-6 and LT-7 passed on the same class (§4). LT-3, LT-4 and LT-5 inform the cap; none of them sets one.
7. A run that failed is recorded as a failed row. A ledger that only contains successes is a marketing document, not a measurement.

### The publication rule

**Only measured numbers may be published.** No page, no answer to a question, no README sentence may state a participant number that is not a published cap in the ledger. An estimate is written as an estimate, or it is not written. When a version pair changes and the row has not been re-measured, the old, lower number stands until the new one is measured — capacity claims only move upward on evidence.

---

## 7. Before the first run

- [ ] Target deployed from this repository's configuration on the instance type under test, `preflight.sh all` green.
- [ ] Two generators provisioned, `ulimit -n 65535` set, load tester installed and version recorded.
- [ ] Metrics collection confirmed on both the target and the generators — a run without generator metrics is unverifiable.
- [ ] The media API secret in `livekit-server.yaml` asserted to match the backend's, or every token fails signature validation and the entire test measures nothing at all.
- [ ] Firewall on the target permits exactly the ports the configuration publishes, including the relay allocation range; an unpublished range makes the relay path silently unreachable under Docker bridge networking.
- [ ] The restricted-network machine for LT-6 prepared with its firewall policy verified **before** the run, by confirming that a normal join fails from it.
- [ ] Someone is watching the target's metrics live. An unattended load test that damages the host teaches nothing.

---

## Changelog

| Rev | Change |
|---|---|
| 1 | Initial specification: rig and generator rules, load-tester codec caveat and the real-browser corroboration rule it forces, seven scenarios LT-1 to LT-7 including the TURN/TLS-only run, pass thresholds and verdict rules, per-instance-type test matrix, result recording into the capacity ledger, and the rule that only measured numbers may be published. |
