"""opt6 accelerator (YWIDE / INT16 build only):
 1. tile chaining: the batch slot toggles per completed batch (not row_index[3])
    and START is accepted while a batch is still waiting for the host;
 2. store unit decoupled from the MAC engine: the bias enters with the first
    product (no accumulator init), so the next row group starts its reads while
    the previous group is still being stored (issue at store cycle >= 5)."""
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


rep("""    localparam [2:0] E_IDLE=0, E_META_REQ=1, E_META_CAP=2,
                     E_ROW_INIT=3, E_MAC_REQ=4, E_MAC_CAP=5, E_STORE=6, E_DRAIN=7;""",
    """    localparam [3:0] E_IDLE=0, E_META_REQ=1, E_META_CAP=2,
                     E_ROW_INIT=3, E_MAC_REQ=4, E_MAC_CAP=5, E_STORE=6, E_DRAIN=7,
                     E_WAITST=8, E_FINAL=9;""")
rep("    reg [2:0] bus_state, engine_state;", "    reg [2:0] bus_state;\n    reg [3:0] engine_state;")

rep("""    wire write_slot = row_index[3];""", """    // opt6 (YWIDE): store unit state.  sv: a row group is being stored;
    // sc = {row-in-group[1:0], lane-half}; sbase = first row of that group.
    reg sv, wslot;
    reg [2:0] sc;
    reg [31:0] sbase;
    wire [31:0] srow = sbase + sc[2:1];
    // YWIDE: the batch slot alternates per completed batch, across tiles.
    wire write_slot = YWIDE ? wslot : row_index[3];""")

rep("""    wire producer_stall = DOUBLE_BUFFER && engine_state==E_STORE && lane_index==0 &&
                          odd_store==0 && batch_ready[write_slot];""",
    """    wire producer_stall = YWIDE ? (sv && sc==3'd0 && batch_ready[write_slot]) :
                          DOUBLE_BUFFER && engine_state==E_STORE && lane_index==0 &&
                          odd_store==0 && batch_ready[write_slot];""")

# bias enters with the first product
rep("""    wire signed [15:0] x_value = x_rdata[0];""", """    wire signed [15:0] x_value = x_rdata[0];
    // opt6: marks the k=0 product (bias replaces the accumulator operand).
    reg op_first, prod_first;
    always @(posedge clk) begin
        op_first <= engine_state==E_MAC_CAP && k_index==0;
        prod_first <= op_first;
    end
    wire first_bias = YWIDE && prod_first;""")
rep("""                assign sums2[g]=$signed({acc2[g][47],acc2[g]})+$signed({{17{product2[31]}},product2});
                assign sums3[g]=$signed({acc3[g][47],acc3[g]})+$signed({{17{product3[31]}},product3});
                assign odd_sums[g] = $signed({odd_acc[g][47],odd_acc[g]}) + $signed({{17{odd_product[31]}},odd_product});""",
    """                wire signed [47:0] base1 = first_bias ? bias[g] : odd_acc[g];
                wire signed [47:0] base2 = first_bias ? bias[g] : acc2[g];
                wire signed [47:0] base3 = first_bias ? bias[g] : acc3[g];
                assign sums2[g]=$signed({base2[47],base2})+$signed({{17{product2[31]}},product2});
                assign sums3[g]=$signed({base3[47],base3})+$signed({{17{product3[31]}},product3});
                assign odd_sums[g] = $signed({base1[47],base1}) + $signed({{17{odd_product[31]}},odd_product});""")
rep("""            assign sums[g] = $signed({acc[g][47],acc[g]}) +
                             $signed({{17{products[g][31]}},products[g]});""",
    """            wire signed [47:0] base0 = first_bias ? bias[g] : acc[g];
            assign sums[g] = $signed({base0[47],base0}) +
                             $signed({{17{products[g][31]}},products[g]});""")

rep("""    wire store_fire = busy && engine_state==E_STORE && !producer_stall;""",
    """    wire store_fire = YWIDE ? (busy && sv && !producer_stall) :
                              (busy && engine_state==E_STORE && !producer_stall);
    // opt6: next row group may issue its k=0 read once the store is at cycle 5:
    // its first accumulator write lands 3 cycles later, after the last store.
    wire mac_kick = YWIDE && engine_state==E_WAITST && (!sv || sc>=3'd5);""")

rep("""            if (engine_state==E_MAC_REQ || prefetch) begin""",
    """            if (engine_state==E_MAC_REQ || prefetch || mac_kick) begin""")

rep("""            if (engine_state==E_STORE && !producer_stall) begin""",
    """            if (store_fire) begin""")
rep("""                    y_addr[store_lane]={write_slot,store_row[2:0],lane_index[3]};
                    y_wdata[store_lane]=round_sat16(odd_store==3 ? acc3[{lane_index[3],store_lane[2:0]}] : odd_store==2 ? acc2[{lane_index[3],store_lane[2:0]}] : odd_store==1 ? odd_acc[{lane_index[3],store_lane[2:0]}] : acc[{lane_index[3],store_lane[2:0]}],shift[{lane_index[3],store_lane[2:0]}]);""",
    """                    y_addr[store_lane]={write_slot,srow[2:0],sc[0]};
                    y_wdata[store_lane]=round_sat16(sc[2:1]==3 ? acc3[{sc[0],store_lane[2:0]}] : sc[2:1]==2 ? acc2[{sc[0],store_lane[2:0]}] : sc[2:1]==1 ? odd_acc[{sc[0],store_lane[2:0]}] : acc[{sc[0],store_lane[2:0]}],shift[{sc[0],store_lane[2:0]}]);""")

# resets
rep("""            rd_bank<=0; weight_pending<=0; bank_rotated<=0;
""", """            rd_bank<=0; weight_pending<=0; bank_rotated<=0;
            sv<=0; sc<=0; sbase<=0; wslot<=0;
""")
rep("""            meta_assembly<=0;
        end else begin
            if (icb_rsp_valid && icb_rsp_ready) icb_rsp_valid<=0;""",
    """            meta_assembly<=0;
            sv<=0; sc<=0; wslot<=0;
        end else begin
            if (icb_rsp_valid && icb_rsp_ready) icb_rsp_valid<=0;
            if (!busy) sv<=0;""")

# START with a batch still pending (YWIDE)
rep("""                                else if (icb_cmd_wdata[0] && (busy || (DOUBLE_BUFFER && |batch_ready))) respond_error(ERR_BUSY_START);""",
    """                                else if (icb_cmd_wdata[0] && (busy || (DOUBLE_BUFFER && !YWIDE && |batch_ready))) respond_error(ERR_BUSY_START);""")
rep("""                                        busy<=1; done_flag<=0; output_count<=0; compute_cycles<=0;
""", """                                        busy<=1; done_flag<=0; output_count<=0; compute_cycles<=0;
                                        // nothing waiting for the host: restart the slot sequence
                                        if (YWIDE && batch_ready==0) wslot<=0;
""")

# MAC end -> store unit
rep("""                        else if (k_index==K-1) begin lane_index<=0; engine_state<=E_STORE; end""",
    """                        else if (k_index==K-1 && YWIDE) begin
                            sv<=1; sc<=0; sbase<=row_index; k_index<=0;
                            if (row_index+4<ROWS) begin row_index<=row_index+4; engine_state<=E_WAITST; end
                            else engine_state<=E_FINAL;
                        end
                        else if (k_index==K-1) begin lane_index<=0; engine_state<=E_STORE; end""")

rep("""                    end else lane_index<=lane_index+STORE_STEP;
                end
                default: ;
            endcase
        end
    end
""", """                    end else lane_index<=lane_index+STORE_STEP;
                end
                E_WAITST: if (mac_kick) engine_state<=E_MAC_CAP;
                E_FINAL: ;
                default: ;
            endcase
            // opt6 store unit (YWIDE): 8 cycles per 4-row group, 2 per row.
            if (YWIDE && store_fire) begin
                if (sc[0]) begin
                    if (srow[2:0]==7 || srow==ROWS-1) begin
                        batch_ready[write_slot]<=1;
                        batch_tail[write_slot]<=srow==ROWS-1;
                        wslot<=!wslot;
                    end
                    if (sc[2:1]!=2'd3 && srow+1<ROWS) sc<=sc+3'd1;
                    else begin
                        sv<=0;
                        if (srow==ROWS-1) begin
                            busy<=0; done_flag<=1; output_count<=ROWS*LANES; engine_state<=E_IDLE;
                        end
                    end
                end else sc<=sc+3'd1;
            end
        end
    end
""")
if crlf:
    s = s.replace("\n", "\r\n")
p.write_bytes(s.encode())
print("accel patched")
