"""opt8 driver: per tile one 0xc0 (automatic write-back of that tile's batches)
after START; one 0xc4 after the last tile waits until every batch is written."""
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


patch("qingyu_accel.h", [
    ("""#ifndef QINGYU_TILE_CHAIN
/* INT16 build: START the next tile before its predecessor's last batch has
 * been copied out (hardware keeps a running batch-slot sequence). */
#ifdef QINGYU_OUT16
#define QINGYU_TILE_CHAIN 1
#else
#define QINGYU_TILE_CHAIN 0
#endif
#endif""", """#ifndef QINGYU_AUTO_WB
/* INT16 build: the FIO writes every output batch back by itself (0xc0/0xc4). */
#ifdef QINGYU_OUT16
#define QINGYU_AUTO_WB 1
#else
#define QINGYU_AUTO_WB 0
#endif
#endif
#ifndef QINGYU_TILE_CHAIN
/* CPU-driven variant of the same overlap (superseded by QINGYU_AUTO_WB). */
#define QINGYU_TILE_CHAIN 0
#endif"""),
])

patch("qingyu_accel.c", [
    ("""    uint32_t batch_seq = 0u, tail_rows = 0u, tail_slot = 0u, tail_dest = 0u;
#endif
""", """    uint32_t batch_seq = 0u, tail_rows = 0u, tail_slot = 0u, tail_dest = 0u;
#endif
#if QINGYU_AUTO_WB && defined(QINGYU_DOUBLE_BUFFER) && defined(QINGYU_READ_AHEAD) && \\
    defined(QINGYU_BLOCK_COPY) && defined(QINGYU_FAST_TASK) && !QINGYU_IL_ACTIVE
#define QINGYU_AUTO_ACTIVE 1
    const int auto_wb = weight_stream && meta_block
        && ((uintptr_t)job->output & QINGYU_OUT_ALIGN_MASK) == 0
        && (uintptr_t)job->output >= 0xa0000000u && (uintptr_t)job->output <= 0xa0073be0u;
#else
    const int auto_wb = 0;
#endif
    /* With automatic write-back the per-batch CPU loop below is skipped. */
    const uint32_t wb_skip __attribute__((unused)) = auto_wb ? QINGYU_ROWS : 0u;
"""),
    ("""#ifdef QINGYU_DOUBLE_BUFFER
#if QINGYU_CHAIN_ACTIVE && !QINGYU_IL_ACTIVE
        if (chain && tail_rows != 0u) {""", """        if (auto_wb) {
            /* queue this tile: the FIO copies each batch as it completes */
            write_register(device, 0xc0u, (uint32_t)(uintptr_t)(job->output + column_base));
        }
#ifdef QINGYU_DOUBLE_BUFFER
#if QINGYU_CHAIN_ACTIVE && !QINGYU_IL_ACTIVE
        if (chain && tail_rows != 0u) {"""),
    ("""        for (uint32_t first=0; first<QINGYU_ROWS; first+=8) {""",
     """        for (uint32_t first=wb_skip; first<QINGYU_ROWS; first+=8) {"""),
    ("""        ++result->completed_tiles;
    }
    status = QINGYU_OK;""", """        ++result->completed_tiles;
    }
    if (auto_wb) {
        /* held by the FIO until every queued batch has been written back */
        write_register(device, 0xc4u, 0u);
    }
    status = QINGYU_OK;"""),
])
