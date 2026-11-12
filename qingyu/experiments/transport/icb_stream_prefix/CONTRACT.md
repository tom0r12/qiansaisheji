# Bounded-prefix ICB stream revision

This independent revision preserves the frozen fixed-count transport contract
in `../icb_stream/CONTRACT.md`. The fixed sources and their evidence are unchanged.
The additional input `wr_desc_prefix` is sampled with the write descriptor.

- `wr_desc_prefix=0`: exact-count behavior is unchanged. Early `last` and a
  missing final `last` are errors.
- `wr_desc_prefix=1`: `wr_desc_count` is a strict maximum allocation of 1..398
  32-bit words. The entire maximum extent must be aligned and within shared
  SRAM. There is no zero-word stream. An invalid maximum generates an error
  completion and no bus command; it does not abort the other valid direction.
- Each accepted word may terminate the prefix with `wr_word_last=1`, including
  the first word. That handshake records the actual length, permanently stops
  further word acceptance for this descriptor and leaves unused slot words
  untouched. No fabricated padding or guessed compressed length is written.
- Without `last`, reaching the maximum is an error. The malformed final word
  is accepted for error detection but is not queued for memory. Earlier offered
  or accepted commands retain their identities and drain normally.
- Successful completion occurs only after every word of the actual prefix
  has received its real bus response. Encoder `last`, FIFO insertion, SRAM
  acceptance and final originating ACK remain distinct events.
- Abort/response-error behavior, retained successful read outputs, global
  drain, completion backpressure and clean restart remain identical to the
  fixed-count version. Already accepted writes are never rolled back.

This matches the output-slot boundary in
`experiments/integration/int8stream/contract.json`: 398-word slots carry only
the actual Rice32 prefix. A controller must subsequently write each bit-length
header, and write the final task magic only after all payloads and headers
are acknowledged. That controller and complete-task measurement are not
implemented or claimed by this transport experiment.

The 16-word read FIFO and 8-word write FIFO remain 96 data bytes. The extension
adds mode/closed state and records the actual count in the existing write-count
register; it does not introduce a whole-tile buffer. Both native official
fabric tests and explicitly test-only delayed-return credit tests are retained.
