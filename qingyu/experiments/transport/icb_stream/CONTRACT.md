# Experimental ordered ICB stream engine

This standalone transport experiment has no SoC integration or PPA claim. It
uses one unchanged 32-bit official E203 memory-fabric master and the frozen
opt33 shared-SRAM slave in its integration test. It adds no shared-memory bypass.

## Descriptors and streams

- One read and one write descriptor can run concurrently. Each descriptor is
  accepted by its own valid/ready handshake. Base is a byte address; count is
  the number of 32-bit words. Only aligned, nonempty ranges wholly inside
  `[0xa0000000, 0xa0080000)` are accepted as valid work. Invalid descriptors
  generate a held error completion without any corresponding bus transaction.
- Each direction remains unavailable until its completion valid/ready
  handshake. Read completion follows consumption of its last returned word;
  write completion follows the real ACK for every accepted write. Completion
  valid/error remains stable under backpressure.
- Read word valid/data/last remains stable while not ready. Successful read
  responses are delivered in descriptor order, exactly once. Error responses
  never become output words. `last` identifies the descriptor's final word.
- Write word valid/ready is distinct from bus command acceptance and response
  retirement. Data uses all four byte lanes. Input `last` must equal the final
  descriptor-word position. An early or missing `last` fails both active
  directions and initiates drain; the malformed word is not queued.
- Read/write address overlap is legal but only the actual ordered bus command
  sequence determines memory values. There is no snapshot or overlap-copy
  guarantee. Software must arrange disjoint buffers when it needs that behavior.

## Credits, ordering and fairness

The engine has parameterized 4 or 8 accepted outstanding transactions, an
ordered owner FIFO, a read-data FIFO and a write-data FIFO. The tested official
fabric returns responses in order with at least one cycle of master latency.
The engine never depends on a shared-slave zero-ACK appearing at its own
master in the same cycle. Unexpected unsolicited responses are a protocol
violation, checked by the independent testbench.

Read FIFO capacity is reserved for every accepted read and any offered but
blocked read, in addition to already returned words. Therefore all accepted
responses can be drained without overflowing the read FIFO even if the
consumer stalls. Arbitration alternates eligible directions after each real
accepted command. If only one direction is eligible it uses the available
bandwidth. A blocked offered command retains its full identity until accepted.

## Abort, errors and reset

Soft abort and any bus response error stop fresh offers in both directions.
An already offered command stays valid with unchanged payload and may still
commit. All accepted responses are drained and their ownership is retained.
Accepted writes cannot be rolled back, including a write whose later response
reports an error. No synthetic ACK or uncommitted success is generated.

Read words that were successfully buffered before the failure remain stable
and must be consumed; later responses during drain are discarded, including
the error response itself. Write words queued but not already offered are
discarded. Each active direction receives an error completion after all bus
work and retained read words drain. A consumer that permanently refuses ready
can therefore delay completion; the engine does not violate valid stability
to manufacture a bounded completion. New work is accepted after all error
completions are acknowledged. Descriptor errors alone do not abort the other
valid direction.

Hard reset is active-low synchronous and must also reset the connected fabric
and slave protocol state. It cancels descriptors, offered commands, credits,
FIFO contents and completions; already committed SRAM writes are preserved.
No assumptions are made about memory output retention during writes.

## Planned files and verification

- `qingyu_icb_stream.sv`: synthesizable stream engine.
- `tb_icb_stream.sv`: independent descriptor/command/response/data scoreboard,
  connected to the literal official fabric and opt33 shared wrapper.
- `run_checks.py`: pinned-vendor and frozen-slave hash checks, unique run
  directory, 4/8-credit matrices, immutable evidence and source-change guard.
- `README.md` and `SOURCE_SHA256.json`: measured results, reproduction and limits.

Directed checks cover read/write/mixed streams, FIFO saturation, held commands,
held output/completions, last and address errors, response errors at first/
middle/final positions, abort with in-flight and blocked offers, hard reset,
and clean restart. Random seeds vary source/consumer stalls and response
backpressure. Bandwidth results distinguish warm sequential reads, cold
misses, writes and mixed traffic; none is full-task throughput or PPA.

The native-return integration test leaves the fabric and its buffers unchanged.
An additional verification-only mode queues responses *after* that fabric so
the engine's 8-credit full and simultaneous replacement cases can be reached.
It still compares every command and SRAM response, but that artificial return
delay is excluded from all bandwidth claims and is never part of the RTL.
