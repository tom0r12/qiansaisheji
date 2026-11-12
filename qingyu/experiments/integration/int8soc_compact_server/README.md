# Compact private SRAM: real E203 fixture and assessment packages

This independent directory changes only the private SRAM mapping selected by
the physical verification and assessment filelists. The frozen `int8soc_server`
R2 fixtures, private compact wrapper, two compute cores, bounded codec, official
fabric, CPU/shared SRAM wrappers and original SoC runners remain unchanged.
`ORIGINS.json` records the copied R2 files; `BASE_SERVER_SOURCE_SHA256.json`
retains their parent inventory. Server instructions are in `SERVER_README.md`.

Both local four-state, actual-E203 first-layer runs passed with every reported
metric equal to the corresponding original behavioral run:

| Core | X valid words/bank | CPU setup through marker ACK | Core cycles | Private128 | Private1024 |
|---|---:|---:|---:|---:|---:|
| prefetch8 | 416 | 10086 | 10043 | 53 | 0 |
| task9 | 352 | 9616 | 9573 | 48 | 0 |

Each run initialized and read back all131072 shared words using real wrapper
ports. Both retained64 shared4096 and16 CPU4096 macros; each performed7879
runtime commands/responses,4522 logical reads and3357 writes. The readback
checked6385 output-region words,4522 source words and every guard/untouched
location. `VALIDATION.json` gives exact report/package paths and SHA256 values.

The external local functional model has SHA256
`cd78caa3d3484f22d397b173e9c6a610c76939f53b7ff332a0dd55354bae9a33`.
It implements synchronous read and poisons Q after write. It is not a
manufacturer model and is absent from the archives. Only one complete
physical-interface SoC task per core has been checked here. The packaged
72-task diagnostic corpus passed on the original behavioral compositions;
it remains a server manufacturer-model regression obligation for these exact
compact physical compositions. No new PPA or official600 result is claimed.

Reproduce each complete local fixture in WSL from the project root:

```sh
python3 experiments/integration/int8soc_compact_server/local_fixture_check.py \
 --soc-run build/int8soc/20261111T174218864779Z \
 --images build/int8_packets_20261112 \
 --models build/bundle_template_checks/20261111T162200Z/local_functional_models.sv \
 --simulator iverilog
# For task9 substitute build/int8soc/20261111T175515904061Z.
```

`local_fixture_check.py` selects416 only for prefetch8 and352 only for task9,
verifies the frozen compact manifest, and creates an explicit configuration
source as the first actual compiled file. `prepare_bundle.py` copies that
same configuration byte for byte as `assessment/private_x_config.v`, first
in the physical and synthesis lists. Missing/default configuration therefore
cannot silently turn the8-row core into the352-word mapping. Compiled macro
source hashes and order are checked against the actual passing Icarus invocation.

```sh
python3 experiments/integration/int8soc_compact_server/prepare_bundle.py \
 --corpus-run build/int8soc_corpus/20261111T174454919053Z \
 --fixture-evidence build/int8soc_compact_physical_fixture/20261111T183709887253Z/result.json \
 --core-dir experiments/arithmetic/winograd_task8_prefetch
python3 experiments/integration/int8soc_compact_server/check_bundle.py BUNDLE_DIRECTORY \
 --fixture-run build/int8soc_compact_physical_fixture/20261111T183709887253Z
python3 experiments/integration/int8soc_compact_server/check_model_gates.py BUNDLE_DIRECTORY
```

For task9 select corpus `20261111T175642268453Z`, physical fixture
`20261111T183727570930Z`, and core `experiments/arithmetic/winograd_task9`.
Each package has a unique directory and a hash-checking `qic` launcher.

The actual compiled macro hierarchy is classified independently by instance
path. Private page selectors, decode and Q mux are included in new compute
area. All128 and4096 macros require reviewed official area/model identities;
unexpected1024 instances fail both pre- and post-synthesis inventories.
R2 library archive/DB identity, vendor header hashes, post-run input checks and
three-way activity artifact identities remain enforced. Whole-SoC power includes
CPU, shared/private memories and all added logic. Only stated unchanged CPU,
fabric/peripheral and fixed shared/CPU macro boundaries are area exclusions.

Reduced storage capacity alone does not prove an area improvement: the new
small-macro instances and selection logic must be assessed using official
macro area and timing. Macro CQ plus the page mux is a new timing path.
Source preload and boot remain outside the engineering CPU-setup window;
the official loader boundary is unresolved. No remote execution is performed.
