"""Install immutable mGBA releases from the upstream project."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

UPSTREAM = "https://github.com/mgba-emu/mgba.git"
API = "https://api.github.com/repos/mgba-emu/mgba"
REFERENCE = "0.10.5"
REFERENCE_COMMIT = "26b7884bc25a5933960f3cdcd98bac1ae14d42e2"
TAG = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
SHA = re.compile(r"[0-9a-f]{40}")
NATIVE = Path(__file__).resolve().parent / "native"
EXE = ".exe" if os.name == "nt" else ""
LIB = {"Darwin": ".dylib", "Windows": ".dll", "Linux": ".so"}


def home():
    if "EMUBENCH_HOME" in os.environ:
        return Path(os.environ["EMUBENCH_HOME"]).expanduser().resolve()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library/Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return root / "EmuBench"


def platform_id():
    return platform.system().lower() + "-" + platform.machine().lower()


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def open_upstream(request):
    trust = ssl.create_default_context()
    # A frozen Python may retain an OpenSSL prefix from the CI build machine.
    # Augment its defaults with the distribution's installed CA roots.
    if os.name != "nt":
        for bundle in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt",
                       "/etc/pki/tls/certs/ca-bundle.crt"):
            if Path(bundle).is_file():
                trust.load_verify_locations(cafile=bundle)
                break
    return urlopen(request, timeout=30, context=trust)


def api(path):
    request = Request(API + path, headers={"User-Agent": "EmuBench/0.1", "Accept": "application/vnd.github+json"})
    with open_upstream(request) as response:
        return json.load(response)


def remote_tags(*refs):
    output = subprocess.check_output(["git", "ls-remote", "--tags", UPSTREAM, *refs], text=True, timeout=60)
    return {ref: commit for commit, ref in (line.split() for line in output.splitlines())}


def releases():
    try:
        return [r["tag_name"] for r in api("/releases?per_page=100")
                if not r["prerelease"] and not r["draft"] and TAG.fullmatch(r["tag_name"])]
    except HTTPError as exc:
        if exc.code not in (403, 429):
            raise
        names = [ref.removeprefix("refs/tags/") for ref in remote_tags()]
        return sorted((v for v in names if TAG.fullmatch(v)),
                      key=lambda v: tuple(map(int, v.split("."))), reverse=True)


def release_tag(value):
    if value == "latest":
        # The canonical latest-release redirect also works on shared networks
        # that have exhausted GitHub's unauthenticated REST quota.
        with open_upstream(Request("https://github.com/mgba-emu/mgba/releases/latest", method="HEAD")) as response:
            prefix = "https://github.com/mgba-emu/mgba/releases/tag/"
            if not response.url.startswith(prefix):
                raise ValueError("Unexpected mGBA release redirect")
            value = response.url[len(prefix):]
    if not TAG.fullmatch(value):
        raise ValueError("Use a stable mGBA release such as 0.10.5 or latest")
    return value


def call(args):
    print("+", " ".join(map(str, args)), file=sys.stderr, flush=True)
    subprocess.run(args, check=True, stdout=sys.stderr)


def compile_target(source, build, target, flags=()):
    call(["cmake", "-S", source, "-B", build, "-DCMAKE_BUILD_TYPE=Release", *flags])
    call(["cmake", "--build", build, "--config", "Release", "--target", target, "--parallel", "2"])


def artifact(build, name):
    paths = [p for p in build.rglob(name) if p.is_file()]
    if len(paths) != 1:
        raise ValueError(f"Expected a single {name} from CMake, found {len(paths)}")
    return paths[0]


def promote(stage, dest):
    # Another process may have installed this immutable build while we compiled.
    try:
        stage.rename(dest)
    except OSError:
        if not dest.is_dir():
            raise


def worker():
    name = "emubench-worker" + EXE
    packaged = NATIVE / "bin" / name
    if packaged.is_file():
        return packaged
    fingerprint = hashlib.sha256("".join(digest(NATIVE / f) for f in
        ("worker.c", "libretro.h", "CMakeLists.txt")).encode()).hexdigest()[:20]
    parent = home() / "workers" / platform_id()
    dest = parent / fingerprint
    if not dest.is_dir():
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            temp = Path(folder)
            compile_target(NATIVE, temp / "build", "emubench-worker")
            stage = temp / "ready"
            stage.mkdir()
            shutil.copy2(artifact(temp / "build", name), stage / name)
            promote(stage, dest)
    return dest / name


def bundled_reference():
    if not getattr(sys, "frozen", False):
        return None
    folder = Path(sys.executable).resolve().parent / "reference"
    meta_file = folder / "build.json"
    if not meta_file.is_file():
        return None
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    path = folder / ("mgba_libretro" + LIB[platform.system()])
    if meta["tag"] != REFERENCE or meta["commit"] != REFERENCE_COMMIT or digest(path) != meta["sha256"]:
        raise ValueError("Packaged reference core failed verification")
    return path, meta


def install(value):
    tag = release_tag(value)
    if tag == REFERENCE:
        bundled = bundled_reference()
        if bundled:
            return bundled
    parent = home() / "engines" / platform_id() / "mgba"
    dest = parent / tag
    name = "mgba_libretro" + LIB[platform.system()]
    if not dest.is_dir():
        if tag == REFERENCE:
            commit = REFERENCE_COMMIT
        else:
            ref = "refs/tags/" + tag
            tags = remote_tags(ref, ref + "^{}")
            commit = tags.get(ref + "^{}", tags.get(ref, ""))
        if not SHA.fullmatch(commit):
            raise ValueError("Invalid upstream commit identity")
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            temp = Path(folder)
            source = temp / "upstream"
            call(["git", "-c", "advice.detachedHead=false", "clone", "--depth", "1",
                  "--branch", tag, UPSTREAM, source])
            actual = subprocess.check_output(["git", "-C", source, "rev-parse", "HEAD"], text=True).strip()
            if actual != commit:
                raise ValueError("The upstream tag changed. Refusing to score a different revision.")
            flags = ["-DCMAKE_POLICY_VERSION_MINIMUM=3.5", "-DLIBMGBA_ONLY=ON",
                     "-DBUILD_LIBRETRO=ON", "-DSKIP_LIBRARY=ON", "-DLIBRETRO_LIBDIR=lib"]
            compile_target(source, temp / "build", "mgba_libretro", flags)
            stage = temp / "ready"
            stage.mkdir()
            shutil.copy2(artifact(temp / "build", name), stage / name)
            meta = {"tag": tag, "commit": commit, "sha256": digest(stage / name)}
            (stage / "build.json").write_text(json.dumps(meta), encoding="utf-8")
            promote(stage, dest)
    meta = json.loads((dest / "build.json").read_text(encoding="utf-8"))
    if (meta["tag"] != tag or not SHA.fullmatch(meta["commit"])
            or tag == REFERENCE and meta["commit"] != REFERENCE_COMMIT
            or digest(dest / name) != meta["sha256"]):
        raise ValueError("Cached build failed verification. Remove that version and install it again.")
    return dest / name, meta
