"""Host hardware without installation identifiers, serial numbers or user paths."""
import ctypes
from functools import lru_cache
import json
import os
from pathlib import Path
import platform
import re
import sys
import psutil
from .telemetry import output, read


def windows_clusters():
    kernel=ctypes.windll.kernel32
    size=ctypes.c_uint32()
    kernel.GetLogicalProcessorInformationEx(0,None,ctypes.byref(size))
    if not 0<size.value<16*1024*1024:
        return {}
    buffer=ctypes.create_string_buffer(size.value)
    if not kernel.GetLogicalProcessorInformationEx(0,buffer,ctypes.byref(size)):
        return {}
    raw=buffer.raw
    counts={}
    pos=0
    while pos+10<=size.value:
        length=int.from_bytes(raw[pos+4:pos+8],"little")
        if length<10 or pos+length>size.value:
            return {}
        key=raw[pos+9]
        counts[key]=counts.get(key,0)+1
        pos+=length
    if len(counts)==2:
        return {"Efficiency":counts[min(counts)],"Performance":counts[max(counts)]}
    return {f"Efficiency class {k}":n for k,n in sorted(counts.items())}


def linux_clusters():
    capacities={}
    for cpu in Path("/sys/devices/system/cpu").glob("cpu[0-9]*"):
        capacity=read(cpu/"cpu_capacity")
        core=read(cpu/"topology/core_id")
        pkg=read(cpu/"topology/physical_package_id")
        if capacity.isdigit() and core and pkg:
            capacities.setdefault(int(capacity),set()).add((pkg,core))
    if len(capacities)==2:
        return {"Performance":len(capacities[max(capacities)]),"Efficiency":len(capacities[min(capacities)])}
    # Intel exposes CPU masks for its hybrid performance monitoring units.
    counts={}
    for pmu,label in (("cpu_core","Performance"),("cpu_atom","Efficiency")):
        physical=set()
        mask=read(Path("/sys/devices/devices")/pmu/"cpus") or read(Path("/sys/bus/event_source/devices")/pmu/"cpus")
        for token in mask.split(","):
            if not re.fullmatch(r"\d+(?:-\d+)?",token):
                continue
            lo,*hi=map(int,token.split("-"))
            for idx in range(lo,(hi[0] if hi else lo)+1):
                base=Path(f"/sys/devices/system/cpu/cpu{idx}/topology")
                physical.add((read(base/"physical_package_id"),read(base/"core_id")))
        if physical:
            counts[label]=len(physical)
    return counts


def linux_cpufreq():
    """Governor and frequency limits. The same SoC under another governor scores differently."""
    root=Path("/sys/devices/system/cpu")
    policies=sorted(root.glob("cpufreq/policy[0-9]*")) or sorted(root.glob("cpu[0-9]*/cpufreq"))
    found=[]
    for policy in policies:
        governor=read(policy/"scaling_governor")
        lo,hi=read(policy/"scaling_min_freq"),read(policy/"scaling_max_freq")
        if governor and lo.isdigit() and hi.isdigit():
            found.append({"governor":governor[:32],"min_khz":int(lo),"max_khz":int(hi)})
    unique=[dict(t) for t in dict.fromkeys(tuple(sorted(f.items())) for f in found)]
    return unique[:8]


def device_class(model, cpu, cores):
    """Normalized key so different installs on the same hardware group together.

    Example keys: "Apple M2 Pro / 12c", "Allwinner H700 / Anbernic RG35XX SP / 4c".
    """
    cpu=re.sub(r"\s+"," ",re.sub(r"\((?:R|TM)\)|CPU|Processor|@.*$","",cpu or "",flags=re.I)).strip()
    parts=[cpu or "Unknown CPU"]
    if model and sys.platform.startswith("linux") and model.lower() not in cpu.lower():
        parts.append(model)  # Device-tree board name for handhelds and SBCs.
    if cores:
        parts.append(f"{cores}c")
    return " / ".join(p[:80] for p in parts)[:160]


@lru_cache(maxsize=1)
def fingerprint():
    clusters={}
    gpu=[]
    model=""
    build=platform.release()
    if sys.platform=="darwin":
        def sysctl(name):
            return output(["/usr/sbin/sysctl","-n",name])
        model=sysctl("hw.model")
        build=sysctl("kern.osversion")
        levels=sysctl("hw.nperflevels")
        for i in range(int(levels) if levels.isdigit() else 0):
            prefix=f"hw.perflevel{i}."
            name=sysctl(prefix+"name")
            count=sysctl(prefix+"physicalcpu")
            if name and count.isdigit():
                clusters[name]=int(count)
        data=output(["/usr/sbin/system_profiler","SPDisplaysDataType","-json"])
        if data:
            gpu=[d["_name"] for d in json.loads(data).get("SPDisplaysDataType",[]) if d.get("_name")]
    elif os.name=="nt":
        build=str(sys.getwindowsversion().build)
        model=output(["powershell","-NoProfile","-NonInteractive","-Command","(Get-CimInstance Win32_ComputerSystem).Model"])
        gpu=output(["powershell","-NoProfile","-NonInteractive","-Command","(Get-CimInstance Win32_VideoController).Name"]).splitlines()
        clusters=windows_clusters()
    else:
        model=read("/sys/class/dmi/id/product_name") or read("/proc/device-tree/model").strip("\0")
        clusters=linux_clusters()
        pci=output(["lspci","-mm"])
        for line in pci.splitlines():
            values=re.findall(r'"([^"]*)"',line)
            if len(values)>=3 and re.search("VGA|3D controller|Display controller",values[0],re.I):
                gpu.append(values[1]+" "+values[2])
        if not gpu:
            for card in Path("/sys/class/drm").glob("card[0-9]*"):
                vendor,device=read(card/"device/vendor"),read(card/"device/device")
                if vendor and device:
                    gpu.append(vendor+":"+device)
    from .scores import cpu_model
    cores=psutil.cpu_count(logical=False)
    extra={"device_class":device_class(model,cpu_model(),cores)}
    if sys.platform.startswith("linux"):
        extra["cpufreq"]=linux_cpufreq()
    return {**extra,"model":model[:160] or None,"ram_bytes":psutil.virtual_memory().total,
            "os_build":build[:120],"physical_cores":psutil.cpu_count(logical=False),
            "core_types":clusters,"gpu":[name[:160] for name in dict.fromkeys(gpu)][:16]}
