"""opt5 firmware: start the background W staging first; issue tile 0's weight
and metadata commands before the input load so they overlap it."""
import sys, pathlib

root = pathlib.Path(sys.argv[1])


def patch(name, pairs):
    p = root / name
    raw = p.read_bytes().decode()
    crlf = "\r\n" in raw
    s = raw.replace("\r\n", "\n")
    for old, new in pairs:
        n = s.count(old)
        if n != 1:
            raise SystemExit(f"{name}: anchor count {n}: {old[:80]!r}")
        s = s.replace(old, new)
    if crlf:
        s = s.replace("\n", "\r\n")
    p.write_bytes(s.encode())
    print("patched", name)


patch("soc_perf_main.c", [
    ("""        uint64_t start = read_cycles(NULL);
        load_words(0, 99u * 64u / 2u);
""", """        uint64_t start = read_cycles(NULL);
#if QINGYU_BG_STAGE
        /* opt5: the W staging engine has its own shared-SRAM ports, so it
         * starts first and runs alongside the input/metadata staging. */
        *(volatile uint32_t *)(uintptr_t)0xf00000b0u = 0xa0004000u;
#endif
        load_words(0, 99u * 64u / 2u);
"""),
    ("""#if QINGYU_BG_STAGE
        /* All W pairs (from pair 0) are staged by the FIO background engine. */
        *(volatile uint32_t *)(uintptr_t)0xf00000b0u = 0xa0004000u;
#elif QINGYU_INTERLEAVE_STAGE""", """#if QINGYU_BG_STAGE
        /* W pairs are staged by the FIO background engine (started above). */
#elif QINGYU_INTERLEAVE_STAGE"""),
])

patch("qingyu_accel.h", [
    ("""#ifndef QINGYU_BG_STAGE
""", """#ifndef QINGYU_EARLY_TILE0
/* Issue tile 0's weight and metadata commands before the input load. */
#define QINGYU_EARLY_TILE0 1
#endif
#ifndef QINGYU_BG_STAGE
"""),
])

patch("qingyu_accel.c", [
    ("""#ifdef QINGYU_FAST_TASK
    int direct = device->read32 == NULL && device->write32 == NULL
        && (((uintptr_t)job->input | (uintptr_t)job->weights) & 3u) == 0;
    if (direct) {
        volatile packed_word *dst = (volatile packed_word *)(device->base + QINGYU_INPUT_OFFSET);
        const packed_word *src = (const packed_word *)job->input;
        if (((uintptr_t)src & 63u)==0 && (uintptr_t)src>=0xa0000000u &&
            (uintptr_t)src<=0xa003c000u) {
            write_register(device,0x90u,(uint32_t)(uintptr_t)src);
        } else {""", """    uint32_t deferred_input = 0u; /* 0x90 source issued after the tile-0 prefetch */
#ifdef QINGYU_FAST_TASK
    int direct = device->read32 == NULL && device->write32 == NULL
        && (((uintptr_t)job->input | (uintptr_t)job->weights) & 3u) == 0;
    if (direct) {
        volatile packed_word *dst = (volatile packed_word *)(device->base + QINGYU_INPUT_OFFSET);
        const packed_word *src = (const packed_word *)job->input;
        if (((uintptr_t)src & 63u)==0 && (uintptr_t)src>=0xa0000000u &&
            (uintptr_t)src<=0xa003c000u) {
            deferred_input = (uint32_t)(uintptr_t)src;
        } else {"""),
    ("""#else
    const int weight_stream = 0;
#endif

    for (column_base = 0u; column_base < QINGYU_COLS;""", """#else
    const int weight_stream = 0;
#endif

    /* Tile 0's weight transfer and metadata gather run in the FIO while the
     * input load below keeps the CPU waiting (accelerator idle, W bank free). */
    int tile0_early = 0;
#if QINGYU_EARLY_TILE0
    if (deferred_input != 0u && weight_stream && meta_block) {
        write_register(device,0x80u,(uint32_t)(uintptr_t)job->weights);
        write_register(device,0xa0u,0u);
        tile0_early = 1;
    }
#endif
    if (deferred_input != 0u) write_register(device,0x90u,deferred_input);

    for (column_base = 0u; column_base < QINGYU_COLS;"""),
    ("""        if (!weight_stream || tile == 0) {""", """        if (!weight_stream || (tile == 0 && !tile0_early)) {"""),
    ("""            if (tile == 0u) write_register(device, 0xa0u, column_base);""",
     """            if (tile == 0u && !tile0_early) write_register(device, 0xa0u, column_base);"""),
])
