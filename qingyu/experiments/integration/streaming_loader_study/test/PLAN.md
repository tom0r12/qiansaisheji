# Conditional loader test implementation plan

This fixture models an explicit platform producer on the existing CPU-side
port of the frozen NP2, OUTSTANDING4, ONE_PER_PORT01 merger. Engine DMA is port1.
The unchanged official memory fabric and opt33 shared wrapper follow it. There
is no CPU in this conditional fixture and no official-loader claim. Source
packet words exist only in the producer reference array; shared memory begins
with poison and receives every source word through real bus writes.

The test owns independent acceptance/response FIFOs for both sources and the
merged/fabric/shared path. Only successful originating producer ACKs advance
the aligned contiguous committed prefix. A failed prefix stays stopped while
held requests and accepted responses drain. The engine cannot accept any read
descriptor or issue any architectural read beyond the prefix. Raw blocked
descriptor payload must remain stable until acceptance or explicit abort.

Each layer runs streaming current/next task and serial current/next task. No
global reset separates ordinary task epochs. Streaming START occurs after202
successful source ACKs; serial START waits for all input ACKs. Every run checks
all6385 output words, unused poison, unchanged produced source values, full
shared guard memory, exact2I+O+1 transactions, cache/core cold initialization,
and final originating magic ACK. Report first source offer/accept/ACK windows
separately, plus engine START and producer completion windows.

First-layer directed cases add:

- Delayed originating ACK at201/202-word and X/W descriptor boundaries.
- Source pause after the last X command, allowing a future-word poison
  prefetch before its real source write; subsequent engine data must be correct.
- Random producer gaps and independent response stalls with held payload checks.
- Producer failure before START and after START while a descriptor waits.
- Fault pulse coincident with START, plus idle fault without START producing no done.
- Producer failure while an output offer is held, followed by full joint drain.
- Coordinated hard reset with both domains active, then cold reload/restart.

The original candidate/core/codec/transport/fabric files remain unchanged.
Tests first use sample009,000,202 and all12 layers for each frozen prefetch8
and task9 core, using bounded codecs. Failed runs and initial-source hashes
are retained; no physical area, timing or energy is inferred from these tests.
