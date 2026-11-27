# Emu Bench

A local-first command-line benchmark for macOS, Windows and Linux. It measures rendered frames from boot with neutral input for mGBA (Game Boy Advance) and Snes9x, bsnes and a locally supplied CartsSNES core (Super NES).

## Who runs EmuBench

EmuBench is built and run by Mr.CTO (GitHub account MrCTO13). The same person develops CARTS, a commercial emulator project that includes the CartsSNES core, and made the Carter homebrew games and Carter Circuit scenes used as official workloads. To keep that from tilting the results: the method and every workload are open source, every emulator runs in the same harness, CartsSNES is a closed build and is never ranked, and results where CARTS is slower are published the same way as results where it is faster.

## How a score is measured (single source of truth)

This section is the method. Where any other part of this README gives a different number, this section wins.

1. **Same harness for every emulator.** A small native libretro worker loads the core in its own process. No frame skipping, no audio device, no run-ahead. Each timed advance must produce exactly one software framebuffer.
2. **Only the emulator is timed.** Every 17th frame (at a random phase per run) is copied inside the video callback, the copy time is measured and subtracted, and the copy is hashed after `retro_run` returns. The harness's own checks never land in a frame time or the 1% low.
3. **At least 10 seconds per pass.** After warm-up the scene's frames are timed. If that took under 10 s, the worker restores a save state taken at the start of the scene and plays the same frames again, until at least 10 s of frames are timed. Every repeat must render identical sampled frames, or the scene is rejected.
4. **Three fresh processes per score**, with a 5 s cool-down between them. The pass with the median throughput is reported. All three must agree within **3%** (relative spread = (fastest − slowest) / median), every pass must be at least 10 s, and no pass may be reported hot (`serious`/`critical`) or throttled. Anything else stays local with the reason (`spread`, `short-window`, `hot`, `throttled`).
5. **Raw numbers on every run:** average FPS, 1% low FPS (99th percentile frame time), minimum FPS (slowest single frame), console speed (x real console) and the console's native target (60.10 NTSC SNES, 50.01 PAL SNES, 59.73 GBA).
6. **Device identity:** device class (CPU + board + core count), RAM, OS build, core types, GPU, Linux cpufreq governor and limits, observed CPU MHz, power source and low-power mode per pass.
7. **What gets ranked:** only *verified* builds (core SHA-256 listed in `emubench/verified_builds.json` after the lab matched it to an official upstream release or signed nightly), only within one device class and power state, only plugged in and idle. Custom builds are shown but never ranked. CartsSNES is closed, so it is shown as unreproducible and never ranked.
8. **Smoke checks are not an accuracy score.** The bundled upstream CPU/memory programs are smoke tests. Each shows pass, fail, unreadable or not run, and "not run" is never counted as a failure.

Result schema 2 carries all of the above. Schema 1 results (short windows, hashing inside the timed loop) are kept locally but are never published or compared with schema 2.

## EmuBench 1 score (draft)

`emubench score RESULTS...` turns saved Carter replay results into three separate numbers:

- **Device score**: pinned reference emulators (exact hashes) on your hardware. Per console, geometric mean over the suite scenes of (x-real-speed / reference x-real-speed) × 1000, then geometric mean over consoles. The reference device is 1000.
- **Emulator score**: `emubench score RESULTS... --baseline REFERENCE_RESULTS...` pairs an emulator with the reference emulator on the same machine, so the hardware cancels out. 1000 = as fast as the reference emulator.
- **Accuracy**: its own number, over every check that ran, failures included. A console only counts toward a speed score when every scene matched its frame-exact reference checkpoints and the emulator passes every pinned check that the console's reference emulator passes (`required_checks` in `emubench/reference_eb1.json`). A check the reference itself fails (for example Snes9x on "65C816 basic") does not block the speed score, but it still counts in the Accuracy number.
- **Playable %**: share of scenes at ≥ 1.0× with the 1% low at or above the native frame rate.

A headline is only given when every console in the suite scored; otherwise it reads "partial (n/m consoles)". The reference ladder lives in `emubench/reference_eb1.json` and is **not calibrated yet**: no Device score is produced until the lab measures the reference device (RG35XX SP class, H700, fixed governor, plugged in) and archives its binaries and traces. Carter Circuit stays out of EmuBench 1 as a synthetic PPU sub-score because its loops idle in a VBlank wait.

## Desktop app

The native Mac and Windows apps use the same measurement engine and on-device history as the CLI. Open EmuBench, pick a workload and emulator, then choose **Run benchmark**. The **History** tab opens frame charts and lets you publish a selected score. The first run downloads the emulator and its diagnostic files. Windows on Arm labels runs that use an x64 emulator. [Downloads and installation](https://emubench.games/download).

## Run the public suite

Download the archive for your OS and CPU. macOS, Windows and Linux each have an ARM64 and an x86-64 build. Open the executable with no arguments, or double-click **Open Emu Bench.command** on macOS. The local desktop launcher can run Carter Circuit or scan a ROM folder. After the first emulator download, the cached build and bundled Carter games work offline.

    emubench suite --emulator mgba
    emubench suite --emulator snes9x --scene hard --paced --checks
    emubench suite --emulator cartssnes --core "/path/to/cartssnes_libretro.dylib"
    emubench chips --emulator bsnes
    emubench catalog install snes
    emubench catalog match snes --rom "My Game.sfc"

Carter Circuit v2 has easy, normal and hard scenes on both GBA and SNES. The CLI builds the original code and graphics locally. Each scene times its 600 frames after 120 warm-up frames, repeated from a save state to at least 10 s (see the method above), and checks both boundary images. Each SNES suite also tests the SA-1 signed multiplier and a Super FX immediate register load. The optional paced pass uses the core’s declared refresh and audio sample rates. A missed deadline is a frame completed after its scheduled end. Missing audio sample frames count headless buffer starvation after an initial two-frame reserve. Physical display presentation and device audio are outside this measurement.

The public results browser supports game search, matched emulator and hardware comparisons, score timelines, campaign links, build history and matched SNES rankings. The browser explains coverage and the estimator used. Raw cartridge hashes, filenames, paths and frame logs stay local. Each upload includes a random installation token. Known editions can be shared across machines with `--share-title` after installing the catalog. Its public edition identifier derives from the catalog entry name. [Public scoreboard and methodology](https://emubench.games/method).

## Minimum-duration pilot

On a reserved idle host, run the command below per core and representative workload. The default trial randomizes 600, 1,800, 3,600 and 10,800 frame windows in each of eight independent cold-start blocks with the same warm-up. A report resumes when invoked again with identical parameters. Each candidate’s paired median ratio and 95% bootstrap interval must lie within ±1% for mean throughput and ±5% for each tail. Longer candidates must also pass. If any relevant workload, device or build is inconclusive, retain the reference duration there. A boot-only pilot applies to the boot sequence. Run separate Carter scenes and representative gameplay routes before generalizing to games, regions or enhancement chips.

    emubench calibrate --emulator snes9x --core "/path/to/core" --scene hard --dedicated --out pilot.json

## Quick start

Download the matching archive from [Releases](https://github.com/MrCTO13/EmuBench/releases) and extract it. On macOS and Linux, run `chmod +x emubench` if your archive utility drops the executable bit. Use `./emubench` on macOS or Linux and `.\emubench.exe` in Windows PowerShell. The examples assume the executable is on your PATH.

```sh
emubench emulators
emubench download --all
emubench run --rom "My Game.gba" --latest-core --out my-run.json
emubench publish my-run.json --game "My Game" --preview
emubench publish my-run.json --game "My Game"
```

Install an emulator once and select the cached build for offline use. Windows ARM64 builds the latest SNES cores from upstream with Git, GNU make and Zig. Other supported desktop targets can fetch the native SNES cores from Libretro Buildbot. Download commands contact upstream directly and keep packages under your per-user downloads directory. The complete shortlist currently has 18 emulator projects. The all-project downloader defaults to benchmark packages. For individual downloads, automatic selection prefers a matching upstream desktop package and otherwise fetches the current Libretro Buildbot core. Use `download snes9x --channel core` to fetch the timing library explicitly. DuckStation offers a desktop download only. Each entry prints the package kind, build and local path. Keep that core path to repeat an exact build offline with `--core`. Desktop downloads are saved for manual installation. Check the upstream project's OS requirements when opening a desktop app.

    emubench download --all --list-only
    emubench download mgba --channel desktop --version 0.10.5
    emubench download --all --target windows-x64

The downloader checks transport length, validates the advertised package format and checks upstream SHA-256 when supplied. A core must match the selected native architecture and upstream fingerprint. When a nightly file and its rolling CRC index disagree, EmuBench can verify the exact executable using Libretro’s signed SHA-256, matching filename and the pinned upstream production signer list. The resulting build uses the signed date and digest. If the macOS SNES nightly is inconsistent and the upstream server has no signature, the CLI can build its current pinned source with Xcode Command Line Tools. Content-addressed cache entries and local receipts preserve the acquired package. Upstream rebuilds can change what “latest” resolves to.

The optional `install mgba --version latest` command downloads the official tagged mGBA source and builds it locally. Install Git, CMake and a C/C++ toolchain first. Use Xcode Command Line Tools on macOS, Visual Studio Build Tools with Desktop development with C++ on Windows, or a C/C++ build toolchain on Linux. Each release is cached independently. A numeric version works offline after installation. The default reference is 0.10.5. To use the release CLI with an existing core and skip compilation, run `emubench run --core "/path/to/mgba_libretro.dylib" --rom "My Game.gba"`. Use a matching-architecture libretro library (.dll on Windows, .so on Linux). The desktop GUI executable uses a different interface.

From a source checkout with Python 3.10 or later, substitute `python -m emubench` for the executable. Source mode builds the measurement worker with CMake on first use. Set `EMUBENCH_HOME` to choose a private installation and results directory.

## Measurement

The default window is 120 warm-up frames followed by 1,800 measured frames. Change either with `--warmup-frames` or `--frames`. Every pass is also extended to at least 10 s of timed frames (see the method above). The native worker times software rendering with a monotonic host clock. It supplies neutral input and accepts audio without waiting for playback. The mGBA profile disables frame skipping, BIOS loading and idle-loop removal. The SNES profile uses each core's native software renderer and bundled defaults. bsnes run-ahead is disabled. Each timed advance must produce one non-null software framebuffer of the console's expected dimensions. The worker copies the full active pixel buffer every seventeenth frame (random phase) and hashes it outside the timed interval. The checks establish frame delivery. Game accuracy requires an independent reference trace.

Average FPS is the frame count divided by the total elapsed seconds. The 1% low is the reciprocal of the nearest-rank 99th-percentile frame time. The 1% high uses the 1st percentile. Both are expressed in FPS. Boot, attract screens and gameplay can have very different costs. Compare identical ROM revisions, frame windows, core binaries and hardware when drawing conclusions.

## Sharing

To upload new scores to the public service from this device, enable uploads. No account is required.

    emubench uploads enable
    emubench run --rom "/path/to/My Game.gba" --latest-core --game "My Game"
    emubench uploads status

Single runs, Carter scenes and campaign jobs save locally first. When uploads are enabled, each completed result queues a public summary for the selected scoreboard. Carter scenes use their official titles. Personal runs use the public title you enter with `--game` or “Personal ROM”. Local filenames, cartridge data, ROM hashes, directories, raw frame timings and device logs stay on the machine. The public summary includes the emulator build, OS, CPU, whole-number FPS, a grouped timing curve and any diagnostic outcomes.

Offline runs keep measuring. Later runs and campaign iterations retry queued summaries with a delay after failures. Run `emubench uploads sync` to retry immediately, including after the last run of a campaign. The CLI must be running to send pending scores. `emubench uploads disable` stops new uploads and drops pending summaries. A request already in flight may finish. Previously completed private runs require a separate manual submission. Each score carries a run ID for reconciling retries.

A run saves a private JSON trace with frame times and ROM and build hashes. `publish --preview` shows exactly which fields may leave the machine. The service authenticates an installation credential, verifies Ed25519 signatures on the measurement and submission, and applies submission limits and plausibility checks. The installation ID links its runs. These signatures identify the submitting installation; the scores and hardware remain self-reported. Use `--destination github` to publish a GitHub issue instead. Existing GitHub enrollments retain their original destination. The optional display title defaults to “Personal ROM”. The public record omits the ROM, its filename, its hash, local paths and raw frame times. Manual publication requires interactive confirmation or explicit `--yes`. [Browse submitted scores](https://emubench.games).

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

Point a campaign at a parent directory to benchmark a whole library, including subfolders. On an idle Mac with a signed-in GitHub CLI:

    emubench uploads enable
    emubench campaign create library.sqlite --rom-dir "/Volumes/Games/ROMs"
    emubench campaign resume library.sqlite --wait-uploads

The scanner matches GBA (`.gba`) to mGBA and SNES (`.sfc`, `.smc`) to both Snes9x and bsnes. It reads loose images and matching members of ZIP files. Supply `--emulator snes9x` or another supported core to narrow the scan. A folder campaign downloads and pins the current cores for the systems it finds. Add `--dedicated` when creating a queue on a reserved Windows or Linux machine, or supply its idle-check executable.

The queue snapshots the library at creation. Identical copies within a system share one run per emulator per round. Other formats, linked entries inside scanned folders, and macOS archive sidecars are skipped. Scan errors are printed locally. Resume the same queue after an interruption. Create a new one to include newly added games.

Automatic uploads share a summary for each completed measurement. Folder scores use the public title **Personal ROM** and an opaque per-device comparison ID. Paths, filenames, ZIP members and cartridge contents stay local. `--wait-uploads` keeps the process running after measurement until the device's pending summaries have been sent, including when connectivity returns. Ctrl-C and resume later to continue. Use `campaign status library.sqlite` for failed jobs and `uploads status` for pending submissions.

Create a queue once on the test device. Add additional files with repeated --rom arguments. For a looping public suite use `emubench campaign create suite.sqlite --circuit all --emulator all --carts-core "/path/to/cartssnes_libretro" --loop --days 14`. Each device pins the selected core and hashes its own ROMs. Resume it whenever the device is available.

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

Desktop downloads include 12 original Carter game editions for nine consoles in the games/roms folder. Run **emubench games list** to see the editions and benchmark coverage. **emubench games install** prints the verified ROM directory and fetches it anonymously when running from source. Cartervania (GBA) and Super Carter Bros. 3 (SNES) have pinned gameplay replays. Other supported editions use the local-ROM benchmark. Final Cartasy (N64) is included for play and has no timing adapter. The replay command also accepts a local pinned game with --rom. [Download the standalone Carter game pack](https://github.com/MrCTO13/EmuBench/releases/download/carter-games-v1/EmuBench-Carter-Games-v1.zip).

| Console and game | Easy | Normal | Hard |
|---|---|---|---|
| GBA · Cartervania | Idle castle entrance | Three standing jumps | Move right, jump and dash |
| SNES · Super Carter Bros. 3 | Sunlit Shores map | Walk through Sunspill Orchard | Run, jump and dash through the orchard |

Each scene starts from power-on with clean temporary storage. A fixed controller replay reaches the scene, then the host times 180 rendered advances with audio enabled, repeated from a save state to at least 10 s. The runner compares a full-frame hash at the end of setup and on a separate advance after timing against a pinned pair of software reference images (stored as digests). An unexpected image invalidates the scene score. A newer core can require review if its video output changes. The labels describe the work in the scene. Their ordering by host FPS can vary. These short windows are intended for repeatable engineering comparisons. Commercial gameplay coverage, agreement with original console output and minimum duration for marketing claims require separate validation.

The CLI also runs a versioned set of named upstream diagnostic programs with the same core and worker. It downloads pinned inputs into the local cache, verifies their SHA-256, runs them separately from FPS timing and reads the terminal message using a pattern derived from the upstream font and display position. Each program contributes one result. Pass, fail and unresolved are shown explicitly. The diagnostic total is a count of programs. It makes no estimate of how much of the console is emulated accurately. A standalone accuracy command returns a nonzero status for a failed or unresolved test. A Carter run retains its FPS and its diagnostic outcomes independently.

- GBA uses the ARM, Thumb and memory programs in [jsmolka/gba-tests at a7113b6](https://github.com/jsmolka/gba-tests/tree/a7113b67e63f83a9b321696ddd7042ccfad6c881). The current mGBA profile uses its built-in BIOS implementation.
- SNES uses the basic 65C816 instruction and SPC700 instruction ROMs from [gilyon/snes-tests v1.4](https://github.com/gilyon/snes-tests/releases/tag/v1.4). Graphics timing and enhancement chips such as Super FX are outside this diagnostic set.

Each saved Carter trace includes its scene, checkpoint digests and per-program outcomes. Use the existing compare, details, history and opt-in publish commands. Easy, normal and hard have different profile IDs so their results appear in separate comparison groups. The FPS command runs all three scenes by default. A campaign accepts the same named scene set with --carter.

## Game-library study design

Freeze the catalog revision, ROM editions, peer builds, viewport, region, audio settings, deterministic routes and failure criteria before timing. Use the same routes on each peer. Keep cold-boot throughput, routed gameplay, paced delivery and conformance in separate tables. A 50 Hz and a 60 Hz edition can have different workloads. Record region and frame count and compare matched editions. Report average and tail FPS as whole numbers.

For a console-wide gameplay claim, define the population and deduplicate regional revisions according to a published rule. Stratify ordinary titles by mapper or hardware family. List rare enhancement hardware ahead of time and include those cases deliberately. Draw randomly within strata with a published seed. Estimate the number of titles from the variability of paired log performance ratios in the pilot and a declared precision target. A fixed number of popular games alone cannot estimate the full library. Weight each stratum by its population for a library-wide estimate. A census removes title sampling uncertainty but still needs representative scenes, repeated-device checks and explicit coverage for failures. Report the fraction of eligible titles that completed and publish per-title rows alongside the estimate. The Carter synthetic score has its own fixed equal-scene weighting.

The live game coverage page lists candidate commercial titles and emulator projects per console. Current measurement adapters cover GBA and SNES. Other downloaded emulator packages need a validated timing adapter before they can produce scores.

## Multi-console benchmarking

`emubench emulators` lists the complete third-party shortlist and timing routes. Use `emubench download --all --channel bench` to prefetch the timing cores and the DuckStation desktop package. Use `--list-only` to inspect the selection first. Cross-platform snapshots depend on upstream availability. Windows on Arm uses native cores where available and an isolated x64 worker for x64-only builds. Public results identify translated runs.

    emubench bench "/path/to/ROMs" --queue library.sqlite --dedicated
    emubench campaign resume library.sqlite
    emubench run --emulator sameboy --rom "/path/to/game.gbc" --checks
    emubench accuracy --emulator gambatte
    emubench study list --console snes

Use `--dedicated` on a reserved machine, or pass `--idle-check PATH`. macOS can use its existing idle gate. Include your local CartsSNES with `--carts-core PATH`. The bench command downloads the compatible timing builds, pins their digests for the queue, and scans nested folders and cartridge ZIP members. A failed installation is recorded beside its jobs while working peers continue. Use a new queue to resolve a newer set of builds.

Supported routes include NES, SNES, GB, GBC, GBA, Master System, Game Gear, Mega Drive/Genesis, 32X, Atari 2600, PC Engine, SuperGrafx, PlayStation and arcade. Use unambiguous cartridge extensions. For a single-file PC Engine CD CHD select `--emulator beetle-pce-fast`. Linux ARM64 builds SameBoy from its upstream release with Git, make and a C compiler when a native download is unavailable. For PlayStation CHD/PBP/PS-X EXE select `--emulator pcsx-rearmed`. For arcade set ZIPs select `--emulator arcade` in bench or a single arcade peer. Use complete non-merged sets. Point `--system-dir` at locally supplied firmware when needed. Timing requires a completed software framebuffer per measured frame. Incomplete measurements and emulator startup errors do not earn scores.

DuckStation has a separate measurement protocol. The desktop downloader covers it; its upstream regression executable can be supplied with `emubench duckstation --runner PATH --rom IMAGE --system-dir BIOS_DIR`. The local report stores its average FPS and counts rendered checkpoints. Signed DuckStation scores with moving checkpoints can be published to a separate standalone cohort. Standalone details show total process time and leave per-frame percentiles unavailable. It may need to be built separately from the upstream project.

See the [frozen samples, verified rankings and accuracy evidence](STUDIES.md).

### Console speed

The primary unit is × real time. EmuBench divides the unrounded rendered frame rate by the loaded game's refresh rate. The libretro harness records the region and AV timing after warm-up (including fractional PAL and NTSC rates). Game Boy, Color and Advance use the LCD clock, 4,194,304 / 70,224 Hz. Frame-rate percentiles remain available in whole FPS. Historical records without a video mode have no normalized score. The denominator for variable video modes is the timing reported by that build at the start of the measured window.

### Standalone executables

Use the mgba-perf or duckstation subcommand with --runner PATH and --rom PATH. DuckStation also needs --system-dir BIOS_DIR. Select the upstream mGBA profiler (CMake BUILD_PERF=ON) or DuckStation regression runner. Both run headless in software. The harness measures launch through exit, including startup and checkpoint I/O. The receipt is kept on the device. mGBA reports the renderer and frame count. Its profiler does not expose framebuffer pixels. Standalone aggregate scores have a distinct protocol and no frame-time percentiles. The upstream bsnes desktop target lacks a headless fixed-frame interface. Its libretro route remains available.

Carter Circuit v2 adds 64 translucent objects on GBA and four layers with pseudo-hires color math on SNES. Hard must run at least 10% slower than normal in the three-pass workload check on mGBA, Snes9x and bsnes. Run tests/scene_load.py with an emulator ID and core path. Revisions use separate comparison groups. A CartsSNES build that misses a reference checkpoint records a failed scene.

Every scored run samples aggregate CPU use for 350 ms before timing. At 25% utilization or higher the run is flagged busy and excluded from rankings. Campaigns additionally monitor their configured idle gate. This preflight measures CPU contention; it does not assert exclusive physical access.

One score now starts three fresh emulator processes. We select the pass with median unrounded throughput and show its trace and whole-number FPS. Relative spread = (fastest − slowest) / median. Spreads above 3%, passes under 10 s and hot or throttled passes are stored locally and rejected for public scoring. Each local receipt includes all three measured durations. The same rule applies to standalone process timing.

Speed listings identify diagnostic coverage. SNES ranking eligibility requires both upstream CPU/audio programs and all three coprocessor probes to pass on the measured build. A missing, failed or unresolved check withholds the ranking while the individual result stays visible. These are named test outcomes, not a percentage of compatibility with the game library.

### Scoreboard domain

The score browser and signed upload service are at [emubench.games](https://emubench.games). The CLI verifies TLS and requires the receipt URL to match the service origin. Reports link to the same domain.
