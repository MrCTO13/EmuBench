"""Render the download choices as ordinary links, including with JavaScript disabled."""
from html import escape

RELEASES = "https://github.com/MrCTO13/EmuBench/releases/download"
DESKTOP_VERSION = "0.8.0-rc.2"
CLI_VERSION = "0.8.0-rc.1"
CHOICES = {
    "mac": ("Mac app", "Apple silicon and Intel"),
    "windows": ("Windows app", "x64 and ARM64"),
    "cli": ("Command line", "Mac, Windows and Linux"),
}


def asset(platform, cpu, label, desktop=False):
    name = ("EmuBench-Desktop-" if desktop else "emubench-") + f"{platform}-{cpu}.zip"
    version = DESKTOP_VERSION if desktop else CLI_VERSION
    return f'<a class="file-link" href="{RELEASES}/v{version}/{name}">{escape(label)}</a>'


def desktop(platform):
    mac = platform == "mac"
    target = "macos" if mac else "windows"
    releases = (
        (("arm64", "Download for Apple silicon"), ("x64", "Download for Intel Mac")) if mac else
        (("x64", "Download for Intel or AMD"), ("arm64", "Download for Windows ARM64"))
    )
    buttons = "".join(asset(target, cpu, label, True) for cpu, label in releases)
    if mac:
        choose = "Open the Apple menu and choose About This Mac. For an Apple M-series chip, choose Apple silicon. For an Intel processor, choose Intel Mac."
        steps = ["Open the ZIP and drag EmuBench into Applications.", "Open EmuBench. Choose a game, an emulator and a scene, then click Run benchmark."]
        gate = "This beta is not notarized by Apple. If macOS blocks the app, review the download in System Settings → Privacy &amp; Security."
    else:
        choose = "In Settings → System → About, check System type. Choose ARM64 for an ARM-based processor, or Intel or AMD for an x64-based processor."
        steps = ["Right-click the ZIP and choose Extract All. Keep the extracted folder together.", "Open EmuBench.exe. Choose a game, an emulator and a scene, then click Run benchmark."]
        gate = "Windows may show an unknown-publisher notice for this unsigned beta."
    instructions = "".join(f"<li>{step}</li>" for step in steps)
    return f"""<section class="install-panel" aria-labelledby="install">
      <h2 id="install">{'EmuBench for Mac' if mac else 'EmuBench for Windows'}</h2>
      <p class="install-note">Desktop beta {DESKTOP_VERSION}</p><div class="download-files">{buttons}</div>
      <details><summary>Which download fits my computer?</summary><p>{choose}</p></details>
      <h3>Install and run</h3><ol>{instructions}
        <li>The first run downloads the emulator and test files. Open History to inspect individual frames or publish a score.</li></ol>
      <p class="install-note">{gate}</p></section>"""


def command_line():
    rows = []
    for name, target in [("macOS","macos"),("Windows","windows"),("Linux","linux")]:
        rows.append(f'<tr><th scope="row">{name}</th><td>{asset(target, "arm64", "Apple silicon" if target=="macos" else "ARM64")}</td><td>{asset(target, "x64", "Intel Mac" if target=="macos" else "x64")}</td></tr>')
    return f"""<section class="install-panel" aria-labelledby="install"><h2 id="install">EmuBench CLI</h2>
      <p class="install-note">CLI beta {CLI_VERSION}</p>
      <table class="cli-files"><caption class="sr">Command-line downloads by operating system and processor</caption>
      <thead><tr><th scope="col">System</th><th scope="col">ARM</th><th scope="col">Intel / AMD</th></tr></thead><tbody>""" + "".join(rows) + """</tbody></table>
      <h3>Run Cartervania from a terminal</h3>
      <p>Extract the ZIP and open a terminal in the extracted folder. Run the command for your system.</p>
      <div class="shell-example"><b>Mac or Linux</b><code>./emubench carter --emulator mgba --scene normal</code></div>
      <div class="shell-example"><b>Windows PowerShell</b><code>.&#92;emubench.exe carter --emulator mgba --scene normal</code></div>
      <p>The first run downloads the emulator and diagnostic files. Use <code>history</code> to see saved runs or <code>uploads enable</code> to share future scores.</p></section>"""


def pages(shell):
    header, body = shell.split('<main id="main"', 1)
    footer = body.split("</main>", 1)[1].replace('<script src="/client.js" defer></script>', "")
    header = header.replace("EmuBench · Emulator benchmarks","Download EmuBench").replace('class="download" href="/download"', 'class="download" aria-current="page" href="/download"')
    result = {}
    for active in ("", *CHOICES):
        links=[]
        for key,(label,subtitle) in CHOICES.items():
            current=' aria-current="page"' if key==active else ""
            links.append(f'<a href="/download?platform={key}"{current}><strong>{label}</strong><span>{subtitle}</span></a>')
        panel = desktop(active) if active in ("mac","windows") else command_line() if active=="cli" else (
            '<figure class="desktop-preview"><img src="/assets/desktop-mac.png" width="960" height="628" '
            'alt="EmuBench window with workload, emulator and scene selectors beside the FPS and accuracy results">'
            '<figcaption>EmuBench Desktop on macOS</figcaption></figure>'
        )
        result[active] = header + """<main id="main" class="downloads" tabindex="-1">
          <section class="lead download-lead"><div class="heading"><h1>Download EmuBench</h1>
          <p>Open the desktop app to benchmark a game. Choose the CLI for scripts and unattended runs.</p></div></section>
          <div class="download-body"><div class="platform-picker" role="group" aria-label="Choose a download">""" + "".join(links) + "</div>" + panel + """</div></main>""" + footer
    return result
