# Shared SRAM read-ahead prototype

This is a standalone experiment, not an integrated or selected SoC candidate.
It does not modify the official fabric or provide any accelerator bypass.

One clock and synchronous active-low reset govern the ICB and SRAM interfaces.
The RAM is synchronous, single-ported, 131072 by 32 bits with four byte enables.
The RAM output may become unknown after a write. The controller must preserve
needed prefetched data before that edge. Reset changes protocol/cache state,
never SRAM contents.

Commands address aligned words in A0000000..A007FFFF. Other addresses return an
error without RAM access. Writes commit on the command-acceptance edge. Writes,
read hits and invalid reads can respond on that same edge; if the response is
not ready, the command still accepts and a held response preserves its data and
error until consumed. Read misses issue one synchronous RAM read and return its
data in the next cycle. No second command accepts while a response is pending.

An accepted read hit or a consumed read-miss response may issue a speculative
read of the next word. Prefetch must not cross the 512 KiB boundary. A registered
data entry and one tagged current macro-Q entry are retained. Writes invalidate
an alias; unrelated writes preserve registered data even if the macro poisons Q.
The speculation adds RAM read activity that must later be included in power.

`cache_clear` suppresses new command acceptance and all RAM operations for that
edge, invalidates both entries, and revokes any old miss's refill eligibility.
It does not discard or alter an already accepted response. Before a new cold
task, integration must assert it and drain the previous task. No integrated
candidate may rely only on this standalone test's global reset to satisfy the
contest cold-task rule.

Required evidence: independent accepted-command FIFO and expected memory;
random and sustained response stalls; every byte mask; invalid and unaligned
addresses; write-Q poisoning; alias/unrelated writes coincident with available
prefetch; clear during a pending response; reset without clearing memory;
sequential read initiation interval and actual extra RAM reads. Functional
tests do not establish official macro timing, bus-level throughput or PPA.
