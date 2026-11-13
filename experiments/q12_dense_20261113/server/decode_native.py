"""Independent fixed-index readback; all 99x256 signed12 elements exist."""
import struct
def decode_output(words):
 if len(words)!=9521 or words[0]!=0x32443151 or words[1:17]!=[19008]*16:
  raise ValueError('native12 output header or size')
 data=struct.pack('<%dI'%len(words),*words);out=[]
 for row in range(99):
  for col in range(256):
   bit=(row*16+col%16)*12;offset=68+(col//16)*2376+bit//8
   v=(int.from_bytes(data[offset:offset+2],'little')>>(bit%8))&4095
   out.append(v-4096 if v&2048 else v)
 return out
