"""opt7 accelerator (YWIDE): shadow accumulators.
After the last accumulate of a row group, the 4x16 accumulators are copied to
shadow registers in one cycle (E_SNAP = state 8); the store unit reads the
shadows, and the same cycle issues the next group's k=0 read (with the next
row index), so a row group costs 64 MAC + 2 drain + 1 snapshot cycles.
If the previous store is still waiting for a free batch slot, E_SNAP waits."""
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


rep("""                     E_WAITST=8, E_FINAL=9;""", """                     E_SNAP=8, E_FINAL=9;""")
rep("""    wire [31:0] srow = sbase + sc[2:1];""", """    wire [31:0] srow = sbase + sc[2:1];
    // opt7: shadow copies of the four row accumulators, read by the store unit.
    reg signed [47:0] sh0 [0:LANES-1], sh1 [0:LANES-1], sh2 [0:LANES-1], sh3 [0:LANES-1];
    wire [31:0] next_row = row_index + 4;""")
rep("""    // opt6: next row group may issue its k=0 read once the store is at cycle 5:
    // its first accumulator write lands 3 cycles later, after the last store.
    wire mac_kick = YWIDE && engine_state==E_WAITST && (!sv || sc>=3'd5);""",
    """    // opt7: snapshot cycle; also issues the next group's k=0 read.
    wire snap_go = YWIDE && engine_state==E_SNAP && !sv;
    wire mac_kick = snap_go && next_row < ROWS;""")
rep("""            if (engine_state==E_MAC_REQ || prefetch || mac_kick) begin
                x_en={row_index+3<ROWS,row_index+2<ROWS,odd_valid,1'b1};
                x_addr[0]=(row_index/4)*K+issue_k;""",
    """            if (mac_kick) begin
                x_en={next_row+3<ROWS,next_row+2<ROWS,next_row+1<ROWS,1'b1};
                x_addr[0]=(next_row/4)*K;
                x_addr[1]=x_addr[0]; x_addr[2]=x_addr[0]; x_addr[3]=x_addr[0];
                for (physical_index=0; physical_index<LANES; physical_index=physical_index+1) begin
                    w_en[physical_index]=1;
                    w_addr[physical_index]=0;
                end
            end
            if (engine_state==E_MAC_REQ || prefetch) begin
                x_en={row_index+3<ROWS,row_index+2<ROWS,odd_valid,1'b1};
                x_addr[0]=(row_index/4)*K+issue_k;""")
rep("""                    y_wdata[store_lane]=round_sat16(sc[2:1]==3 ? acc3[{sc[0],store_lane[2:0]}] : sc[2:1]==2 ? acc2[{sc[0],store_lane[2:0]}] : sc[2:1]==1 ? odd_acc[{sc[0],store_lane[2:0]}] : acc[{sc[0],store_lane[2:0]}],shift[{sc[0],store_lane[2:0]}]);""",
    """                    y_wdata[store_lane]=round_sat16(sc[2:1]==3 ? sh3[{sc[0],store_lane[2:0]}] : sc[2:1]==2 ? sh2[{sc[0],store_lane[2:0]}] : sc[2:1]==1 ? sh1[{sc[0],store_lane[2:0]}] : sh0[{sc[0],store_lane[2:0]}],shift[{sc[0],store_lane[2:0]}]);""")
rep("""                        else if (k_index==K-1 && YWIDE) begin
                            sv<=1; sc<=0; sbase<=row_index; k_index<=0;
                            if (row_index+4<ROWS) begin row_index<=row_index+4; engine_state<=E_WAITST; end
                            else engine_state<=E_FINAL;
                        end""", """                        else if (k_index==K-1 && YWIDE) begin
                            k_index<=0; engine_state<=E_SNAP;
                        end""")
rep("""                E_WAITST: if (mac_kick) engine_state<=E_MAC_CAP;""",
    """                E_SNAP: if (snap_go) begin
                    for (si=0; si<LANES; si=si+1) begin
                        sh0[si]<=acc[si]; sh1[si]<=odd_acc[si]; sh2[si]<=acc2[si]; sh3[si]<=acc3[si];
                    end
                    sv<=1; sc<=0; sbase<=row_index;
                    if (next_row<ROWS) begin row_index<=next_row; engine_state<=E_MAC_CAP; end
                    else engine_state<=E_FINAL;
                end""")
for bad in ("E_WAITST",):
    if bad in s:
        raise SystemExit("leftover " + bad)
if crlf:
    s = s.replace("\n", "\r\n")
p.write_bytes(s.encode())
print("accel shadow patched")
