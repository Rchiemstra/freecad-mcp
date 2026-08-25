from __future__ import annotations
import hashlib
Q=2**255-19;D=(-121665*pow(121666,Q-2,Q))%Q;L=2**252+27742317777372353535851937790883648493;B=(15112221349535400772501151409588531511454012693041857206046113283949847762202,46316835694926478169428394003475163141307993866256225615783033603165251855960)
def _a(a,b):
 x,y=a;u,v=b;c=(x*v+y*u)%Q;d=(y*v+x*u)%Q;return c*pow(1+D*x*u*y*v,Q-2,Q)%Q,d*pow(1-D*x*u*y*v,Q-2,Q)%Q
def _m(p,n):
 r=(0,1)
 while n:
  if n&1:r=_a(r,p)
  p=_a(p,p);n>>=1
 return r
def _e(p):
 x,y=p;return (y|((x&1)<<255)).to_bytes(32,"little")
def sign(message:bytes,seed:bytes=bytes(range(32))):
 d=hashlib.sha512(seed).digest();a=(int.from_bytes(d[:32],"little")&((1<<254)-8))|(1<<254);public=_e(_m(B,a));r=int.from_bytes(hashlib.sha512(d[32:]+message).digest(),"little")%L;encoded=_e(_m(B,r));k=int.from_bytes(hashlib.sha512(encoded+public+message).digest(),"little")%L
 return public,encoded+((r+k*a)%L).to_bytes(32,"little")
