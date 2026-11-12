# Independent INT8 E203 physical verification and server packaging

This directory owns new fixtures and packaging only. Frozen engine/core/codec,
the root INT8 SoC runner, legacy candidates and existing archives are unchanged.
Server-side usage and measurement limits are in `SERVER_README.md`.

`prepare_fixture.py` derives the independent physical checker from the validated
root `int8soc/tb_int8soc.sv`, requiring exact source anchors. It preserves every
runtime source/output/guard/path check, adds true-port preload and full131072-word
physical readback, and records the complete inclusive CPU setup activity window.
`prepare_templates.py` copies the reviewed fail-closed model/library gates into
this directory and adapts only INT8 source/metric/accounting boundaries; the
original template hashes are recorded in `TEMPLATE_ORIGINS.json`.

Reproduce local four-state fixture verification in WSL:

```sh
python3 experiments/integration/int8soc_server/local_fixture_check.py \
 --soc-run build/int8soc/20261111T174218864779Z \
 --images build/int8_packets_20261112 \
 --models build/bundle_template_checks/20261111T162200Z/local_functional_models.sv \
 --simulator iverilog
```

The explicit external model SHA is
`cd78caa3d3484f22d397b173e9c6a610c76939f53b7ff332a0dd55354bae9a33`.
It poisons Q after writes and models synchronous reads; it is a functional
substitute, not manufacturer timing/power evidence. It is never copied into
the server archive. Input filenames are relative to the simulation directory
because Icarus cannot reliably read the original non-ASCII absolute path.
The initial failed-path diagnostic remains under
`build/int8soc_physical_fixture/20261111T174625832811Z`.

Passed prefetch8 physical evidence:
`build/int8soc_physical_fixture/20261111T174803874627Z/result.json`.
All metrics match the real-CPU behavioral run exactly: CPU setup10086,
START10074,7879 commands/responses,4522 reads and3357 writes. Every shared
word was read back through the actual macro wrapper. The four-state compiled
hierarchy independently contains21/8/64/16 private128/private1024/shared4096/
CPU4096 macros; package checks classify every macro by its actual instance path.

Package a complete validated72-task composition, then audit its ZIP:

```sh
python3 experiments/integration/int8soc_server/prepare_bundle.py \
 --corpus-run build/int8soc_corpus/20261111T174454919053Z \
 --fixture-evidence build/int8soc_physical_fixture/20261111T174803874627Z/result.json \
 --core-dir experiments/arithmetic/winograd_task8_prefetch
python3 experiments/integration/int8soc_server/check_bundle.py BUNDLE_DIRECTORY \
 --fixture-run build/int8soc_physical_fixture/20261111T174803874627Z
```

`--core-dir experiments/arithmetic/winograd_task9` is an explicit alternative,
requiring its own passed72-task report and matching physical fixture evidence;
its ninth X macro is counted. Evidence from prefetch8 cannot authorize a task9
package. Package output directories are unique and historical ZIPs are untouched.

The package audit checks all file hashes and ordered compiled-source hashes,
ZIP CRC, Python/Tcl syntax, actual macro hierarchy, all INT8 area boundaries,
unconfigured-library rejection, absence of private-array shortcuts and external
macro models. It also excludes local credentials, instruction files and local
product names. No remote upload or EDA command is performed by these tools.

`VALIDATION.json` is the tracked summary for both completed72-task compositions,
their independent physical fixtures, current R2 archives and package checks.
`SOURCE_SHA256.json` freezes these preparation/checking tools and templates.
