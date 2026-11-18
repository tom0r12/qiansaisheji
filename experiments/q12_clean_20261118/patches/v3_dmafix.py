R = [
 (" assign p_cmd_valid=busy&&!error_q&&(phase==REQUEST||(phase==READ&&cooldown==0));",
  " // Never withdraw an offered command: an announced burst always completes.\n assign p_cmd_valid=busy&&(phase==REQUEST||(phase==READ&&cooldown==0));"),
 ("        if(issued+14'd1!=length)begin burst_count<=",
  "        if(issued+14'd1!=length&&!error_q)begin burst_count<="),
]
