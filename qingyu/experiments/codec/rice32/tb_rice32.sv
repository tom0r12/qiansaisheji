`timescale 1ns/1ps
`default_nettype none
module tb_rice32;
    parameter integer LANES=4;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0;
    reg es=0,ds=0;wire esr,dsr;
    reg [15:0] n=0;
    reg [31:0] declared_bits=0;
    reg [2:0] k=0;reg delta=0;reg [8:0] row_bytes=0;
    reg eiv=0,div=0,eir_last=0,dir_last=0;
    wire eir,dir,eov,dov;reg eor=0,dor=0;
    reg [31:0] eid=0,did=0;reg [2:0] eic=0;reg [5:0] dib=0;
    wire [31:0] eod,dod;wire [5:0] eob;wire [2:0] doc;
    wire eol,dol,eb,db,ed,dd,ee,de;
    wire [31:0] ec,dc,encoded,consumed;
    rice32_encoder #(.LANES(LANES)) encoder(.clk,.rst_n,.start_valid(es),.start_ready(esr),
        .start_symbols(n),.start_k(k),.start_delta(delta),.start_row_bytes(row_bytes),
        .in_valid(eiv),.in_ready(eir),.in_data(eid),.in_count(eic),.in_last(eir_last),
        .out_valid(eov),.out_ready(eor),.out_data(eod),.out_valid_bits(eob),.out_last(eol),
        .busy(eb),.done(ed),.error(ee),.total_cycles(ec),.encoded_bits(encoded));
    rice32_decoder #(.LANES(LANES)) decoder(.clk,.rst_n,.start_valid(ds),.start_ready(dsr),
        .start_symbols(n),.start_encoded_bits(declared_bits),.start_k(k),.start_delta(delta),.start_row_bytes(row_bytes),
        .in_valid(div),.in_ready(dir),.in_data(did),.in_valid_bits(dib),.in_last(dir_last),
        .out_valid(dov),.out_ready(dor),.out_data(dod),.out_count(doc),.out_last(dol),
        .busy(db),.done(dd),.error(de),.total_cycles(dc),.consumed_bits(consumed));
    reg [31:0] raw[0:16383],coded[0:32767];
    integer cycle=0,seed=17,case_id=0,mode=0,count=0,payload_bits=0;
    integer errors_tested=0,resets_tested=0,normal_tested=0;
    reg [31:0] rng=1;
    reg eh=0,dh=0;reg [38:0] epayload;reg [35:0] dpayload;
    integer eh_checks=0,dh_checks=0;
    function automatic [31:0] rand32;
        reg[31:0]v;begin v=rng;v=v^(v<<13);v=v^(v>>17);v=v^(v<<5);rng=v;rand32=v;end
    endfunction
    function automatic [31:0] symbol_word(input integer index,input integer amount);
        reg [31:0] value;begin value=raw[index/4]>>(8*(index%4));
            if(amount<4)value=value&((32'h1<<(8*amount))-1);symbol_word=value;end
    endfunction
    always @(posedge clk)begin
        cycle=cycle+1;
        if(cycle>10000000)$fatal(1,"global watchdog");
        if(!rst_n)begin eh=0;dh=0;end
        else begin
            if(eh)begin eh_checks=eh_checks+1;if(!eov || {eol,eob,eod}!==epayload)$fatal(1,"encoder held payload changed case=%0d",case_id);end
            if(dh)begin dh_checks=dh_checks+1;if(!dov || {dol,doc,dod}!==dpayload)$fatal(1,"decoder held payload changed case=%0d",case_id);end
            eh=eov&&!eor;dh=dov&&!dor;epayload={eol,eob,eod};dpayload={dol,doc,dod};
        end
    end
    task automatic reset_all;
        begin
            @(negedge clk);rst_n=0;es=0;ds=0;eiv=0;div=0;eor=0;dor=0;
            repeat(3)@(negedge clk);
            rst_n=1;
        end
    endtask

    task automatic encode_case(input integer stalls,output integer elapsed);
        integer sent,got,amount,wanted_bits,start_tick,ticks,low;
        reg take_in,take_out,source_held;reg[31:0]r;
        begin
            @(negedge clk);es=1;eor=0;
            @(posedge clk);if(!esr)$fatal(1,"encoder not ready at start");#1;start_tick=cycle;
            @(negedge clk);es=0;sent=0;got=0;ticks=0;low=0;source_held=0;
            while(!ed)begin
                amount=count-sent;if(amount>LANES)amount=LANES;
                r=rand32();
                eiv=sent<count && (source_held || stalls==0 || r[2:0]!=0);
                eid=sent<count?symbol_word(sent,amount):0;eic=3'(amount);eir_last=sent+amount==count;
                if(low>0)begin eor=0;low=low-1;end
                else if(stalls!=0 && r[8:4]==0)begin low=6+int'(r[12:9]);eor=0;end
                else eor=stalls==0 || r[3:1]!=0;
                @(posedge clk);take_in=eiv&&eir;take_out=eov&&eor;source_held=eiv&&!eir;
                if(eov)begin
                    wanted_bits=payload_bits-32*got;if(wanted_bits>32)wanted_bits=32;
                    if(wanted_bits<=0 || eod!==coded[got] || int'(eob)!=wanted_bits || eol!=(32*(got+1)>=payload_bits))
                        $fatal(1,"encoder mismatch case=%0d word=%0d got=%h/%0d/%b expected=%h/%0d",case_id,got,eod,eob,eol,coded[got],wanted_bits);
                end
                if(take_in)sent=sent+amount;if(take_out)got=got+1;
                #1;ticks=ticks+1;
                if(ee)$fatal(1,"encoder unexpected error case=%0d sent=%0d",case_id,sent);
                if(ticks>200000)$fatal(1,"encoder timeout case=%0d",case_id);
                if(ed)begin
                    elapsed=cycle-start_tick+1;
                    if(ec!=32'(elapsed) || encoded!=32'(payload_bits) || sent!=count || got!=(payload_bits+31)/32)
                        $fatal(1,"encoder completion/count/cycle mismatch case=%0d ec=%0d expected=%0d bits=%0d/%0d",case_id,ec,elapsed,encoded,payload_bits);
                end
                @(negedge clk);
            end
            eiv=0;eor=0;
        end
    endtask

    task automatic decode_case(input integer stalls,input reg expected_error,output integer elapsed);
        integer sent,got,amount,bits_now,start_tick,ticks,low;
        reg take_in,take_out,source_held;reg[31:0]r,expected;
        begin
            @(negedge clk);ds=1;dor=0;
            @(posedge clk);if(!dsr)$fatal(1,"decoder not ready at start");#1;start_tick=cycle;
            @(negedge clk);ds=0;sent=0;got=0;ticks=0;low=0;source_held=0;
            while(!dd)begin
                bits_now=payload_bits-32*sent;if(bits_now>32)bits_now=32;
                r=rand32();
                div=bits_now>0 && (source_held || stalls==0 || r[2:0]!=0);
                did=bits_now>0?coded[sent]:0;dib=6'(bits_now);dir_last=32*(sent+1)>=payload_bits;
                if(low>0)begin dor=0;low=low-1;end
                else if(stalls!=0 && r[8:4]==0)begin low=6+int'(r[12:9]);dor=0;end
                else dor=stalls==0 || r[3:1]!=0;
                @(posedge clk);take_in=div&&dir;take_out=dov&&dor;source_held=div&&!dir;
                if(dov && !expected_error)begin
                    amount=count-got;if(amount>LANES)amount=LANES;expected=symbol_word(got,amount);
                    if(amount<=0 || dod!==expected || int'(doc)!=amount || dol!=(got+amount==count))
                        $fatal(1,"decoder mismatch case=%0d index=%0d got=%h/%0d/%b expected=%h/%0d",case_id,got,dod,doc,dol,expected,amount);
                end
                if(dov && expected_error && dol)$fatal(1,"malformed frame emitted successful last case=%0d",case_id);
                if(take_in)sent=sent+1;if(take_out)got=got+int'(doc);
                #1;ticks=ticks+1;
                if(!expected_error && de)$fatal(1,"decoder unexpected error case=%0d sent=%0d decoded=%0d",case_id,sent,got);
                if(ticks>200000)$fatal(1,"decoder timeout case=%0d error=%b sent=%0d",case_id,de,sent);
                if(dd)begin
                    elapsed=cycle-start_tick+1;
                    if(dc!=32'(elapsed) || de!==expected_error)$fatal(1,"decoder done status/cycle mismatch");
                    if(!expected_error && (consumed!=32'(payload_bits) || got!=count || sent!=(payload_bits+31)/32))
                        $fatal(1,"decoder completion/count mismatch case=%0d",case_id);
                end
                @(negedge clk);
            end
            div=0;dor=0;
        end
    endtask

    task automatic errors_while_output_held;
        integer sent,t;
        begin
            @(negedge clk);n=96;k=3;delta=0;row_bytes=16;es=1;eor=0;
            @(posedge clk);#1;@(negedge clk);es=0;sent=0;t=0;
            while(!eov)begin
                eiv=1;eid=0;eic=3'(LANES);eir_last=0;
                @(posedge clk);if(eir)sent=sent+LANES;#1;t=t+1;
                if(t>200)$fatal(1,"encoder held-error setup timeout");@(negedge clk);
            end
            eiv=1;eic=0;eir_last=1;
            @(posedge clk);if(!eir)$fatal(1,"encoder cannot accept directed malformed beat");#1;
            @(negedge clk);eiv=0;repeat(6)@(negedge clk);
            if(!ee||!eov)$fatal(1,"encoder error failed to retain held output");
            eor=1;t=0;while(!ed)begin @(posedge clk);#1;t=t+1;if(t>20)$fatal(1,"encoder held-error drain timeout");end
            @(negedge clk);eor=0;errors_tested=errors_tested+1;

            @(negedge clk);n=32;k=3;delta=0;row_bytes=16;declared_bits=129;ds=1;dor=0;
            @(posedge clk);#1;@(negedge clk);ds=0;sent=0;
            while(sent<4)begin
                div=1;did=0;dib=32;dir_last=sent==3;
                @(posedge clk);if(dir)sent=sent+1;#1;@(negedge clk);
            end
            div=0;repeat(6)@(negedge clk);
            if(!de||!dov)$fatal(1,"decoder error failed to retain held output");
            dor=1;t=0;while(!dd)begin @(posedge clk);#1;t=t+1;if(t>20)$fatal(1,"decoder held-error drain timeout");end
            @(negedge clk);dor=0;errors_tested=errors_tested+1;
            // Configuration errors complete without waiting for nonexistent data.
            @(negedge clk);n=0;es=1;ds=1;declared_bits=1;
            @(posedge clk);#1;@(negedge clk);es=0;ds=0;
            @(posedge clk);#1;
            if(!ed||!dd||!ee||!de)$fatal(1,"zero-symbol configuration not rejected");
            @(negedge clk);errors_tested=errors_tested+2;
        end
    endtask

    task automatic encoder_error_checks;
        integer t;
        begin
            for(integer which=0;which<3;which=which+1)begin
                @(negedge clk);n=which==2?16'd4:16'd32;k=3;delta=0;row_bytes=64;es=1;
                @(posedge clk);#1;@(negedge clk);es=0;eiv=1;eid=0;eic=which==0?0:3'(LANES);eir_last=which!=2;eor=0;
                @(posedge clk);if(!eir)$fatal(1,"error input not accepted");#1;
                @(negedge clk);
                if(which==2)begin eic=1;eir_last=1;@(posedge clk);#1;@(negedge clk);end
                eiv=0;eor=1;t=0;
                while(!ed)begin @(posedge clk);#1;t=t+1;if(t>16)$fatal(1,"encoder error did not finish");end
                if(!ee)$fatal(1,"encoder malformed input not rejected");
                @(negedge clk);eor=0;errors_tested=errors_tested+1;
            end
        end
    endtask

    task automatic reset_inflight;
        integer sent,t;
        begin
            // Abort encoder before block completion, then during held output.
            for(integer which=0;which<2;which=which+1)begin
                @(negedge clk);n=64;k=3;delta=1;row_bytes=16;es=1;eor=0;
                @(posedge clk);#1;@(negedge clk);es=0;sent=0;t=0;
                while((which==0 && sent<LANES) || (which==1 && !eov))begin
                    eiv=sent<64;eid=32'h7f80ff00;eic=3'(LANES);eir_last=sent+LANES==64;
                    @(posedge clk);if(eiv&&eir)sent=sent+LANES;#1;t=t+1;
                    if(t>300)$fatal(1,"encoder reset setup timeout");@(negedge clk);
                end
                reset_all();resets_tested=resets_tested+1;
            end
            // Valid zero Rice block: flag0 then 32 codes of 0000 (k3), 129 bits.
            for(integer which=0;which<2;which=which+1)begin
                @(negedge clk);n=32;k=3;delta=1;row_bytes=16;declared_bits=129;ds=1;dor=0;
                @(posedge clk);#1;@(negedge clk);ds=0;sent=0;t=0;
                while((which==0 && sent<1) || (which==1 && !dov))begin
                    div=sent<5;did=0;dib=sent==4?1:32;dir_last=sent==4;
                    @(posedge clk);if(div&&dir)sent=sent+1;#1;t=t+1;
                    if(t>300)$fatal(1,"decoder reset setup timeout");@(negedge clk);
                end
                reset_all();resets_tested=resets_tested+1;
            end
        end
    endtask

    string manifest,raw_file,coded_file;
    integer fd,status,ki,di,rows,declared,enc_elapsed,dec_elapsed,stalls;
    initial begin
        if(!$value$plusargs("SEED=%d",seed))seed=17;rng=32'(seed);
        if(!$value$plusargs("MANIFEST=%s",manifest))manifest="manifest.txt";
        reset_all();encoder_error_checks();errors_while_output_held();reset_inflight();
        fd=$fopen(manifest,"r");if(fd==0)$fatal(1,"manifest missing");
        while(!$feof(fd))begin
            status=$fscanf(fd,"%d %d %d %d %d %d %d %d %s %s\n",case_id,mode,count,ki,di,rows,payload_bits,declared,raw_file,coded_file);
            if(status==10)begin
                $readmemh(raw_file,raw,0,(count+3)/4-1);$readmemh(coded_file,coded,0,(payload_bits+31)/32-1);
                n=16'(count);k=3'(ki);delta=1'(di);row_bytes=9'(rows);declared_bits=32'(declared);
                if(mode==0)begin
                    for(stalls=0;stalls<2;stalls=stalls+1)begin
                        encode_case(stalls,enc_elapsed);decode_case(stalls,0,dec_elapsed);
                        $display("CASE id=%0d stalls=%0d symbols=%0d bits=%0d enc_cycles=%0d dec_cycles=%0d",case_id,stalls,count,payload_bits,enc_elapsed,dec_elapsed);
                    end
                    normal_tested=normal_tested+1;
                end else begin decode_case(1,1,dec_elapsed);errors_tested=errors_tested+1;end
            end else if(status!=-1)$fatal(1,"malformed manifest fields=%0d",status);
        end
        $fclose(fd);repeat(4)@(negedge clk);
        if(eb||db||eov||dov)$fatal(1,"late busy/output");
        $display("PASS rice32 lanes=%0d seed=%0d normal=%0d errors=%0d resets=%0d held_encoder=%0d held_decoder=%0d",LANES,seed,normal_tested,errors_tested,resets_tested,eh_checks,dh_checks);
        $finish;
    end
endmodule
`default_nettype wire
