"""Download the data files. This is the only module that touches the network,
and it is only ever called from ``localddi import``."""

from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import REPO_URL, __version__

RXNORM_URL = "https://download.nlm.nih.gov/rxnorm/RxNorm_full_prescribe_current.zip"
DDINTER_BASE = "https://ddinter2.scbdd.com/static/media/download/"
# DDInter splits its data by ATC drug category. Its download page links eight of the
# files; the other six are served from the same directory but are not linked there.
# Without them, pairs where neither drug falls in a linked category are missing
# (for example sildenafil + nitroglycerin). See docs/data-and-licensing.md.
DDINTER_LINKED = [f"ddinter_downloads_code_{code}.csv" for code in "ABDHLPRV"]
DDINTER_UNLINKED = [f"ddinter_downloads_code_{code}.csv" for code in "CGJMNS"]
DDINTER_FILES = DDINTER_LINKED + DDINTER_UNLINKED

USER_AGENT = f"localddi/{__version__} (+{REPO_URL})"
CHUNK = 1 << 16


def fetch(url: str, dest: Path, *, retries: int = 5, timeout: int = 60) -> Path:
    """Download ``url`` to ``dest``, resuming a partial file and retrying on errors."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        offset = part.stat().st_size if part.exists() else 0
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if offset:
            request.add_header("Range", f"bytes={offset}-")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                resumed = response.status == 206
                if offset and not resumed:
                    offset = 0  # server ignored the range request; start again
                length = response.headers.get("Content-Length")
                total = offset + int(length) if length else None
                done = offset
                last_print = 0.0
                with part.open("ab" if resumed else "wb") as handle:
                    while True:
                        chunk = response.read(CHUNK)
                        if not chunk:
                            break
                        handle.write(chunk)
                        done += len(chunk)
                        now = time.monotonic()
                        if total and now - last_print > 5:
                            last_print = now
                            print(f"  {dest.name}: {done / 1e6:.0f} / {total / 1e6:.0f} MB", file=sys.stderr)
                if total is not None and done < total:
                    raise OSError(f"connection closed after {done} of {total} bytes")
            part.replace(dest)
            return dest
        except urllib.error.HTTPError as error:
            if error.code == 416 and part.exists():  # stale partial file
                part.unlink()
            last_error = error
        except (OSError, urllib.error.URLError) as error:
            last_error = error
        print(f"  download attempt {attempt}/{retries} failed for {url}: {last_error}", file=sys.stderr)
        time.sleep(min(2**attempt, 20))
    raise RuntimeError(f"could not download {url}: {last_error}")


def fetch_rxnorm(cache_dir: Path, refresh: bool = False) -> Path:
    dest = cache_dir / "RxNorm_full_prescribe_current.zip"
    if dest.exists() and not refresh:
        print(f"Using cached {dest}", file=sys.stderr)
        return dest
    print(f"Downloading RxNorm Current Prescribable Content (about 75 MB) from {RXNORM_URL}", file=sys.stderr)
    return fetch(RXNORM_URL, dest)


def fetch_ddinter(cache_dir: Path, refresh: bool = False, linked_only: bool = False) -> Path:
    target = cache_dir / "ddinter"
    for name in DDINTER_LINKED if linked_only else DDINTER_FILES:
        dest = target / name
        if dest.exists() and not refresh:
            continue
        print(f"Downloading {DDINTER_BASE}{name}", file=sys.stderr)
        try:
            fetch(DDINTER_BASE + name, dest)
        except RuntimeError as error:
            if name in DDINTER_LINKED:
                raise
            # The unlinked files are not promised by DDInter's download page.
            print(f"  WARNING: {name} is not available ({error}); continuing without it.", file=sys.stderr)
    if linked_only:
        for name in DDINTER_UNLINKED:  # do not let stale cached copies slip into the import
            (target / name).unlink(missing_ok=True)
    return target
