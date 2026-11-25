# Controlled lab rankings

The SNES and GBA studies each draw 24 base USA editions from a pinned public No-Intro catalog. The [frozen manifest](emubench/studies.json) lists the eligible population size, every selected game, its edition identifier, and its cartridge-size group. Only single-image entries whose title ends in a single “(USA)” and matches the image name qualify. This excludes revisions with additional qualifiers, imports and many multi-region editions.

The [selection program](tools/freeze_sample.py) sorts eligible entries by image size, breaking ties by title. It divides that list into four equal-count groups, then takes the six lowest SHA-256 ranks in each group using a public versioned seed and the exact catalog title. Size stratification spreads the sample across cartridge capacities. Special-chip and other diagnostic results are reported separately. The 24-game sample is a first preregistered study, and its precision still needs a physical pilot.

Each edition gets 120 warm-up frames followed by 1,800 measured boot frames without controller input. The study measures boot and attract-mode throughput. Its score does not estimate interactive gameplay across a console's entire library. A change in window, cohort or workload requires a new study ID. The ranking takes a geometric mean of average FPS across games in each size group and weights each group's log mean by its share of the eligible population. Each table also shows per-game whole-number average, 1% low and 1% high FPS. Every peer must complete every edition on the same hardware, timing worker and pinned build. Missing games, duplicate cells, unresolved failures and mixed timing windows withhold the aggregate.

## Run and review

1. Use `emubench study list --console snes` to see the games, then install the matching edition catalog with `emubench catalog install snes`.
2. Point `emubench bench /path/to/selected-games --queue lab.sqlite --dedicated` at the local editions on a reserved host. An idle check can replace the dedicated setting. Use one directory per console. Enable score uploads separately to share individual run pages.
3. Run `emubench study review --console snes --queue lab.sqlite --out review.json`. The CLI checks the full first round, recomputes FPS from local frame traces, and writes a public-field receipt. Local paths, ROMs, raw frame traces, firmware and device logs stay on the machine.
4. A maintainer who controlled or witnessed the run checks its hardware, power configuration, idle conditions, matching settings, software versions, lack of selective retries and score traces. Record the review in the project history and include the public receipt under `site/reviewed/` only after signoff. Publishing a new website version admits that receipt to the lab board. A public submission cannot grant itself lab status. A digest or local receipt alone cannot establish who controlled the host.

## Accuracy evidence

CGB graphics use Matt Currie's [cgb-acid2 v1.1](https://github.com/mattcurrie/cgb-acid2/tree/v1.1), whose author provides an expected image and a photograph of a real unit. Emu Bench checks every pixel's color grouping across the 160 × 144 image, allowing display color correction. The test exercises scanline interrupts, windows, sprite limits and priority. It does not check exact display colors or every mode-3 timing edge.

Five independent CGB APU probes read the terminal verdict from [Blargg's CGB sound tests](https://github.com/retrio/gb-test-roms/tree/c240dd7d700e5c0b00a7bbba52b53e4ee67b5f15/cgb_sound). These check CPU-observable sound hardware behavior. They do not compare an analog recording. Program digests and the author's font-derived pass/fail masks are pinned. An unrecognized or unfinished screen yields “unresolved.”

The SNES special-chip panel checks signed SA-1 multiplication, a Super FX register immediate and DSP-1 signed Q15 multiplication. Each original cartridge computes and displays a verdict. They are functional probes with program-defined expectations. Emu Bench has not yet recorded these cartridges on original SNES hardware.
