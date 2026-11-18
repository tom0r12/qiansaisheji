R = [
 ("""            if (busy) total_cycles<=total_cycles+1;
            case(state_q)
                X_LOAD: load_cycles<=load_cycles+1;
                X_DRAIN: factor_cycles<=factor_cycles+1;
                WAIT_SLOT: begin
                    if(loader_q==L_COMMIT || loader_q==L_DRAIN) factor_cycles<=factor_cycles+1;
                    else load_cycles<=load_cycles+1;
                end
                M_READ,M_WAIT: cache_read_cycles<=cache_read_cycles+1;
                DOT_READ,DOT_WAIT: compute_cycles<=compute_cycles+1;
                TILE_DRAIN,ERROR_DRAIN: store_cycles<=store_cycles+1;
                default: begin end
            endcase
""", """            // Free-running per-phase diagnostic counters removed (area/power);
            // the engine-level task cycle counter remains architecturally visible.
"""),
]
