"""Lossless private storage for the declared signed10 weight contract."""
def transform(core):
 def replace(old,new):
  nonlocal core
  assert core.count(old)==1,(old,core.count(old));core=core.replace(old,new)
 replace('logic [383:0] wp_wdata;','logic [319:0] wp_wdata;')
 replace('wire [383:0] wp_rdata;','wire [319:0] wp_rdata;')
 replace('wp_wdata[c*24+:24]=w_wdata[c];','wp_wdata[c*20+:20]={w_wdata[c][21:12],w_wdata[c][9:0]};')
 replace('q12_striped_sram #(.WIDTH(384),','q12_striped_sram #(.WIDTH(320),')
 replace('.wmask({384{1\'b1}})', '.wmask({320{1\'b1}})')
 replace('assign w_rdata[c]=wp_rdata[c*24+:24];',
         'assign w_rdata[c]={{2{wp_rdata[c*20+19]}},wp_rdata[c*20+10+:10],{2{wp_rdata[c*20+9]}},wp_rdata[c*20+:10]};')
 # Reject malformed signed12 words that do not represent the declared signed10
 # numbers. Reuse the existing error drain; never silently truncate invalid data.
 bad=' || '.join('(w_data[%d:%d]!={2{w_data[%d]}})'%(12*i+11,12*i+10,12*i+9)for i in range(4))
 replace('assign metadata_fault = meta_fire && meta_count_q==39 && (load_meta_bad_q || meta_bad || !(&c_complete_q));',
         'assign metadata_fault = (w_fire && ('+bad+')) || (meta_fire && meta_count_q==39 && (load_meta_bad_q || meta_bad || !(&c_complete_q)));')
 return core
