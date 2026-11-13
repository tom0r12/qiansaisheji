"""Independent signed integer Q12/12/13 arithmetic, without learned parameters."""
import numpy as np

def requantize(acc, shifts):
    acc=np.asarray(acc,dtype=np.int64); shifts=np.asarray(shifts,dtype=np.int64)
    if np.any((shifts<0)|(shifts>47)):raise ValueError('shift range')
    magnitude=np.abs(acc); quotient=magnitude>>shifts
    remainder=magnitude&((np.int64(1)<<shifts)-1)
    half=np.int64(1)<<np.maximum(shifts-1,0)
    increment=(shifts>0)&((remainder>half)|((remainder==half)&((quotient&1)!=0)))
    result=np.where(acc<0,-(quotient+increment),quotient+increment)
    return np.clip(result,-4096,4095).astype(np.int64)

def direct(x,w,bias,shifts):
    x=np.asarray(x,dtype=np.int64);w=np.asarray(w,dtype=np.int64);bias=np.asarray(bias,dtype=np.int64)
    if x.shape!=(99,64)or w.shape!=(64,256)or bias.shape!=(256,):raise ValueError('shape')
    if any(np.any((v<-2048)|(v>2047))for v in[x,w]):raise ValueError('X/W signed12')
    if np.any((bias<-(1<<21))|(bias>=(1<<21))):raise ValueError('bias22')
    acc=x@w+bias
    if np.any((acc<-(1<<31))|(acc>=(1<<31))):raise ValueError('corrected32 overflow')
    return requantize(acc,shifts)

def pair_identity(x,w,bias):
    """Exact factorized identity and per-stage width guards, not RTL simulation."""
    x=np.asarray(x,dtype=np.int64);w=np.asarray(w,dtype=np.int64)
    raw=np.zeros((len(x),w.shape[1]),dtype=np.int64)
    row=np.sum(x[:,0::2]*x[:,1::2],axis=1)
    col=np.sum(w[0::2,:]*w[1::2,:],axis=0)
    for k in range(0,64,2):
        term=(x[:,k,None]+w[k+1,None,:])*(x[:,k+1,None]+w[k,None,:])
        if np.any((term<-(1<<25))|(term>=(1<<25))):raise AssertionError('product26')
        raw+=term
        if np.any((raw<-(1<<30))|(raw>=(1<<30))):raise AssertionError('raw31')
    for v in[row,col]:
        if np.any((v<-(1<<28))|(v>=(1<<28))):raise AssertionError('factor29')
    corrected=raw-row[:,None]-col[None,:]+bias
    if not np.array_equal(corrected,x@w+bias):raise AssertionError('factor identity')
    if np.any((corrected<-(1<<31))|(corrected>=(1<<31))):raise AssertionError('corrected32')
    return corrected
