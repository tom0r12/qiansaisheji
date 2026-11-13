"""Independent, standard-library-only wire output checker (signed Y13, Rice7)."""
def decode_output(words):
    if len(words)!=10353 or words[0]!=0x31593151:
        raise ValueError('output header/allocation')
    result=[0]*(99*256)
    for tile,nbits in enumerate(words[1:17]):
        if not 0<nbits<=1584*13+50:raise ValueError('output bit count')
        start=17+tile*646;nwords=(nbits+31)//32
        if any(w!=0xcccccccc for w in words[start+nwords:start+646]):
            raise ValueError('unused slot modified')
        payload=b''.join(w.to_bytes(4,'little')for w in words[start:start+nwords])
        bits=''.join(format(b,'08b')for b in payload)
        if '1' in bits[nbits:]:raise ValueError('nonzero output padding')
        bits=bits[:nbits];pos=0;values=[]
        def get(n):
            nonlocal pos
            if pos+n>nbits:raise ValueError('truncated output')
            value=int(bits[pos:pos+n],2) if n else 0;pos+=n
            return value
        while len(values)<1584:
            raw=get(1);n=min(32,1584-len(values));block=[];cost=0
            for _ in range(n):
                if raw:
                    value=get(13);signed=value-8192 if value&4096 else value
                    zigzag=-2*signed-1 if signed<0 else 2*signed
                else:
                    end=bits.find('0',pos)
                    if end<0 or end-pos>63:raise ValueError('invalid unary output')
                    q=end-pos;pos=end+1;zigzag=(q<<7)|get(7)
                    signed=-(zigzag+1)//2 if zigzag&1 else zigzag//2
                    value=signed&8191
                block.append(value);cost+=(zigzag>>7)+8
            if bool(raw)!=(cost>=13*n):raise ValueError('noncanonical output block')
            values.extend(block)
        if pos!=nbits:raise ValueError('trailing output bits')
        previous=[0]*16
        for n,value in enumerate(values):
            col=n%16;row=n//16
            previous[col]=(previous[col]+value)&8191
            signed=previous[col]-8192 if previous[col]&4096 else previous[col]
            result[row*256+tile*16+col]=signed
    return result
