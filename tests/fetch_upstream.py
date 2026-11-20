"""Download small, pinned upstream source fixtures; never model weights."""
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

REPOS = {
    "forge": ("Haoming02/sd-webui-forge-classic", "neo", {
        "main_entry.py": "modules_forge/main_entry.py",
        "presets.py": "modules_forge/presets.py",
        "k_prediction.py": "backend/modules/k_prediction.py",
        "krea.py": "backend/diffusion_engine/krea.py",
        "base.py": "backend/diffusion_engine/base.py",
        "infotext_utils.py": "modules/infotext_utils.py",
        "processing.py": "modules/processing.py",
        "xyz_grid.py": "scripts/xyz_grid.py",
        "sd_samplers_kdiffusion.py": "modules/sd_samplers_kdiffusion.py",
        "sd_schedulers.py": "modules/sd_schedulers.py",
        "sd_samplers_common.py": "modules/sd_samplers_common.py",
        "scripts.py": "modules/scripts.py",
        "ui_components.py": "modules/ui_components.py",
        "gradio_extensions.py": "modules/gradio_extensions.py",
        "inputAccordion.js": "javascript/inputAccordion.js",
    }),
    "iib": ("zanllp/infinite-image-browsing", "main", {
        "iib_setup.py": "scripts/iib_setup.py",
        "iib_tool.py": "scripts/iib/tool.py",
    }),
}


def get(url):
    return urlopen(Request(url, headers={"User-Agent": "neo-krea-shift-tests"}), timeout=60).read()


if __name__ == "__main__":
    dest = Path(sys.argv[1])
    dest.mkdir(parents=True, exist_ok=True)
    lock = Path(__file__).with_name("upstream.json")
    revisions = json.loads(lock.read_text()) if lock.exists() else {}
    for name, (repo, branch, files) in REPOS.items():
        if name not in revisions:
            revisions[name] = json.loads(get(f"https://api.github.com/repos/{repo}/commits/{branch}"))["sha"]
        for filename, source in files.items():
            (dest / filename).write_bytes(get(f"https://raw.githubusercontent.com/{repo}/{revisions[name]}/{source}"))
        print(name, revisions[name], len(files), "source files")
    lock.write_text(json.dumps(revisions, indent=2) + "\n")
