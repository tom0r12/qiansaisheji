# Explicit block timing contract. Values must be supplied with their provenance.
# No default numerical assumptions; units must be verified as ns and pF.
# Synchronous reset is timed as an input. No false/multicycle paths are added.
foreach required {
    CLOCK_PERIOD_NS INPUT_DELAY_MIN_NS INPUT_DELAY_MAX_NS
    OUTPUT_DELAY_MIN_NS OUTPUT_DELAY_MAX_NS
    SETUP_UNCERTAINTY_NS HOLD_UNCERTAINTY_NS
    INPUT_SLEW_NS CLOCK_SLEW_NS OUTPUT_LOAD_PF
} {
    if {![info exists $required] || ![string is double -strict [set $required]]} {
        error "Missing or nonnumeric platform timing parameter: $required"
    }
}
if {$CLOCK_PERIOD_NS <= 0} {error "Clock period must be positive"}
foreach nonnegative {SETUP_UNCERTAINTY_NS HOLD_UNCERTAINTY_NS INPUT_SLEW_NS CLOCK_SLEW_NS OUTPUT_LOAD_PF} {
    if {[set $nonnegative] < 0} {error "$nonnegative must be nonnegative"}
}
# Negative min delays can be valid, especially output hold requirements.
if {$INPUT_DELAY_MIN_NS > $INPUT_DELAY_MAX_NS || $OUTPUT_DELAY_MIN_NS > $OUTPUT_DELAY_MAX_NS} {
    error "Minimum IO delay exceeds maximum delay"
}
create_clock -name core_clk -period $CLOCK_PERIOD_NS [get_ports clk]
set_clock_uncertainty -setup $SETUP_UNCERTAINTY_NS [get_clocks core_clk]
set_clock_uncertainty -hold $HOLD_UNCERTAINTY_NS [get_clocks core_clk]
set_clock_transition $CLOCK_SLEW_NS [get_clocks core_clk]
set timed_inputs [remove_from_collection [all_inputs] [get_ports clk]]
set_input_delay -min $INPUT_DELAY_MIN_NS -clock core_clk $timed_inputs
set_input_delay -max $INPUT_DELAY_MAX_NS -clock core_clk $timed_inputs
set_output_delay -min $OUTPUT_DELAY_MIN_NS -clock core_clk [all_outputs]
set_output_delay -max $OUTPUT_DELAY_MAX_NS -clock core_clk [all_outputs]
set_input_transition $INPUT_SLEW_NS $timed_inputs
set_load $OUTPUT_LOAD_PF [all_outputs]
