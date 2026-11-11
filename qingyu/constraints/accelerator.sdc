# 150 MHz accelerator constraint template for the formal ASIC tool flow.
# Delays, slew, uncertainty and loads must come from the platform requirements.
# The reset is synchronous and remains timed; no broad false-path exceptions.
if {![info exists CLOCK_PERIOD_NS]} { set CLOCK_PERIOD_NS 6.666666667 }
foreach required {INPUT_DELAY_NS OUTPUT_DELAY_NS CLOCK_UNCERTAINTY_NS INPUT_SLEW_NS OUTPUT_LOAD_PF} {
    if {![info exists $required]} {
        error "Missing platform constraint $required; supply it before sourcing accelerator.sdc"
    }
    if {[set $required] < 0} { error "$required must be nonnegative" }
}
if {$CLOCK_PERIOD_NS <= 0} { error "CLOCK_PERIOD_NS must be positive" }

create_clock -name sys_clk -period $CLOCK_PERIOD_NS [get_ports clk]
set_clock_uncertainty $CLOCK_UNCERTAINTY_NS [get_clocks sys_clk]
set timed_inputs [remove_from_collection [all_inputs] [get_ports clk]]
set_input_delay $INPUT_DELAY_NS -clock sys_clk $timed_inputs
set_output_delay $OUTPUT_DELAY_NS -clock sys_clk [all_outputs]
set_input_transition $INPUT_SLEW_NS $timed_inputs
set_load $OUTPUT_LOAD_PF [all_outputs]

# Units assume the supplied library uses ns and pF. Verify library units for
# another technology before reusing this template. SRAM timing is provided by
# its actual macro library, not approximated by an invalid multicycle path.
