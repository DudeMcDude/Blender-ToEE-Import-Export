import struct,zlib,sys,os,re
def entries(path):
    f=open(path,'rb'); d=f.read()
    _,_,_,dsz=struct.unpack('<16s4sII',d[-28:])
    p=len(d)-dsz; n,=struct.unpack_from('<I',d,p); p+=4
    names=[];parents=[]
    for _ in range(n):
        l,=struct.unpack_from('<I',d,p); p+=4
        name=d[p:p+l].rstrip(b'\0').decode('latin1'); p+=l
        unk,flags,real,comp,off,par,fc,ns=struct.unpack_from('<5I3i',d,p); p+=32
        names.append(name); parents.append(par)
        full=name; q=par
        while q>=0: full=names[q]+'/'+full; q=parents[q]
        yield full,flags,real,comp,off,d
if __name__=='__main__':
    pat=re.compile(sys.argv[2],re.I); out=sys.argv[3]
    for name,flags,real,comp,off,d in entries(sys.argv[1]):
        if flags&0x400 or not pat.search(name): continue
        b=d[off:off+comp]; b=zlib.decompress(b) if flags&2 else b
        o=os.path.join(out,name.replace('\\','/')); os.makedirs(os.path.dirname(o),exist_ok=True); open(o,'wb').write(b); print(name,len(b))
