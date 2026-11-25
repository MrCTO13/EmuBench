# Emu Bench

Presented by Carts. A local-first command-line benchmark for macOS, Windows and Linux. It measures rendered frames from boot with neutral input for mGBA (Game Boy Advance) and Snes9x and bsnes (Super NES).

## Quick start

Download the matching archive from [Releases](https://github.com/MrCTO13/EmuBench/releases) and extract it. On macOS and Linux, run `chmod +x emubench` if your archive utility drops the executable bit. Use `./emubench` on macOS or Linux and `.\emubench.exe` in Windows PowerShell. The examples assume the executable is on your PATH.

```sh
emubench emulators
emubench download --all
emubench run --rom "My Game.gba" --latest-core --out my-run.json
emubench publish my-run.json --game "My Game" --preview
emubench publish my-run.json --game "My Game"
```

The release CLI can run all three supported measurement cores without a compiler. Download commands contact upstream directly and keep packages under your per-user downloads directory. The complete shortlist currently has 18 emulator projects. Automatic selection prefers a matching upstream desktop package and otherwise fetches the current Libretro Buildbot core. Use `download snes9x --channel core` to fetch the timing library explicitly. DuckStation offers a desktop download only. Each entry prints the package kind, build and local path. Keep that core path to repeat an exact build offline with `--core`. Desktop downloads are saved for manual installation. Check the upstream project's OS requirements when opening a desktop app.

    emubench download --all --list-only
    emubench download mgba --channel desktop --version 0.10.5
    emubench download --all --target windows-x64

The downloader checks transport length, validates the advertised package format and checks upstream SHA-256 when supplied. A core must match the published CRC and the selected native architecture. Content-addressed cache entries and local receipts preserve the acquired package. Upstream rebuilds can change what “latest” resolves to.

The optional `install mgba --version latest` command downloads the official tagged mGBA source and builds it locally. Install Git, CMake and a C/C++ toolchain first. Use Xcode Command Line Tools on macOS, Visual Studio Build Tools with Desktop development with C++ on Windows, or a C/C++ build toolchain on Linux. Each release is cached independently. A numeric version works offline after installation. The default reference is 0.10.5. To use the release CLI with an existing core and skip compilation, run `emubench run --core "/path/to/mgba_libretro.dylib" --rom "My Game.gba"`. Use a matching-architecture libretro library (.dll on Windows, .so on Linux). The desktop GUI executable uses a different interface.

From a source checkout with Python 3.10 or later, substitute `python -m emubench` for the executable. Source mode builds the measurement worker with CMake on first use. Set `EMUBENCH_HOME` to choose a private installation and results directory.

## Measurement

The default window is 120 warm-up frames followed by 1,800 measured frames. Change either with `--warmup-frames` or `--frames`. These are engineering defaults pending a duration and repeatability study. The native worker times software rendering with a monotonic host clock. It supplies neutral input and accepts audio without waiting for playback. The mGBA profile disables frame skipping, BIOS loading and idle-loop removal. The SNES profile uses each core's native software renderer and bundled defaults. bsnes run-ahead is disabled. Each timed advance must produce one non-null software framebuffer of the console's expected dimensions. The worker samples eight pixel locations and records an elapsed interval. The checks establish frame delivery. Game accuracy requires an independent reference trace.

Average FPS is the frame count divided by the total elapsed seconds. The 1% low is the reciprocal of the nearest-rank 99th-percentile frame time. The 1% high uses the 1st percentile. Both are expressed in FPS. Boot, attract screens and gameplay can have very different costs. Compare identical ROM revisions, frame windows, core binaries and hardware when drawing conclusions.

## Sharing

To upload new scores automatically from this device, sign in to GitHub once and enable uploads:

    gh auth login --hostname github.com
    emubench uploads enable
    emubench run --rom "/path/to/My Game.gba" --latest-core --game "My Game"
    emubench uploads status

Single runs, Carter scenes and campaign jobs save locally first. When uploads are enabled, each completed result queues a public summary for the existing GitHub scoreboard under your signed-in account. Carter scenes use their official titles. Personal runs use the public title you enter with `--game` or “Personal ROM”. Local filenames, cartridge data, ROM hashes, directories, raw frame timings and device logs stay on the machine. The public summary includes the emulator build, OS, CPU, whole-number FPS, a grouped timing curve and any diagnostic outcomes.

Offline runs keep measuring. Later runs and campaign iterations retry queued summaries with a delay after failures. Run `emubench uploads sync` to retry immediately, including after the last run of a campaign. The CLI must be running to send pending scores. `emubench uploads disable` stops new uploads and drops pending summaries. A request already in flight may finish. Previously completed private runs require a separate manual submission. Each score carries a run ID for reconciling retries.

A run saves a private JSON trace with frame times and ROM and build hashes. `publish --preview` shows exactly which fields may leave the machine. Publishing uses the GitHub CLI (`gh auth login`) to create a public, self-reported score in this repository under the submitting account. The optional display title defaults to “Personal ROM”. The public record omits the ROM, its filename, its hash, local paths and raw frame times. Manual publication requires interactive confirmation or explicit `--yes`. [Browse submitted scores](https://github.com/MrCTO13/EmuBench/issues?q=is%3Aissue%20in%3Atitle%20%22Score%22).

A random comparison token is assigned per exact ROM in the local device journal. Sharing it allows readers to link runs of that image from the same journal. Keep one journal per physical device. Published runs remain self-reported.

## Compare SNES emulators

    emubench run --rom "My Game.sfc" --emulator snes9x --latest-core --out snes9x.json
    emubench run --rom "My Game.sfc" --emulator bsnes --latest-core --out bsnes.json
    emubench compare snes9x.json bsnes.json --out comparison.html

Open the report, check the emulators to display, and use the FPS trace link to inspect dips. The same comparison view is available in the downloadable scores.html for published runs. It matches cartridge/device tokens, OS, architecture, processor, workload profile, worker hash, warm-up and measured frames. It displays every matching repeat separately and identifies selected emulators with no matching run. Reports created before v0.2 remain individually readable. SNES co-processor games that need external firmware require additional support. Commercial performance claims require representative gameplay and repeatability validation.

Desktop CI builds the native CLI and runs freshly generated GBA and SNES programs on each OS. This checks the measurement path. Reference-suite and commercial-game rankings require separate workloads and validation.

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

On Windows, Task Scheduler can invoke the same “campaign resume” command at logon. On Linux it can run as a user service. Campaigns use the device's automatic upload setting.

## Carter FPS and accuracy checks

    emubench carter --emulator mgba --rom "Carts-Cartervania-GBA.gba" --out-dir results
    emubench carter --emulator mgba --version 0.10.5 --scene hard --out-dir results
    emubench carter --emulator snes9x --scene hard --out-dir results
    emubench carter --emulator bsnes --scene hard --out-dir results
    emubench accuracy --emulator snes9x --refresh --out diagnostics.json
    emubench campaign create carter.sqlite --emulator mgba --carter all --loop --days 7
    emubench campaign resume carter.sqlite

With no ROM path, Carter mode uses the verified cached original or fetches the exact build from the game's private GitHub repository using your authenticated GitHub CLI. Locally supplied cartridges must match the pinned edition. The open-source CLI and its release archives contain only the runner, replay definitions and reference digests. Public upstream diagnostics work independently of Carter access.

| Console and game | Easy | Normal | Hard |
|---|---|---|---|
| GBA · Cartervania | Idle castle entrance | Three standing jumps | Move right, jump and dash |
| SNES · Super Carter Bros. 3 | Sunlit Shores map | Walk through Sunspill Orchard | Run, jump and dash through the orchard |

Each scene starts from power-on with clean temporary storage. A fixed controller replay reaches the scene, then the host times 180 rendered advances with audio enabled. The runner compares a full-frame hash at the end of setup and on a separate advance after timing against a pinned pair of software reference images (stored as digests). An unexpected image invalidates the scene score. A newer core can require review if its video output changes. The labels describe the work in the scene. Their ordering by host FPS can vary. These short windows are intended for repeatable engineering comparisons. Commercial gameplay coverage, agreement with original console output and minimum duration for marketing claims require separate validation.

The CLI also runs a versioned set of named upstream diagnostic programs with the same core and worker. It downloads pinned inputs into the local cache, verifies their SHA-256, runs them separately from FPS timing and reads the terminal message using a pattern derived from the upstream font and display position. Each program contributes one result. Pass, fail and unresolved are shown explicitly. The diagnostic total is a count of programs. It makes no estimate of how much of the console is emulated accurately. A standalone accuracy command returns a nonzero status for a failed or unresolved test. A Carter run retains its FPS and its diagnostic outcomes independently.

- GBA uses the ARM, Thumb and memory programs in [jsmolka/gba-tests at a7113b6](https://github.com/jsmolka/gba-tests/tree/a7113b67e63f83a9b321696ddd7042ccfad6c881). The current mGBA profile uses its built-in BIOS implementation.
- SNES uses the basic 65C816 instruction and SPC700 instruction ROMs from [gilyon/snes-tests v1.4](https://github.com/gilyon/snes-tests/releases/tag/v1.4). Graphics timing and enhancement chips such as Super FX are outside this diagnostic set.

Each saved Carter trace includes its scene, checkpoint digests and per-program outcomes. Use the existing compare, details, history and opt-in publish commands. Easy, normal and hard have different profile IDs so their results appear in separate comparison groups. The FPS command runs all three scenes by default. A campaign accepts the same named scene set with --carter.
