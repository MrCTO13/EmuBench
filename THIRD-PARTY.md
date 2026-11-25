Emu Bench is presented by Carts. The Emu Bench frontend and measurement worker are MIT licensed.

The worker builds against the libretro API header by the RetroArch team. The full notice appears at the top of the vendored header. [Source at the exact imported revision](https://github.com/mgba-emu/mgba/blob/26b7884bc25a5933960f3cdcd98bac1ae14d42e2/src/platform/libretro/libretro.h).

Emu Bench fetches mGBA from its upstream repository and builds it on your machine. mGBA and its dependencies retain their respective licenses. The reference revision is 26b7884bc25a5933960f3cdcd98bac1ae14d42e2. [mGBA license and acknowledgments](https://github.com/mgba-emu/mgba/tree/26b7884bc25a5933960f3cdcd98bac1ae14d42e2#license).

The Carts and Emu Bench wordmarks identify the presenter and project. The header in the HTML score viewer uses the Carts wordmark supplied for this site.

Desktop releases contain the Emu Bench tools and score viewer. Emulator packages are downloaded directly from the selected upstream project or Libretro Buildbot to the user’s machine and retain their upstream terms.

Cartervania and Super Carter Bros. 3 are Carts game projects with their own source and distribution terms. Emu Bench supplies controller replays and checkpoint digests. Accuracy workloads are fetched from [GBA Tests](https://github.com/jsmolka/gba-tests) and [SNES tests](https://github.com/gilyon/snes-tests) under their upstream terms. The reader recognizes the terminal pass/fail messages defined by those projects.

Beginning with 0.6, the reference directory includes an unmodified mGBA 0.10.5 libretro library, its license, component notices and matching buildable source in mgba-source.zip. The upstream cinema regression corpus is omitted. mGBA is copyright Jeffrey Pfau and contributors. See LICENSE-mGBA.txt and the component notices in the reference directory. To rebuild, extract the source and use the libretro CMake flags in emubench/engines.py. Any compatible replacement library can be selected with --core.

Carter Circuit and the SA-1 and Super FX probe programs and graphics in this repository are original MIT-licensed source. Users build them locally. The optional edition catalog comes directly from the pinned libretro-database No-Intro metadata. CartsSNES remains a separately supplied Carts core.

The optional Game Boy Color checks fetch Matt Currie's cgb-acid2 v1.1 and five CGB sound tests written by Blargg from their upstream locations at run time. The CLI ships their identities and expected-result checks. See [STUDIES.md](STUDIES.md) for credits and reference images. The sample manifest uses public No-Intro metadata from the pinned Libretro Database revision recorded in each study.
