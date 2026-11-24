# Emu Bench

Presented by Carts. A local-first command-line benchmark for macOS, Windows and Linux. The first profile measures rendered mGBA Game Boy Advance frames from boot with neutral input.

## Quick start

Download the matching archive from [Releases](https://github.com/MrCTO13/EmuBench/releases) and extract it. On macOS and Linux, run `chmod +x emubench` if your archive utility drops the executable bit. Use `./emubench` on macOS or Linux and `.\emubench.exe` in Windows PowerShell. The examples assume the executable is on your PATH.

```sh
emubench versions mgba
emubench install mgba --version latest
emubench run --rom "My Game.gba" --version latest --out my-run.json
emubench publish my-run.json --game "My Game" --preview
emubench publish my-run.json --game "My Game"
```

The managed installer downloads the official tagged mGBA source and builds it locally. Install Git, CMake and a C/C++ toolchain first. Use Xcode Command Line Tools on macOS, Visual Studio Build Tools with Desktop development with C++ on Windows, or a C/C++ build toolchain on Linux. Each release is cached independently. A numeric version works offline after installation. The default reference is 0.10.5. To use the release CLI with an existing core and skip compilation, run `emubench run --core "/path/to/mgba_libretro.dylib" --rom "My Game.gba"`. Use a matching-architecture libretro library (.dll on Windows, .so on Linux). The desktop GUI executable uses a different interface.

From a source checkout with Python 3.10 or later, substitute `python -m emubench` for the executable. Source mode builds the measurement worker with CMake on first use. Set `EMUBENCH_HOME` to choose a private installation and results directory.

## Measurement

The default window is 120 warm-up frames followed by 1,800 measured frames. Change either with `--warmup-frames` or `--frames`. These are engineering defaults pending a duration and repeatability study. The native worker times software rendering with a monotonic host clock. It supplies neutral input, disables frame skipping, BIOS loading and idle-loop removal, and accepts audio without waiting for playback. For each timed advance it requires one non-null 240 × 160 video buffer, samples eight pixel locations, and records an elapsed interval. The checks establish frame delivery. Game accuracy requires an independent reference trace.

Average FPS is the frame count divided by the total elapsed seconds. The 1% low is the reciprocal of the nearest-rank 99th-percentile frame time. The 1% high uses the 1st percentile. Both are expressed in FPS. Boot, attract screens and gameplay can have very different costs. Compare identical ROM revisions, frame windows, core binaries and hardware when drawing conclusions.

## Sharing

A run saves a private JSON trace with frame times and ROM and build hashes. `publish --preview` shows exactly which fields may leave the machine. Publishing uses the GitHub CLI (`gh auth login`) to create a public, self-reported score in this repository under the submitting account. The optional display title defaults to “Personal GBA ROM”. The public record omits the ROM, its filename, its hash, local paths and raw frame times. Publication requires interactive confirmation or explicit `--yes`. [Browse submitted scores](https://github.com/MrCTO13/EmuBench/issues?q=is%3Aissue%20in%3Atitle%20%22Score%22).

Desktop CI builds the native CLI and runs a freshly generated GBA program on each OS. This checks the measurement path. Reference-suite and commercial-game rankings require separate workloads and validation.

## Device history and FPS dips

Each device keeps its own SQLite history under the EmuBench data directory. It records the local filename, chosen build, UTC start and finish, result location, scores and outcome. An attempt without a completion record remains visible as unfinished. Campaign attempts also record their round and job number.

    emubench history --game "Fusion"
    emubench details my-run.json --out my-run.html

Open the HTML file locally. The blue line shows average FPS per interval, and the orange points preserve each interval’s slowest individual frame. The inspector opens at the worst frame and shows its number, elapsed time and milliseconds. Published scores include this compact curve. Exact frame timings and device history stay local. The scores.html file in each desktop archive opens a searchable community board and reads public submissions from GitHub.

## Unattended campaigns

Create a queue once on the test device. Add additional files with repeated --rom arguments. Each device pins the selected core and hashes its own ROMs. Resume it whenever the device is available.

    emubench campaign create nightly.sqlite --rom "My Game.gba" --version 0.10.5 --loop --days 14
    emubench campaign resume nightly.sqlite
    emubench campaign status nightly.sqlite
    emubench campaign export nightly.sqlite --job 1 --out run-1.json

macOS waits for five minutes without HID input and checks host load before starting a job. Activity during a measurement discards the unfinished window. A trusted executable supplied via --idle-check can implement the device's own policy. It must return zero only while the host is idle and safe for measurement, including throughout the run. Windows, Linux and Graphite require that check or an explicit --dedicated reservation. Graphite needs a check that observes the launcher and controller before it can be used unattended during normal play.

By default the queue finishes one pass. --loop starts numbered rounds. --days limits elapsed time from the first resume. Three failed attempts place a job on hold. A targeted retry uses “campaign retry QUEUE --job ID”. Failures remain in the local journal. Less than 256 MiB free on the queue volume pauses new measurements. Private traces are retained until you archive them. The worker takes an OS measurement lock to prevent competing Emu Bench runs using the same data directory.

To resume after login on the test Mac, put the extracted CLI in its permanent location and generate a per-user launch agent. The command writes the plist. Loading it on the test machine starts the supervisor.

    emubench campaign launch-agent nightly.sqlite --out "$HOME/Library/LaunchAgents/org.emubench.nightly.plist"
    launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/org.emubench.nightly.plist"

On Windows, Task Scheduler can invoke the same “campaign resume” command at logon. On Linux it can run as a user service. Campaigns never publish automatically.
