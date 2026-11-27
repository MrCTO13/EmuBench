#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include "libretro.h"
#include <stdio.h>
#include <stdarg.h>
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
    unsigned (*api_version)(void), (*get_region)(void);
    void (*init)(void), (*deinit)(void), (*run)(void), (*unload_game)(void);
    void (*get_system_av_info)(struct retro_system_av_info *);
    void (*get_system_info)(struct retro_system_info *);
    void (*set_environment)(retro_environment_t);
    void (*set_video_refresh)(retro_video_refresh_t);
    void (*set_audio_sample)(retro_audio_sample_t);
    void (*set_audio_sample_batch)(retro_audio_sample_batch_t);
    void (*set_input_poll)(retro_input_poll_t);
    void (*set_input_state)(retro_input_state_t);
    bool (*load_game)(const struct retro_game_info *);
    size_t (*serialize_size)(void);
    bool (*serialize)(void *, size_t), (*unserialize)(const void *, size_t);
} core;
static unsigned renders, pixel_bytes = 2;
static uint64_t audio_frames, signature = 2166136261u;
static bool bad_video, have_previous, snes, can_dupe;
static bool arcade, fbneo, arcade_loaded, load_error;
static void core_log(enum retro_log_level level, const char *fmt, ...) {
    if (!arcade) return;
    char message[1024];
    va_list args;
    va_start(args, fmt);
    vsnprintf(message, sizeof(message), fmt, args);
    va_end(args);
    if (fbneo && strstr(message, "No missing files, proceeding")) arcade_loaded = true;
    if (level == RETRO_LOG_ERROR || strstr(message, "WRONG CHECKSUM")) load_error = true;
}
static uint16_t buttons;
static const char *capture_video;
static enum retro_pixel_format pixel_format = RETRO_PIXEL_FORMAT_0RGB1555;
static uint64_t previous_sample;
static unsigned frame_index, checked_frames, visual_changes, unchanged, longest_stall;
static bool verify_video;
/* Checkpoint frames are copied inside the callback (the copy time is measured and
   excluded) and hashed after the timed advance returns, so hashing never lands in a
   frame time. The sample phase is random per process so a core cannot predict it. */
#define SAMPLE_PERIOD 17
static unsigned sample_phase;
static uint8_t *pending;
static size_t pending_capacity;
static unsigned pending_width, pending_height;
static bool pending_ready;
static uint64_t excluded_ns;
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
/* Wait outside retro_run. Count scheduler delays as part of headless delivery. */
static void wait_until(uint64_t target) {
    uint64_t now;
    while ((now = clock_ns()) < target) {
        uint64_t remain = target - now;
#ifdef _WIN32
        if (remain > 2000000) Sleep((DWORD)((remain - 1000000) / 1000000));
        else SwitchToThread();
#else
        struct timespec delay = {(time_t)(remain / 1000000000), (long)(remain % 1000000000)};
        nanosleep(&delay, NULL);
#endif
    }
}
static bool environment(unsigned command, void *data) {
    switch (command) {
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE:
        if (!arcade) return false;
        ((struct retro_log_callback *)data)->log = core_log;
        return true;
    case RETRO_ENVIRONMENT_SHUTDOWN:
        load_error = true;
        return true;
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
        *(const char **)data = getenv("EMUBENCH_SYSTEM_DIR");
        if (!*(const char **)data) *(const char **)data = ".";
        return true;
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *(const char **)data = ".";
        return true;
    case RETRO_ENVIRONMENT_GET_CAN_DUPE:
        *(bool *)data = can_dupe;
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
        else if (getenv("EMUBENCH_FORCE_COLOR") && !strcmp(var->key, "sameboy_model")) var->value = "Game Boy Color";
        else if (getenv("EMUBENCH_FORCE_COLOR") && !strcmp(var->key, "gambatte_gb_hwmode")) var->value = "GBC";
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
                               : width >= 16 && width <= 4096 && height >= 16 && height <= 4096;
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
    if (verify_video && (frame_index + sample_phase) % SAMPLE_PERIOD == 0) {
        uint64_t copy_start = clock_ns();
        size_t row = (size_t)width * pixel_bytes, need = row * height;
        if (need > pending_capacity) {
            uint8_t *grown = realloc(pending, need);
            if (!grown) exit(fail("Out of memory for frame checkpoint"));
            pending = grown;
            pending_capacity = need;
        }
        for (unsigned y = 0; y < height; ++y) memcpy(pending + y * row, pixels + y * pitch, row);
        pending_width = width;
        pending_height = height;
        pending_ready = true;
        excluded_ns += clock_ns() - copy_start;
    }
    ++renders;
}
/* Hash every active byte, including the right and bottom edges, excluding row padding.
   Runs between timed advances only. */
static uint64_t loop_signature;
static void hash_pending(void) {
    if (!pending_ready) return;
    pending_ready = false;
    uint64_t sample = UINT64_C(14695981039346656037);
    sample = (sample ^ pending_width) * UINT64_C(1099511628211);
    sample = (sample ^ pending_height) * UINT64_C(1099511628211);
    size_t length = (size_t)pending_width * pixel_bytes * pending_height;
    for (size_t x = 0; x < length; ++x)
        sample = (sample ^ pending[x]) * UINT64_C(1099511628211);
    if (have_previous && sample != previous_sample) { ++visual_changes; unchanged = 0; }
    else if (have_previous && ++unchanged > longest_stall) longest_stall = unchanged;
    previous_sample = sample;
    have_previous = true;
    ++checked_frames;
    loop_signature = (loop_signature ^ sample) * UINT64_C(1099511628211);
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
    BIND(api_version); BIND(get_region); BIND(init); BIND(deinit); BIND(run); BIND(unload_game);
    BIND(get_system_av_info); BIND(get_system_info); BIND(set_environment); BIND(set_video_refresh);
    BIND(set_audio_sample); BIND(set_audio_sample_batch); BIND(set_input_poll);
    BIND(set_input_state); BIND(load_game);
    /* Optional: used to repeat the same measured scene until the minimum window is met. */
    void (*symbol)(void);
    if ((symbol = (void (*)(void)) SYMBOL("retro_serialize_size"))) memcpy(&core.serialize_size, &symbol, sizeof(symbol));
    if ((symbol = (void (*)(void)) SYMBOL("retro_serialize"))) memcpy(&core.serialize, &symbol, sizeof(symbol));
    if ((symbol = (void (*)(void)) SYMBOL("retro_unserialize"))) memcpy(&core.unserialize, &symbol, sizeof(symbol));
    return core.api_version() == RETRO_API_VERSION ? 0 : fail("Unsupported libretro API");
}
static long number(const char *value, long min, long max) {
    char *end;
    long n = strtol(value, &end, 10);
    return *value && !*end && min <= n && n <= max ? n : -1;
}
int main(int argc, char **argv) {
    if (argc != 5 && argc != 6) return fail("Expected ROM byte count, warm-up frames, measured frames and core name");
    long bytes = number(argv[1], 0, 32 * 1024 * 1024);
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
    snes = !strcmp(argv[4], "Snes9x") || !strcmp(argv[4], "bsnes") || !strcmp(argv[4], "CartsSNES");
    if (!info.library_name || strcmp(info.library_name, argv[4]))
        return fail("Selected library does not identify as the requested emulator");
    fbneo = !strcmp(argv[4], "FinalBurn Neo");
    arcade = fbneo || !strcmp(argv[4], "MAME");
    can_dupe = !strcmp(argv[4], "Gambatte");
    const char *version = info.library_version;
    if (!version || !*version || strlen(version) > 80 ||
        strspn(version, "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz().-+_ ") != strlen(version))
        return fail("Invalid core version");
    uint8_t *rom = malloc(bytes ? (size_t)bytes : 1);
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
    const char *filename = getenv("EMUBENCH_CONTENT_NAME");
    if (filename) game.path = filename;
    if (!bytes && getenv("EMUBENCH_STAGED")) {
        if (!info.need_fullpath) return fail("Core requires in-memory content");
        game.data = NULL;
    } else if (info.need_fullpath) {
        FILE *staged = fopen(game.path, "wb");
        if (!staged || fwrite(rom, 1, (size_t)bytes, staged) != (size_t)bytes || fclose(staged))
            return fail("Could not stage input for a full-path core");
        game.data = NULL;
        game.size = 0;
    }
    if (!core.load_game(&game)) return fail("Core could not load this ROM");
    uint8_t *replay = NULL;
    bool diagnostic = false;
    bool paced = argc == 6 && !strcmp(argv[5], "paced");
    if (argc == 6 && !paced) {
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
    struct retro_system_av_info av = {0};
    core.get_system_av_info(&av);
    FILE *rate = fopen("video-rate", "w");
    if (!rate || fprintf(rate, "%u %.17g\n", core.get_region(), av.timing.fps) < 0 || fclose(rate))
        return fail("Cannot record console video timing");
    if (paced && (!(av.timing.fps >= 45 && av.timing.fps <= 75) ||
                  !(av.timing.sample_rate >= 8000 && av.timing.sample_rate <= 192000)))
        return fail("Unsupported core refresh rate or audio sample rate");
    long late = 0;
    uint64_t missing = 0, last = clock_ns(), epoch = last;
    /* Two refresh periods of initial audio buffering. No physical audio device is involved. */
    uint64_t reserve = paced ? (uint64_t)(2 * av.timing.sample_rate / av.timing.fps) : 0;
    /* Minimum timed window. Short windows are dominated by turbo, scheduler and timer
       noise, so the same measured frames repeat from a saved state until both the frame
       count and the wall-time minimum are met. Paced and diagnostic runs never repeat. */
    const char *min_env = getenv("EMUBENCH_MIN_WINDOW_MS");
    uint64_t min_window = (!paced && !diagnostic && min_env) ? (uint64_t)number(min_env, 0, 600000) * 1000000ull : 0;
    if (min_env && !paced && !diagnostic && number(min_env, 0, 600000) < 0) return fail("Invalid minimum window");
    size_t state_size = 0;
    void *state = NULL;
    if (min_window && core.serialize_size && core.serialize && core.unserialize) {
        state_size = core.serialize_size();
        state = state_size ? malloc(state_size) : NULL;
        if (state && !core.serialize(state, state_size)) { free(state); state = NULL; }
    }
#ifdef _WIN32
    uint64_t pid = GetCurrentProcessId();
#else
    uint64_t pid = (uint64_t)getpid();
#endif
    sample_phase = (unsigned)((clock_ns() ^ pid * UINT64_C(0x9E3779B97F4A7C15)) % SAMPLE_PERIOD);
    if (getenv("EMUBENCH_SAMPLE_PHASE")) sample_phase = (unsigned)number(getenv("EMUBENCH_SAMPLE_PHASE"), 0, SAMPLE_PERIOD - 1);
    uint64_t first_signature = 0, timed_ns = 0;
    long total = 0, loops = 0, capacity = frames;
    bool consistent = true;
    for (;;) {
        loop_signature = 2166136261u;
        for (long i = 0; i < frames; i++) {
            if (replay) {
                long pos = (warmup + i) * 2;
                buttons = (uint16_t)(replay[pos] | replay[pos+1] << 8);
            }
            if (paced) wait_until(epoch + (uint64_t)(i * 1e9 / av.timing.fps));
            verify_video = !diagnostic;
            frame_index = (unsigned)i;
            uint64_t supplied = audio_frames;
            renders = 0;
            excluded_ns = 0;
            core.run();
            uint64_t now = clock_ns();
            if ((!diagnostic && (bad_video || renders != 1)) || now <= last + excluded_ns)
                return fail("Expected one completed software framebuffer per timed frame and a positive duration");
            if (paced) {
                uint64_t due = epoch + (uint64_t)((i + 1) * 1e9 / av.timing.fps);
                if (now > due) ++late;
                uint64_t consumed = (uint64_t)((now - epoch) * (av.timing.sample_rate / 1e9));
                if (consumed > reserve + supplied + missing)
                    missing = consumed - reserve - supplied;
            }
            if (total == capacity) {
                long grown = capacity * 2 > 1000000 ? 1000000 : capacity * 2;
                uint64_t *more = grown > capacity ? realloc(timings, (size_t)grown * sizeof(*timings)) : NULL;
                if (!more) return fail("Frame trace limit reached");
                timings = more;
                capacity = grown;
            }
            timings[total] = now - last - excluded_ns;
            timed_ns += timings[total++];
            hash_pending();
            last = paced ? now : clock_ns();  // Hashing between frames is never timed.
        }
        if (!loops) first_signature = loop_signature;
        else if (loop_signature != first_signature) consistent = false;
        ++loops;
        if (timed_ns >= min_window || total + frames > 1000000) break;
        if (state) {
            if (!core.unserialize(state, state_size)) return fail("Core could not restore the scene start");
        } else if (replay) break;  // A replay cannot run past its recording without a saved state.
        last = clock_ns();
    }
    free(state);
    signature = first_signature;
    frames = total;
    verify_video = false;
    if (!diagnostic && (!visual_changes || longest_stall >= 30))
        return fail("No motion across framebuffer checkpoints or a sustained duplicate frame sequence");
    if (load_error || (fbneo && !arcade_loaded)) return fail("Emulator could not confirm a working game or ROM set");
    if (!audio_frames) return fail("Core emitted no audio samples");
    if (paced) {
        FILE *report = fopen("paced-result", "w");
        if (!report) return fail("Could not save paced report");
        fprintf(report, "%ld %ld %" PRIu64 " %.9f %.9f\n", frames, late, missing, av.timing.fps, av.timing.sample_rate);
        if (fclose(report)) return fail("Incomplete paced report");
    }
    FILE *evidence = fopen("frame-evidence", "wb");
    if (!evidence) return fail("Could not save measured frame times");
    fprintf(evidence, "EB3\n%s\n%" PRIu64 "\n%016" PRIx64 "\n%" PRIu32 "\n%ld\n%d\n%u\n%u\n", version, audio_frames, signature,
            visual_changes, loops, consistent ? 1 : 0, sample_phase, checked_frames);
    for (long i = 0; i < frames; i++) fprintf(evidence, "%" PRIu64 "\n", timings[i]);
    if (fclose(evidence)) return fail("Incomplete frame evidence");
    // Capture the next frame after sealing the timed interval and its counters.
    if (replay) {
        bad_video = false;
        renders = 0;
        capture_video = diagnostic ? "final-frame" : "scene-end";
        core.run();
        if (bad_video || renders != 1) return fail("Incomplete visual checkpoint");
        capture_video = NULL;
    }
    free(replay);
    free(pending);
    core.unload_game();
    core.deinit();
    free(timings);
    free(rom);
    return 0;
}
