"""Public, non-identifying measurements from the host OS. Missing readings stay null."""
import ctypes
import os
from pathlib import Path
import re
import subprocess
import sys
import psutil


def output(command):
    try:
        return subprocess.check_output(command, text=True, timeout=5, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return ""


def read(path):
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeError):
        return ""


def mac_power(result):
    from ctypes import c_char_p, c_void_p, c_long
    ctypes.CDLL("/System/Library/Frameworks/Foundation.framework/Foundation")
    objc=ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.objc_getClass.argtypes=[c_char_p]
    objc.objc_getClass.restype=c_void_p
    objc.sel_registerName.argtypes=[c_char_p]
    objc.sel_registerName.restype=c_void_p
    getter=ctypes.CFUNCTYPE(c_void_p,c_void_p,c_void_p)(("objc_msgSend",objc))
    integer=ctypes.CFUNCTYPE(c_long,c_void_p,c_void_p)(("objc_msgSend",objc))
    info=getter(objc.objc_getClass(b"NSProcessInfo"),objc.sel_registerName(b"processInfo"))
    if info:
        result["thermal_state"]={0:"nominal",1:"fair",2:"serious",3:"critical"}.get(integer(info,objc.sel_registerName(b"thermalState")))
        selector=objc.sel_registerName(b"isLowPowerModeEnabled")
        responds=ctypes.CFUNCTYPE(ctypes.c_bool,c_void_p,c_void_p,c_void_p)(("objc_msgSend",objc))
        if responds(info,objc.sel_registerName(b"respondsToSelector:"),selector):
            result["low_power"]=bool(integer(info,selector)&255)
    power=output(["/usr/bin/pmset","-g","batt"]).splitlines()
    if power:
        result["power_source"]="ac" if "AC Power" in power[0] else "battery" if "Battery Power" in power[0] else None
    limit=re.search(r"CPU_Speed_Limit\s*=\s*(\d+)",output(["/usr/bin/pmset","-g","therm"]))
    if limit:
        result["throttled"]=int(limit[1])<100


def snapshot():
    result=dict(thermal_state=None,temperature_c=None,throttled=None,throttle_count=None,power_source=None,low_power=None)
    if sys.platform=="darwin":
        mac_power(result)
    elif os.name=="nt":
        class Status(ctypes.Structure):
            _fields_=[("ac",ctypes.c_ubyte),("flags",ctypes.c_ubyte),("percent",ctypes.c_ubyte),
                      ("saving",ctypes.c_ubyte),("remaining",ctypes.c_uint32),("full",ctypes.c_uint32)]
        status=Status()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            result.update(power_source={0:"battery",1:"ac"}.get(status.ac),low_power={0:False,1:True}.get(status.saving))
    else:
        battery=psutil.sensors_battery()
        if battery and battery.power_plugged is not None:
            result["power_source"]="ac" if battery.power_plugged else "battery"
        supplies=Path("/sys/class/power_supply")
        if any(read(p/"type") in ("Mains","USB","USB_C") and read(p/"online")=="1" for p in supplies.glob("*")):
            result["power_source"]="ac"
        temps=psutil.sensors_temperatures() if hasattr(psutil,"sensors_temperatures") else {}
        cpu=[entry.current for name,entries in temps.items() if name in ("coretemp","k10temp","cpu_thermal","zenpower")
             for entry in entries if entry.current is not None and -40<=entry.current<=150]
        if cpu:
            result["temperature_c"]=round(max(cpu),1)
        counts=[read(p) for p in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/thermal_throttle/core_throttle_count")]
        if counts and all(c.isdigit() for c in counts):
            result["throttle_count"]=sum(map(int,counts))
        profile=read("/sys/firmware/acpi/platform_profile")
        if profile:
            result["low_power"]=profile in ("low-power","quiet")
    return result


def window(before):
    after=snapshot()
    if before["throttle_count"] is not None and after["throttle_count"] is not None:
        after["throttled"]=after["throttle_count"]>before["throttle_count"]
    return {"before":before,"after":after}
