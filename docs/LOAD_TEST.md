# Load test specification

**Status:** Proposed · **Owner:** Lours

How the capacity of this deployment shape — La Suite Meet plus a LiveKit SFU on a single host — is measured, so that the participant cap we configure and the numbers we state are measurements rather than estimates.

Results go to [`CAPACITY.md`](CAPACITY.md). **A number that is not in that ledger may not be published anywhere**, and the ledger is the only place a cap comes from.

---

## 1. Why this exists

The stack has exactly one participant cap: `room.max_participants` in `livekit-server.yaml`, asserted by `scripts/preflight.sh config`. Meet exposes none of its own and never calls `CreateRoom`, so that server-level value binds every room. LiveKit's default is `0`, meaning unlimited. Choosing the number is therefore the whole capacity decision, and it is currently a conservative guess (see [`CAPACITY.md`](CAPACITY.md)).

Two things must be measured before it moves:

1. **The knee** — the participant count at which quality degrades on a given instance type and LiveKit version.
2. **The real per-subscriber egress in Meet's own layouts.** A browser's adaptive layer selection differs from a synthetic subscriber's, and the host's network cap is a hard ceiling that arrives before CPU on most instance types.

Everything else in this document exists to make those two numbers trustworthy.

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

Participant counts below are written for a 100-participant target shape. When the instance type under test is smaller, every count scales proportionally and the shape — the publisher-to-subscriber ratio and the layout — stays the same, so that rows in the ledger remain comparable across instance types.

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

### LT-4 — Knee

LT-1's shape at **150** participants, then at **200**. Run until a threshold in §4 is crossed or the target refuses joins.

The purpose is to find where degradation starts, not to pass. A knee that is not found because the run stopped at the target number is not a knee.

### LT-5 — UDP port range

LT-1 against a target configured with a **UDP port range** instead of the single multiplexed `udp_port`. `udp_port` and `port_range_start`/`port_range_end` are mutually exclusive, and a range widens the firewall surface, so this run exists to decide whether the change is justified by measurement rather than by upstream's general advice. Compare CPU, packet rate and loss against the LT-1 baseline on the same instance type and version.

### LT-6 — Restrictive network, TURN/TLS-only

The run that reflects venue and corporate reality, and the only one that proves the relay path.

- LT-1's synthetic load as background, **plus five real browsers** on a machine whose local firewall **drops all UDP and all TCP except 443**.
- Two sub-cases, because they fail differently:
  - **UDP/443 permitted** — the relay works over QUIC-friendly UDP.
  - **TCP/443 only, with TLS inspection** — requires a TURN listener with TLS on the media address. Without one, a participant joins the room interface and gets no media at all, which reads to them as a broken product rather than as a blocked network.
- Recorded: whether each browser establishes media, time to first frame, relay share, and the additional host CPU and egress the relayed sessions cost.

**LT-6 also supplies the real-browser corroboration required by §2.3.** No cap is published from a test suite in which LT-6 did not run and pass.

### LT-7 — Join storm

100 HTTP requests within 60 seconds against the room endpoint (`/api/v1.0/rooms/<slug>`), from **many source addresses** rather than one — a real audience arriving at a scheduled start time comes from many addresses, and testing from one address measures the rate limiter instead of the application.

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

The 50 % thresholds are deliberate: they are not the point of failure, they are the point beyond which there is no room for the thing we did not test. Everything published carries **20 % headroom below the measured knee** on top of that.

### At the knee run (LT-4)

| Signal | Threshold |
|---|---|
| Packet loss | < **2 %** |
| Subscriber disconnects | **zero** |
| Joins rejected | only at the configured cap, never through failure |

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

### Verdict rules

- **All of LT-1, LT-2, LT-6 and LT-7 pass at count *N*** → *N* is the measured maximum for that instance type and version.
- **LT-2 fails while LT-1 passes** → the instance type is not viable at *N* for meetings with screen sharing; the ledger records the lower count that passes LT-2, and that is the cap.
- **LT-4 fails** → the knee is below the next step; the cap stays at the highest fully passing count.
- **Any generator exceeded its own limits** → the run is void and does not enter the ledger.

---

## 5. What is measured on which instance type

The host's NIC cap is per instance type and is usually the binding constraint before CPU, so every row in the ledger is per instance type — a number measured on one type transfers to no other, and a number measured on bare-metal hardware transfers to no virtual instance at all.

| Instance class under test | Scenarios | Why |
|---|---|---|
| 2 vCPU / 8 GB | LT-1, LT-2, LT-6, LT-7 at a proportionally reduced count | Establishes the floor. The knee run is unnecessary: the NIC cap binds long before CPU does |
| 4 vCPU / 16 GB | LT-1, LT-2, LT-3, LT-4, LT-6, LT-7 | The mid class, and the one where screen sharing is most likely to be the deciding factor |
| 8 vCPU / 32 GB | **All seven**, at the full 100-participant shape | The reference measurement; LT-5 decides the RTC port configuration for this class |
| 16 vCPU / 64 GB | LT-1, LT-2, LT-4 at 150 and 200, LT-6 | Only the upper bound is interesting here; the lower scenarios are already answered by the smaller classes |

Every ledger row also names the **LiveKit version** and the **Meet version**, because a capacity number is a property of a version pair and not of the hardware alone. A minor upgrade to either does not invalidate a row automatically, but a row older than the currently deployed version pair is marked as such and is re-measured before it is used to raise a cap.

---

## 6. Recording results

For each run, archive: the exact command line, the raw load-tester output, the metric series for the run window, the versions of everything (Meet, LiveKit, the CLI, the instance type), the preflight verdict before and after, and the generator's own utilisation.

Then, and only then, add or update a row in [`CAPACITY.md`](CAPACITY.md):

1. One row per **instance type × LiveKit version × scenario**.
2. **Measured max participants** is the highest count at which every applicable threshold in §4 passed.
3. **Headroom** is the margin below the measured knee that the published cap keeps — 20 % unless a written reason says otherwise, and then the reason goes in the row.
4. The published cap is `measured max − headroom`, rounded down, and it is what goes into `room.max_participants` and into the `preflight.sh config` assertion. The two must agree; preflight is what proves they do.
5. A run that failed is recorded as a failed row. A ledger that only contains successes is a marketing document, not a measurement.

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
