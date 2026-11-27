"""Measure host load before launching the emulator, outside the score window."""
import psutil


def idle():
    utilization = psutil.cpu_percent(interval=0.35)
    return {"cpu_percent":utilization, "state":"busy" if utilization>=25 else "idle"}
