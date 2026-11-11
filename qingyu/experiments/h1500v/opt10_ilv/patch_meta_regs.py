"""opt9 accelerator (YWIDE): metadata goes straight into a second bias/shift
register set as it is written (FIO gather or MMIO window); START copies it to
the working set in one cycle and skips the 64-word metadata read phase.
The metadata RAM is still written, so MMIO readback is unchanged."""
import sys, pathlib

p = pathlib.Path(sys.argv[1])
raw = p.read_bytes().decode()
crlf = "\r\n" in raw
s = raw.replace("\r\n", "\n")


def rep(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        raise SystemExit(f"anchor count {n} != {count}: {old[:90]!r}")
    s = s.replace(old, new)


rep("""    reg [7:0] shift [0:LANES-1];
""", """    reg [7:0] shift [0:LANES-1];
    // opt9: next tile's metadata, assembled as the words are written
    reg signed [47:0] nbias [0:LANES-1];
    reg [7:0] nshift [0:LANES-1];
    reg [LANES-1:0] nbad;
""")

rep("""            if (hw_release) batch_ready[stream_slot]<=0;""",
    """            if (hw_release) batch_ready[stream_slot]<=0;""")  # anchor check only

# START: take the staged metadata, go straight to the first row group
rep("""                                        weight_pending<=0;
""", """                                        weight_pending<=0;
                                        if (YWIDE) begin
                                            for (si=0; si<LANES; si=si+1) begin bias[si]<=nbias[si]; shift[si]<=nshift[si]; end
                                            engine_state<=E_ROW_INIT;
                                            if (|nbad) begin
                                                busy<=0; error_flag<=1; error_code<=ERR_METADATA; engine_state<=E_IDLE;
                                            end
                                        end
""")

# metadata capture block, appended before endmodule's SYNTHESIS check
rep("""`ifndef SYNTHESIS
    initial begin""", """    // opt9 metadata capture: segment 0..2 = bias[15:0],[31:16],[47:32], 3 = {0,shift}
    integer mi, me;
    always @(posedge clk) begin
        if (!rst_n) nbad <= 0;
        else if (YWIDE) begin
`ifdef QINGYU_BLOCK_COPY
            if (meta_wr_en) begin
                mi = meta_wr_addr[5:2];
                case (meta_wr_addr[1:0])
                    2'd0: nbias[mi][15:0] <= meta_wr_data;
                    2'd1: nbias[mi][31:16] <= meta_wr_data;
                    2'd2: nbias[mi][47:32] <= meta_wr_data;
                    2'd3: begin nshift[mi] <= meta_wr_data[7:0];
                                nbad[mi] <= (meta_wr_data[15:8]!=0) || (meta_wr_data[7:0]>47); end
                endcase
            end else
`endif
            if (((bus_state==B_LO)||(bus_state==B_HI)) && bus_kind==2 && !bus_read) begin
                me = bus_index + (bus_state==B_HI ? 1 : 0);
                mi = me / 4;
                case (me % 4)
                    0: nbias[mi][15:0] <= bus_half;
                    1: nbias[mi][31:16] <= bus_half;
                    2: nbias[mi][47:32] <= bus_half;
                    3: begin nshift[mi] <= bus_half[7:0];
                             nbad[mi] <= (bus_half[15:8]!=0) || (bus_half[7:0]>47); end
                endcase
            end
        end
    end

`ifndef SYNTHESIS
    initial begin""")
if crlf:
    s = s.replace("\n", "\r\n")
p.write_bytes(s.encode())
print("meta regs patched")
