"""Small dependency-free FIT record reader for running performance streams.

Reads standard FIT record message (global 20). Advanced developer fields are ignored.
Malformed FIT files are rejected or yield no points; original ZIP remains the source.
"""
from __future__ import annotations
import struct
from datetime import datetime, timezone, timedelta
from io import BytesIO
import zipfile

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc).timestamp()
FORMATS = {0x00:'B',0x01:'b',0x02:'B',0x83:'h',0x84:'H',0x85:'i',0x86:'I',0x88:'f',0x89:'d',0x0a:'B',0x8b:'H',0x8c:'I',0x0d:'s',0x8e:'q',0x8f:'Q',0x10:'Q'}
SIZES = {'B':1,'b':1,'h':2,'H':2,'i':4,'I':4,'f':4,'d':8,'s':1,'q':8,'Q':8}


def _field_value(blob, typ, endian):
    fmt = FORMATS.get(typ & 0x9f)
    if not fmt or not blob or len(blob) % SIZES[fmt]: return None
    if fmt=='s':
        return blob.split(b'\0',1)[0].decode('utf-8','replace')
    try:
        vals = struct.unpack(endian + fmt*(len(blob)//SIZES[fmt]), blob)
    except (ValueError, struct.error): return None
    v = vals[0]
    # FIT invalid values are usually max unsigned / max positive signed.
    if isinstance(v, int):
        maximum=(2 ** (8*SIZES[fmt]-1)-1 if fmt in 'bhiq' else 2**(8*SIZES[fmt])-1)
        if v == maximum: return None
    return v


def parse_fit(data: bytes) -> list[dict]:
    if len(data)<14 or data[8:12]!=b'.FIT': raise ValueError('Not a valid FIT file')
    header_size=data[0]
    if header_size not in (12,14): raise ValueError('Invalid FIT header size')
    length=struct.unpack_from('<I',data,4)[0]
    if header_size+length>len(data): raise ValueError('FIT data is truncated')
    p=header_size; end=p+length; definitions={}; records=[]; last_ts=None
    while p<end:
        header=data[p]; p+=1
        compressed=bool(header & 0x80)
        local=(header >> 5) & 3 if compressed else header & 0x0f
        if not compressed and header & 0x40:
            if p+5>end: break
            reserved, arch, global_num, count = struct.unpack_from('<BBHB',data,p) if data[p+1]==0 else (None,None,None,None)
            if arch is None:
                reserved=data[p]; arch=data[p+1]; global_num=struct.unpack_from('>H',data,p+2)[0]; count=data[p+4]
            p+=5
            fields=[]
            for _ in range(count):
                if p+3>end: return records
                fields.append(tuple(data[p:p+3])); p+=3
            if header & 0x20:
                if p>=end: break
                developer_count=data[p]; p+=1+3*developer_count
            definitions[local]=(global_num,'<' if arch==0 else '>',fields)
            continue
        if local not in definitions: raise ValueError('Undefined FIT local message')
        global_num,endian,fields=definitions[local]; values={}
        for num,size,typ in fields:
            if p+size>end: return records
            raw=data[p:p+size]; p+=size
            if global_num==20 and num in (0,1,2,3,4,5,6,73,78,253):
                values[num]=_field_value(raw,typ,endian)
        if compressed:
            offset=header & 0x1f
            if last_ts is not None:
                ts=(int(last_ts)&~0x1f)|offset
                if ts<last_ts: ts+=0x20
                values.setdefault(253,ts)
        if values.get(253) is not None: last_ts=values[253]
        if global_num != 20: continue
        t=values.get(253); d=values.get(5)
        if t is None or d is None: continue
        hr=values.get(3)
        altitude=values.get(78)
        if altitude is not None: altitude=altitude/5-500
        elif values.get(2) is not None: altitude=values[2]/5-500
        records.append({'t':round(FIT_EPOCH + t,2),'d':round(d/100,2),'hr':int(hr) if hr is not None else None,'alt':round(altitude,1) if altitude is not None else None})
    return records


def parse_activity_archive(data: bytes) -> list[dict]:
    if data[:2] == b'PK':
        with zipfile.ZipFile(BytesIO(data)) as z:
            fit_names=[x for x in z.namelist() if x.lower().endswith('.fit') and not x.startswith('__MACOSX')]
            if not fit_names: raise ValueError('Archive contains no FIT file')
            info=z.getinfo(fit_names[0])
            if info.file_size > 80_000_000: raise ValueError('Uncompressed FIT file exceeds safety limit')
            return parse_fit(z.read(fit_names[0]))
    return parse_fit(data)


def split_stream(points: list[dict]) -> list[list[dict]]:
    """Split at recording discontinuities and physically impossible spikes."""
    segments=[]; current=[]
    for p in points:
        if current:
            prev=current[-1]; dt=p['t']-prev['t']; dd=p['d']-prev['d']
            if dt<=0 or dt>180 or dd<-.5 or (dt>0 and dd/dt>10.0):
                if len(current)>1: segments.append(current)
                current=[]
        current.append(p)
    if len(current)>1: segments.append(current)
    return segments


def fastest_effort(points: list[dict], target_m: float):
    """Fastest timestamp-interpolated moving-distance segment, scored by elapsed time.
    Pauses (180s+) and GPS spikes split the activity; no cross-gap interpolation.
    """
    best=None
    for segment in split_stream(points):
        if segment[-1]['d']-segment[0]['d']<target_m: continue
        # For every right endpoint, interpolate left when distance crosses the target.
        left=0
        for right in range(1,len(segment)):
            end_d=segment[right]['d']; need=end_d-target_m
            if need<segment[0]['d']: continue
            while left+1<right and segment[left+1]['d']<=need: left+=1
            a=segment[left]; b=segment[left+1]
            if b['d']<=a['d']: continue
            frac=(need-a['d'])/(b['d']-a['d'])
            start_t=a['t']+frac*(b['t']-a['t'])
            duration=segment[right]['t']-start_t
            if duration<=0: continue
            if best is None or duration<best['seconds']:
                best={'seconds':round(duration,2),'start_t':round(start_t,2),'end_t':segment[right]['t'],'kind':'recorded_segment'}
    return best


def time_in_zones(points, zones):
    distribution=[0.0]*5
    for segment in split_stream(points):
        for a,b in zip(segment,segment[1:]):
            dt=b['t']-a['t']
            if dt<=0 or dt>30 or a['hr'] is None or a['hr']<35 or a['hr']>245: continue
            for i,z in enumerate(zones):
                if z['low']<=a['hr']<=z['high']:
                    distribution[i]+=dt; break
    return [round(x) for x in distribution]
