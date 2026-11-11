"""opt6 firmware:
 - driver: tile chaining (the last batch of tile n is copied out after START of
   tile n+1; batch slots follow a running sequence across tiles);
 - environment: the FIO staging engine also copies bias+shift (0xb4 pre-copy)
   in parallel with the CPU's input staging."""
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
    ("""#ifndef QINGYU_EARLY_TILE0
""", """#ifndef QINGYU_TILE_CHAIN
/* INT16 build: START the next tile before its predecessor's last batch has
 * been copied out (hardware keeps a running batch-slot sequence). */
#ifdef QINGYU_OUT16
#define QINGYU_TILE_CHAIN 1
#else
#define QINGYU_TILE_CHAIN 0
#endif
#endif
#ifndef QINGYU_BG_META
/* Environment: FIO staging engine also copies bias+shift (command 0xb4). */
#define QINGYU_BG_META 1
#endif
#ifndef QINGYU_EARLY_TILE0
"""),
])

patch("soc_perf_main.c", [
    ("""#if QINGYU_BG_STAGE
        /* opt5: the W staging engine has its own shared-SRAM ports, so it
         * starts first and runs alongside the input/metadata staging. */
        *(volatile uint32_t *)(uintptr_t)0xf00000b0u = 0xa0004000u;
#endif
        load_words(0, 99u * 64u / 2u);
        load_words(0xc000u, 256u * 2u);
        load_words(0xc800u, 256u / 4u);
""", """#if QINGYU_BG_STAGE
#if QINGYU_BG_META
        /* opt6: bias (512 words) + shift (64 words) = 36 x 64-byte units,
         * copied by the staging engine ahead of the W pairs. */
        *(volatile uint32_t *)(uintptr_t)0xf00000b4u = 0xa000c000u | 36u;
#endif
        /* opt5: the W staging engine has its own shared-SRAM ports, so it
         * starts first and runs alongside the input staging. */
        *(volatile uint32_t *)(uintptr_t)0xf00000b0u = 0xa0004000u;
#endif
        load_words(0, 99u * 64u / 2u);
#if !(QINGYU_BG_STAGE && QINGYU_BG_META)
        load_words(0xc000u, 256u * 2u);
        load_words(0xc800u, 256u / 4u);
#endif
"""),
])

patch("qingyu_accel.c", [
    ("""void qingyu_init(qingyu_device *device, uintptr_t base, uint32_t poll_limit)""",
     """#if QINGYU_TILE_CHAIN && defined(QINGYU_DOUBLE_BUFFER) && defined(QINGYU_READ_AHEAD) && \\
    defined(QINGYU_BLOCK_COPY) && defined(QINGYU_FAST_TASK)
#define QINGYU_CHAIN_ACTIVE 1
/* Wait for one output batch in `slot`, copy it to `destination` with the FIO
 * batch command and release the slot. */
static int drain_batch(const qingyu_device *device, qingyu_result *result,
                       uint32_t slot, uint32_t rows, uint32_t destination)
{
    const uint32_t status_addr = QINGYU_REG_BATCH_A + 4u * slot;
    volatile const uint32_t *ready_reg =
        (volatile const uint32_t *)(device->base + status_addr);
    uint32_t left = device->poll_limit, count;
    do { count = *ready_reg; } while (!count && --left);
    if (count != rows * QINGYU_LANES / QINGYU_OUT_PER_WORD) {
        result->hardware_error = read_register(device, QINGYU_REG_ERROR);
        return count ? QINGYU_ERR_HARDWARE : QINGYU_ERR_TIMEOUT;
    }
    qingyu_fence();
    write_register(device, slot ? 0x40u : 0x3cu, destination);
    qingyu_fence();
    write_register(device, status_addr, 1u);
    return QINGYU_OK;
}
#endif

void qingyu_init(qingyu_device *device, uintptr_t base, uint32_t poll_limit)"""),
    ("""    if (deferred_input != 0u) write_register(device,0x90u,deferred_input);
""", """    if (deferred_input != 0u) write_register(device,0x90u,deferred_input);
#if QINGYU_CHAIN_ACTIVE && !QINGYU_IL_ACTIVE
    /* Tile chaining: every batch goes through drain_batch(); the last batch
     * of a tile is drained after the next tile's START. */
    const int chain = weight_stream && meta_block
        && ((uintptr_t)job->output & QINGYU_OUT_ALIGN_MASK) == 0
        && (uintptr_t)job->output >= 0xa0000000u && (uintptr_t)job->output <= 0xa0067400u;
    uint32_t batch_seq = 0u, tail_rows = 0u, tail_slot = 0u, tail_dest = 0u;
#endif
"""),
    ("""#ifdef QINGYU_DOUBLE_BUFFER
        for (uint32_t first=0; first<QINGYU_ROWS; first+=8) {
            uint32_t slot=(first/8)%2;
            uint32_t rows=QINGYU_ROWS-first < 8 ? QINGYU_ROWS-first : 8;
""", """#ifdef QINGYU_DOUBLE_BUFFER
#if QINGYU_CHAIN_ACTIVE && !QINGYU_IL_ACTIVE
        if (chain && tail_rows != 0u) {
            status = drain_batch(device, result, tail_slot, tail_rows, tail_dest);
            if (status != QINGYU_OK) {
                goto abort_task;
            }
            tail_rows = 0u;
            ++batch_seq;
        }
#endif
        for (uint32_t first=0; first<QINGYU_ROWS; first+=8) {
            uint32_t slot=(first/8)%2;
            uint32_t rows=QINGYU_ROWS-first < 8 ? QINGYU_ROWS-first : 8;
#if QINGYU_CHAIN_ACTIVE && !QINGYU_IL_ACTIVE
            if (chain) {
                const uint32_t dest = (uint32_t)(uintptr_t)(job->output + first * QINGYU_COLS + column_base);
                slot = batch_seq & 1u;
                if (first + 8u >= QINGYU_ROWS && tile + 1u < tile_count) {
                    tail_rows = rows; tail_slot = slot; tail_dest = dest;
                    break;
                }
                status = drain_batch(device, result, slot, rows, dest);
                if (status != QINGYU_OK) {
                    goto abort_task;
                }
                ++batch_seq;
                continue;
            }
#endif
"""),
])
