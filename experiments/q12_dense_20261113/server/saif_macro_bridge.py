"""Lossless SRAM activity hierarchy bridge; no toggle or duration editing.

Only escaped generate spelling and '] .' versus '] /' hierarchy spelling
(without the spaces) are normalized for matching. Ambiguity is fatal.
"""
import hashlib,re

TOKENS=re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+')

def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def canonical(name):return name.replace('\\','').replace('].',']/')

def instance_spans(text):
 stack=[];path=[];spans={};first=None
 for m in TOKENS.finditer(text):
  token=m.group()
  if token=='(':
   stack.append({'start':m.start(),'kind':None,'name':None})
  elif token==')':
   if not stack:raise ValueError('Unbalanced SAIF close')
   frame=stack.pop()
   if frame['kind']=='INSTANCE':
    if frame['name']is None:raise ValueError('Unnamed instance')
    key='/'.join(path)
    if key in spans:raise ValueError('Duplicate SAIF instance '+key)
    spans[key]=(frame['body_start'],m.start())
    path.pop()
  else:
   if not stack:raise ValueError('SAIF token outside root')
   frame=stack[-1]
   if frame['kind']is None:frame['kind']=token
   elif frame['kind']=='INSTANCE'and frame['name']is None:
    name=token[1:-1]if token.startswith('"')else token
    frame['name']=name;frame['body_start']=m.end();path.append(name)
    if first is None:first=frame['start']
 if stack or path:raise ValueError('Unbalanced SAIF end')
 if first is None:raise ValueError('No SAIF instances')
 return spans,first

def encode_name(name):
 name=name.replace('\\','')
 if not re.fullmatch(r'[A-Za-z0-9_.$\[\]-]+',name):raise ValueError('Unexpected mapped identifier '+name)
 return name.replace('[','\\[').replace(']','\\]')

def build_macro_overlay(text,macro_rows,scope='tb_q12soc/dut'):
 spans,first=instance_spans(text);lookup={}
 for name in spans:lookup.setdefault(canonical(name),[]).append(name)
 original_merger=scope+'/u_e203_subsys_top/u_e203_subsys_main/u_mem_merge/u_original'
 if len(lookup.get(canonical(original_merger),[]))!=1:raise ValueError('Original System Bus merger activity missing')
 root={};mapping=[];seen=set()
 for target,ref,_lib in macro_rows:
  key=scope+'/'+target;matches=lookup.get(canonical(key),[])
  if len(matches)!=1:raise ValueError('Missing/ambiguous macro activity '+key+' '+repr(matches))
  source=matches[0]
  if source in seen:raise ValueError('Two mapped macros reuse source activity')
  seen.add(source)
  a,b=spans[source];body=text[a:b]
  entry=root
  parts=key.split('/')
  for part in parts:
   if '__body__'in entry:raise ValueError('Macro hierarchy collision')
   entry=entry.setdefault(part,{})
  if entry:raise ValueError('Duplicate or parent macro target')
  entry['__body__']=body
  mapping.append({'mapped_instance':target,'reference':ref,'saif_instance':source,
                  'raw_body_sha256':sha_bytes(body.encode())})
 def render(tree,level=0):
  output=[]
  for name,value in tree.items():
   if name=='__body__':raise ValueError('Unexpected body at branch')
   output.append(' '*level+'(INSTANCE '+encode_name(name))
   if '__body__'in value:output.append(value['__body__'])
   else:output.append('\n'+render(value,level+1))
   output.append(')\n')
  return ''.join(output)
 overlay=text[:first]+render(root)+')\n'
 check,_=instance_spans(overlay)
 checked={canonical(k):v for k,v in check.items()}
 for item in mapping:
  a,b=checked[canonical(scope+'/'+item['mapped_instance'])]
  if sha_bytes(overlay[a:b].encode())!=item['raw_body_sha256']:raise ValueError('Activity body changed during remapping')
 return overlay,{'macro_count':len(mapping),'mapping':mapping,'original_merger_path':original_merger,
                 'original_sha256':sha_bytes(text.encode()),'overlay_sha256':sha_bytes(overlay.encode()),
                 'changed_activity_values':False,'scope':'Only hierarchy containers changed; raw SRAM activity bodies retained byte-for-byte'}
