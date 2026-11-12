# Single-stage MAC lane experiment

The frozen prefetch8 cache/control structure is retained. Each of128 lanes
computes the signed9-bit operand sums,9x9 product and23-bit accumulation in
one clock cycle, without the old registered18-bit product and three tags.
One central level-valid delay preserves the original completion schedule and
three W-bank write opportunities between DOT bursts.

The initial early-completion version was rejected by the unchanged checker:
it removed a W-write opportunity and eliminated metadata/load overlap. Its
failure is retained in `build/winograd_task8_single_mac/20261111T183030709943Z`.
The final version passed three seeds, each22 real/synthetic cases plus11
recovery completions,7 aborts,2 expected errors and8 resets. Complete private
no-stall timing remains9931cycles. Report:
`build/winograd_task8_single_mac/20261111T183314428041Z/result.json`.

Raw declared state difference is128×21 removed bits minus1 added central
control bit =2687bits. This is not mapped FF or physical area. SRAM geometry
and arithmetic precision are unchanged. Real SRAM timing and SoC results
remain separate validation stages.

The new path combines SRAM clock-to-Q, operand additions, multiplication and
accumulation. Its150MHz timing is unproven. This experiment must not replace
the original pipelined candidate without actual competition-library STA,
equivalence and power/area evidence.

The only lint waiver is DECLFILENAME for the alternate lane deliberately
stored in the same hashed core compilation unit. No logic warning is waived.
