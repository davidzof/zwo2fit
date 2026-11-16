#!/usr/bin/env python3
"""Minimal ZWO to iGPSPORT-style FIT workout converter.

Built against an exported BSC300/iGPSPORT workout. Supports Warmup, Cooldown, Ramp, SteadyState/SolidState, IntervalsT,
FreeRide/Freeride, and MaxEffort. Ramps are segmented into 30s steps.
No proprietary cloud API needed. Requires Python standard library only.
"""
import argparse
import datetime
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

CRC_TABLE = (0x0000,0xCC01,0xD801,0x1400,0xF001,0x3C00,0x2800,0xE401,
             0xA001,0x6C00,0x7800,0xB401,0x5000,0x9C01,0x8801,0x4400)

def crc(data):
    value = 0
    for byte in data:
        tmp = CRC_TABLE[value & 15]
        value = (value >> 4) & 0x0fff
        value ^= tmp ^ CRC_TABLE[byte & 15]
        tmp = CRC_TABLE[value & 15]
        value = (value >> 4) & 0x0fff
        value ^= tmp ^ CRC_TABLE[(byte >> 4) & 15]
    return value

def definition(global_id, fields):
    return bytes([0x40,0,0]) + struct.pack('<HB',global_id,len(fields)) + b''.join(bytes(f) for f in fields)

def record(fields, values):
    result = bytearray([0])
    for fid,size,typ in fields:
        value=values[fid]
        if isinstance(value,str):
            encoded=value.encode('ascii','replace')[:size-1]
            result.extend((encoded+b'\0').ljust(size,b'\0'))
        elif size==1: result.extend(struct.pack('<B',value))
        elif size==2: result.extend(struct.pack('<H',value))
        elif size==4: result.extend(struct.pack('<I',value))
        else: raise ValueError((fid,size,typ))
    return bytes(result)

def parse_zwo(path,ftp,ramp_step):
    root=ET.parse(path).getroot()
    name=(root.findtext('name') or Path(path).stem).strip()
    sport=(root.findtext('sportType') or 'bike').strip().lower()
    if sport != 'bike': raise ValueError('Only bike workouts are supported')
    workout=root.find('workout')
    if workout is None: raise ValueError('No <workout> element')
    steps=[]
    def add(label,seconds,power,kind=0):
        if seconds<=0: raise ValueError('Step must have positive duration')
        if power is None:
            steps.append((label,round(seconds*1000),None,kind))
            return
        watts=round(power*ftp)
        if not 0<=watts<=1000: raise ValueError('Power outside supported range')
        steps.append((label,round(seconds*1000),watts,kind))
    def ramp(label,seconds,lo,hi,kind):
        if seconds<=0: raise ValueError('Ramp must have positive duration')
        import math
        count=math.ceil(seconds/ramp_step)
        for j in range(count):
            start=j*ramp_step; end=min(seconds,(j+1)*ramp_step)
            fraction=((start+end)/2)/seconds
            add(f'{label} {j+1}',end-start,lo+(hi-lo)*fraction,kind)
    for element in workout:
        tag=element.tag.split('}')[-1]
        a=element.attrib
        if tag in ('Warmup','Cooldown','Ramp'):
            # Zwift Cooldown is generally descending even when XML lists
            # PowerLow first, PowerHigh second. Ramp respects explicit order.
            low=float(a.get('PowerLow',a.get('Power',0)))
            high=float(a.get('PowerHigh',a.get('Power',0)))
            if tag=='Cooldown' and low<high:
                low,high=high,low
            ramp({'Warmup':'Warm','Cooldown':'Cool','Ramp':'Ramp'}[tag],
                 float(a['Duration']),low,high,
                 {'Warmup':2,'Cooldown':3,'Ramp':0}[tag])
        elif tag in ('SteadyState','SolidState'):
            power=float(a['Power']) if 'Power' in a else (
                float(a['PowerLow'])+float(a['PowerHigh']))/2
            add('Steady',float(a['Duration']),power)
        elif tag=='IntervalsT':
            for i in range(int(a['Repeat'])):
                add(f'Hard {i+1}',float(a['OnDuration']),float(a['OnPower']))
                add(f'Easy {i+1}',float(a['OffDuration']),float(a['OffPower']),1)
        elif tag in ('FreeRide','Freeride','MaxEffort'):
            # FIT target_type=0 means open/no target; important to avoid ERG
            # on a free-ride segment. Verify BSC300 behaviour on hardware.
            add('Free Ride' if tag!='MaxEffort' else 'Max Effort',
                float(a['Duration']),None,0)
        elif tag in ('textevent','TextEvent','TextNotification','gameplayevent'):
            # Coaching annotations are not workout steps.
            continue
        elif tag=='RestDay':
            raise ValueError('RestDay is not a timed cycling workout step')
        else:
            raise ValueError(f'Unsupported ZWO step: {tag}')
    return name,steps

def make_fit(name,steps):
    # File ID (global 0), matching native iGPSPORT profile field definitions.
    file_id=[(0,1,0),(1,2,132),(2,2,132),(3,4,140),(4,4,134)]
    workout=[(8,24,7),(6,2,132),(4,1,0)]
    step=[(5,4,134),(6,4,134),(21,4,134),(22,4,134),(254,2,132),
          (0,12,7),(1,1,0),(2,4,134),(3,1,0),(4,4,134),
          (19,1,0),(20,4,134),(7,1,0)]
    epoch=datetime.datetime(1989,12,31,tzinfo=datetime.timezone.utc)
    timestamp=int((datetime.datetime.now(datetime.timezone.utc)-epoch).total_seconds())
    body=bytearray()
    body += definition(0,file_id)
    body += record(file_id,{0:5,1:115,2:65534,3:0xffffffff,4:timestamp})
    body += definition(26,workout)
    body += record(workout,{8:name,6:len(steps),4:2})
    body += definition(27,step)
    for index,(label,duration,watts,kind) in enumerate(steps):
        is_free=watts is None
        body += record(step,{5:0xffffffff if is_free else 1000+watts,
                             6:0xffffffff if is_free else 1000+watts,
                             21:0xffffffff,22:0xffffffff,
                             254:index,0:label,1:0,2:duration,
                             3:0 if is_free else 4,4:0,19:0,20:0,7:kind})
    header=struct.pack('<BBHI4s',14,0x10,0x088d,len(body),b'.FIT')
    header+=struct.pack('<H',crc(header))
    payload=header+body
    return payload+struct.pack('<H',crc(payload))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zwo',type=Path)
    parser.add_argument('--ftp',type=int,required=True,help='FTP in watts (required)')
    parser.add_argument('--ramp-step',type=int,default=30,help='Ramp segment seconds (default 30)')
    parser.add_argument('--output','-o',type=Path)
    args=parser.parse_args()
    if args.ftp<=0 or args.ramp_step<=0: parser.error('ftp and ramp-step must be positive')
    name,steps=parse_zwo(args.zwo,args.ftp,args.ramp_step)
    out=args.output or args.zwo.with_suffix('.fit')
    out.write_bytes(make_fit(name,steps))
    print(f'{out}: {name}, {len(steps)} steps, {sum(s[1] for s in steps)/60000:.1f} min, FTP={args.ftp} W')
    for i,(label,ms,w,kind) in enumerate(steps,1): print(f'  {i:02d}: {label:12} {ms/1000:5.0f}s {str(w)+' W' if w is not None else 'open'}')

if __name__=='__main__': main()
