# Exact INT8 paired inner product experiment

This directory is independent of the frozen SoC candidates. It proves an integer arithmetic identity with hardware-computed factors; it does not claim a new throughput, area or energy score. There is no new model fitting, cached task answer, SRAM bypass or vendor change.

For 64 terms, define `R = sum(x[2p]*x[2p+1])` and `C = sum(w[2p]*w[2p+1])`. Expansion over integers gives

```
b + sum(x[k]*w[k])
  = b - R - C + sum((x[2p]+w[2p+1])*(x[2p+1]+w[2p])).
```

Every term of `R` and `C` is computed by `winograd_int8_factor32`. The testbench supplies the dot unit only with captured outputs of these hardware units. Its independent expected answer uses the ordinary 64 products. Bias and factors are sampled on the first accepted pair; deliberately changing later metadata does not change the result.

`winograd_int8_factor32` has one signed8 multiplier, a signed21 accumulator and an elastic product register. `winograd_int8_dot64` has two signed9 pre-adders, one signed9 multiplier, a signed23 pair accumulator, factor correction and bias addition. Both accept one pair per cycle, can queue a multiply behind a stalled response, and hold output data stable under backpressure. A frame contains exactly 32 handshakes. Reset is synchronous active-low and abandons partial or completed unconsumed frames.

The full signed8 range includes -128. Pair sums span [-256,254], requiring signed9; their products span [-65024,65536], requiring signed18. Thirty-two ordinary products give a factor in [-520192,524288], so signed20 fails at the positive endpoint and signed21 is required. Pair accumulation spans [-2080768,2097152], fitting signed23. The final ordinary dot lies in [-1040384,1048576], fitting signed22. With signed16 bias, the conservative correction-prefix magnitude is at most `32768 + 2*524288 + 32*65536 = 3178496`; the implementation uses signed24 for correction/result. These are algebraic range proofs, not a formal-tool equivalence claim.

Default `BIAS_W=16` explicitly matches a compact-bias numerical format. The separate `BIAS_W=48` configuration produces signed49, which contains the exact mathematical bias-plus-dot for every signed48 bias. It does **not** reproduce a legacy exception raised by a signed48 overflow after an individual original MAC. Retaining that exception policy requires a separate integration decision; narrowing arbitrary 48-bit bias to 16-bit is not allowed.

Without stalls, a result becomes valid one clock after the 32nd input handshake. The first input-to-output-handshake latency is 33 clocks and consecutive complete frames can produce a response every 32 clocks. Factors are computed separately and their time must be counted unless safely overlapped in hardware. The last pair accumulation, two factor subtractions and bias addition currently form one combinational path: these cycle counts do not establish 150 MHz timing closure.

For an `M x 64` input and `64 x N` weight matrix, reused factors reduce multiplications from `64*M*N` to `32*M*N + 32*M + 32*N`. At M=99,N=256, this is 1,622,016 versus 822,368 multiplications, a 49.2996% operation-count reduction. The pair multipliers are 9x9 rather than 8x8; pre-adds, factor storage, correction and control are additional hardware. This operation count is not an area or energy estimate. Without cross-output reuse, one isolated dot plus its own factors costs 96 multiplications and is worse than 64.

An 8-row by 16-channel array of 128 pair multipliers would have a padded paired body of `ceil(99/8)*32*16=6656` cycles. Sequential factor phases at 8 rows / 16 columns add 416+512 cycles, giving a conditional 7584-cycle arithmetic schedule before fill/drain, memory, control, correction conflicts or RNE. All 355 factors require 7455 data bits, or 11360 bits if each uses a 32-bit slot. SRAM must supply two adjacent signed8 values per row/column per cycle; the current production INT16 layout does not establish this bandwidth. Cold-start factor recomputation and all input/output traffic remain required.

Run from the project root:

```
.venv-model/Scripts/python.exe experiments/arithmetic/winograd_int8/run_checks.py
```

The runner compiles Icarus self-checking tests for three fixed seeds and performs strict Verilator lint on factor, dot16 and dot48. It preserves commands, logs, source hashes and results in a new build directory. The tests cover all 7^4 combinations drawn from {-128,-127,-1,0,1,126,127}, 500 random vectors per seed, extreme signed16/signed48 biases, partial-frame and response/pipeline resets, response/input backpressure, metadata sampling and continuous-frame timing. No full-SoC, official-loader, synthesis, STA, CDC-tool or PPA signoff is implied.
