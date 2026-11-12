module task_inout_repro(input wire clk,input wire [7:0] value,input wire [3:0] amount,
                        output reg [15:0] payload,output reg [7:0] count);
 reg [15:0] temporary;
 integer cursor,previous;
 task automatic append;
  input [7:0] data;
  input integer length;
  inout reg [15:0] bits;
  inout integer used;
  begin bits=bits|({data,8'b0}>>used);used=used+length;end
 endtask
 always @(posedge clk)begin
  temporary=0;cursor=0;previous=cursor;
  append(value,amount,temporary,cursor);
  payload<=temporary;count<=cursor-previous;
 end
endmodule
