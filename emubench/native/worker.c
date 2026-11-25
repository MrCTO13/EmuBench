#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include "libretro.h"
#include <stdio.h>
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <time.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#endif

/* The core runs in a dedicated child process. Python never enters the timed loop. */
static struct {
    unsigned (*api_version)(void);
    void (*init)(void), (*deinit)(void), (*run)(void), (*unload_game)(void);
    void (*get_system_info)(struct retro_system_info *);
    void (*set_environment)(retro_environment_t);
    void (*set_video_refresh)(retro_video_refresh_t);
    void (*set_audio_sample)(retro_audio_sample_t);
    void (*set_audio_sample_batch)(retro_audio_sample_batch_t);
    void (*set_input_poll)(retro_input_poll_t);
    void (*set_input_state)(retro_input_state_t);
    bool (*load_game)(const struct retro_game_info *);
} core;
static unsigned renders, pixel_bytes = 2;
static uint64_t audio_frames, signature = 2166136261u;
static bool bad_video, have_previous, snes;
static uint16_t buttons;
static const char *capture_video;
static enum retro_pixel_format pixel_format = RETRO_PIXEL_FORMAT_0RGB1555;
static uint32_t previous_sample, visual_changes;
#ifdef _WIN32
static LARGE_INTEGER frequency, origin;
#endif

static int fail(const char *message) {
    fprintf(stderr, "%s\n", message);
    return 1;
}
/* The OS releases this slot even if the controller or worker crashes. */
static int claim_slot(void) {
#ifdef _WIN32
    const wchar_t *path = _wgetenv(L"EMUBENCH_WORKER_LOCK");
    if (!path) return fail("Missing measurement lock path");
    HANDLE lock = CreateFileW(path, GENERIC_WRITE, 0, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (lock != INVALID_HANDLE_VALUE) return 0;
    return GetLastError() == ERROR_SHARING_VIOLATION ? 75 : fail("Cannot lock measurement slot");
#else
    const char *path = getenv("EMUBENCH_WORKER_LOCK");
    int fd = path ? open(path, O_WRONLY | O_CREAT, 0600) : -1;
    if (fd < 0) return fail("Cannot open measurement lock");
    struct flock lock = {0};
    lock.l_type = F_WRLCK;
    lock.l_whence = SEEK_SET;
    if (fcntl(fd, F_SETLK, &lock) == 0) return 0;
    return errno == EAGAIN || errno == EACCES ? 75 : fail("Cannot lock measurement slot");
#endif
}
static uint64_t clock_ns(void) {
#ifdef _WIN32
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    uint64_t ticks = (uint64_t)(now.QuadPart - origin.QuadPart);
    uint64_t hz = (uint64_t)frequency.QuadPart;
    return (ticks / hz) * 1000000000ull + (ticks % hz) * 1000000000ull / hz;
#else
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) exit(fail("Monotonic clock failed"));
    return (uint64_t)now.tv_sec * 1000000000ull + now.tv_nsec;
#endif
}
static bool environment(unsigned command, void *data) {
    switch (command) {
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *(const char **)data = ".";
        return true;
    case RETRO_ENVIRONMENT_GET_CAN_DUPE:
        *(bool *)data = false;
        return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT: {
        enum retro_pixel_format format = *(enum retro_pixel_format *)data;
        pixel_format = format;
        pixel_bytes = format == RETRO_PIXEL_FORMAT_XRGB8888 ? 4 : 2;
        return format == RETRO_PIXEL_FORMAT_RGB565 || format == RETRO_PIXEL_FORMAT_0RGB1555 ||
               format == RETRO_PIXEL_FORMAT_XRGB8888;
    }
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        struct retro_variable *var = data;
        if (!strcmp(var->key, "mgba_frameskip")) var->value = "0";
        else if (!strcmp(var->key, "mgba_use_bios")) var->value = "OFF";
        else if (!strcmp(var->key, "mgba_skip_bios")) var->value = "ON";
        else if (!strcmp(var->key, "mgba_idle_optimization")) var->value = "Don't Remove";
        else if (!strcmp(var->key, "bsnes_run_ahead_frames")) var->value = "OFF";
        else { var->value = NULL; return false; }
        return true;
    }
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
        *(bool *)data = false;
        return true;
    case RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE:
        *(int *)data = 3;
        return true;
    case RETRO_ENVIRONMENT_GET_INPUT_BITMASKS:
        return true;
    default:
        return false;
    }
}
static void video(const void *buffer, unsigned width, unsigned height, size_t pitch) {
    bool valid_geometry = snes ? (width == 256 || width == 512) && height >= 200 && height <= 512
                               : width == 240 && height == 160;
    if (!buffer || buffer == RETRO_HW_FRAME_BUFFER_VALID || !valid_geometry ||
        pitch < width * pixel_bytes) {
        bad_video = true;
        return;
    }
    const uint8_t *pixels = buffer;
    // The accuracy command requests one final image on a separate, untimed advance.
    if (capture_video) {
        FILE *f = fopen(capture_video, "wb");
        if (!f) exit(fail("Could not save diagnostic frame"));
        fprintf(f, "%u %u %u\n", width, height, (unsigned)pixel_format);
        for (unsigned y = 0; y < height; ++y)
            if (fwrite(pixels + y * pitch, pixel_bytes, width, f) != width)
                exit(fail("Incomplete diagnostic frame"));
        if (fclose(f)) exit(fail("Incomplete diagnostic frame"));
    }
    uint32_t sample = 2166136261u;
    for (unsigned i = 0; i < 8; i++) {
        size_t offset = (i * 19 + 5) * pitch + (i * 29 + 3) * pixel_bytes;
        for (unsigned channel = 0; channel < pixel_bytes; channel++)
            sample = (sample ^ pixels[offset + channel]) * 16777619u;
    }
    if (have_previous && sample != previous_sample) ++visual_changes;
    have_previous = true;
    previous_sample = sample;
    signature = (signature ^ sample) * 16777619u;
    ++renders;
}
static void audio(int16_t left, int16_t right) { (void)left; (void)right; ++audio_frames; }
static size_t audio_batch(const int16_t *buffer, size_t frames) {
    if (buffer) audio_frames += frames;
    return frames;
}
static void poll_input(void) {}
static int16_t input(unsigned port, unsigned device, unsigned index, unsigned id) {
    if (port || device != RETRO_DEVICE_JOYPAD || index) return 0;
    if (id == RETRO_DEVICE_ID_JOYPAD_MASK) return (int16_t)buttons;
    return id < 16 && (buttons & (1u << id)) ? 1 : 0;
}
static int open_core(void) {
#ifdef _WIN32
    const wchar_t *path = _wgetenv(L"EMUBENCH_CORE_PATH");
    HMODULE lib = path ? LoadLibraryExW(path, NULL, LOAD_WITH_ALTERED_SEARCH_PATH) : NULL;
#define SYMBOL(n) GetProcAddress(lib, n)
#else
    const char *path = getenv("EMUBENCH_CORE_PATH");
    void *lib = path ? dlopen(path, RTLD_NOW | RTLD_LOCAL) : NULL;
#define SYMBOL(n) dlsym(lib, n)
#endif
    if (!lib) return fail("Cannot load the selected core. Check OS, architecture and dependencies.");
#define BIND(field) do { void (*symbol)(void) = (void (*)(void)) SYMBOL("retro_" #field); \
    if (!symbol) return fail("Missing libretro entry point: " #field); \
    memcpy(&core.field, &symbol, sizeof(symbol)); } while (0)
    BIND(api_version); BIND(init); BIND(deinit); BIND(run); BIND(unload_game);
    BIND(get_system_info); BIND(set_environment); BIND(set_video_refresh);
    BIND(set_audio_sample); BIND(set_audio_sample_batch); BIND(set_input_poll);
    BIND(set_input_state); BIND(load_game);
    return core.api_version() == RETRO_API_VERSION ? 0 : fail("Unsupported libretro API");
}
static long number(const char *value, long min, long max) {
    char *end;
    long n = strtol(value, &end, 10);
    return *value && !*end && min <= n && n <= max ? n : -1;
}
int main(int argc, char **argv) {
    if (argc != 5 && argc != 6) return fail("Expected ROM byte count, warm-up frames, measured frames and core name");
    long bytes = number(argv[1], 192, 32 * 1024 * 1024);
    long warmup = number(argv[2], 0, 1000000), frames = number(argv[3], 100, 1000000);
    if (bytes < 0 || warmup < 0 || frames < 0) return fail("Invalid measurement parameters");
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
    if (!QueryPerformanceFrequency(&frequency) || !QueryPerformanceCounter(&origin))
        return fail("Performance clock unavailable");
#endif
    int lock_status = claim_slot();
    if (lock_status) return lock_status;
    if (open_core()) return 1;
    struct retro_system_info info = {0};
    core.get_system_info(&info);
    snes = !strcmp(argv[4], "Snes9x") || !strcmp(argv[4], "bsnes");
    if ((!snes && strcmp(argv[4], "mGBA")) || !info.library_name || strcmp(info.library_name, argv[4]))
        return fail("Selected library does not identify as the requested emulator");
    const char *version = info.library_version;
    if (!version || !*version || strlen(version) > 80 ||
        strspn(version, "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.-+_ ") != strlen(version))
        return fail("Invalid core version");
    uint8_t *rom = malloc((size_t)bytes);
    uint64_t *timings = calloc((size_t)frames, sizeof(*timings));
    if (!rom || !timings || fread(rom, 1, (size_t)bytes, stdin) != (size_t)bytes)
        return fail("Unable to read ROM into memory");
    core.set_environment(environment);
    core.set_video_refresh(video);
    core.set_audio_sample(audio);
    core.set_audio_sample_batch(audio_batch);
    core.set_input_poll(poll_input);
    core.set_input_state(input);
    core.init();
    struct retro_game_info game = { snes ? "workload.sfc" : "workload.gba", rom, (size_t)bytes, NULL };
    if (info.need_fullpath) {
        FILE *staged = fopen(game.path, "wb");
        if (!staged || fwrite(rom, 1, (size_t)bytes, staged) != (size_t)bytes || fclose(staged))
            return fail("Could not stage input for a full-path core");
        game.data = NULL;
        game.size = 0;
    }
    if (!core.load_game(&game)) return fail("Core could not load this ROM");
    uint8_t *replay = NULL;
    bool diagnostic = false;
    if (argc == 6) {
        diagnostic = !strcmp(argv[5], "diagnostic");
        if (!diagnostic && strcmp(argv[5], "replay")) return fail("Unknown workload mode");
        size_t length = (size_t)(warmup + frames) * 2;
        FILE *file = fopen("controller.bin", "rb");
        replay = malloc(length);
        if (!file || !replay || fread(replay, 1, length, file) != length || fgetc(file) != EOF)
            return fail("Invalid controller recording");
        fclose(file);
    }
    for (long i = 0; i < warmup; i++) {
        if (replay) buttons = (uint16_t)(replay[i*2] | replay[i*2+1] << 8);
        if (replay && !diagnostic && i + 1 == warmup) capture_video = "scene-start";
        core.run();
    }
    capture_video = NULL;
    audio_frames = 0;
    bad_video = false;
    visual_changes = 0;
    have_previous = false;
    signature = 2166136261u;
    uint64_t last = clock_ns();
    for (long i = 0; i < frames; i++) {
        if (replay) {
            long pos = (warmup + i) * 2;
            buttons = (uint16_t)(replay[pos] | replay[pos+1] << 8);
        }
        renders = 0;
        core.run();
        uint64_t now = clock_ns();
        if (bad_video || renders != 1 || now <= last)
            return fail("Expected one completed software framebuffer per timed frame and a positive duration");
        timings[i] = now - last;
        last = now;
    }
    if (!audio_frames) return fail("Core emitted no audio samples");
    FILE *evidence = fopen("frame-evidence", "wb");
    if (!evidence) return fail("Could not save measured frame times");
    fprintf(evidence, "EB2\n%s\n%" PRIu64 "\n%016" PRIx64 "\n%" PRIu32 "\n", version, audio_frames, signature, visual_changes);
    for (long i = 0; i < frames; i++) fprintf(evidence, "%" PRIu64 "\n", timings[i]);
    if (fclose(evidence)) return fail("Incomplete frame evidence");
    // Capture the next frame after sealing the timed interval and its counters.
    if (replay) {
        renders = 0;
        capture_video = diagnostic ? "final-frame" : "scene-end";
        core.run();
        if (bad_video || renders != 1) return fail("Incomplete visual checkpoint");
        capture_video = NULL;
    }
    free(replay);
    core.unload_game();
    core.deinit();
    free(timings);
    free(rom);
    return 0;
}
