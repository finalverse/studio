# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Render worker isolation derived from accepted Core G0's supervisor policy."""
import json
import os
from pathlib import Path
import plistlib
import resource
import signal
import subprocess
import sys
import time

app, work, project = [str(Path(p).resolve()) for p in sys.argv[1:4]]
engine = str(Path(app)/'Contents/MacOS/Finalverse Studio')
worker = str(Path(app)/'Contents/Resources/5.4/scripts/modules/finalverse_creation/render_worker.py')
parent = os.getppid()
bundle = plistlib.loads((Path(app)/'Contents/Info.plist').read_bytes())['CFBundleIdentifier']
if bundle not in {'org.finalverse.studio', 'org.finalverse.studio.s1'}:
    raise ValueError('Unknown Studio development bundle identity')
cache = Path(subprocess.check_output(['/usr/bin/getconf', 'DARWIN_USER_CACHE_DIR'], text=True).strip()).resolve()/bundle
graphics_caches = [cache/'com.apple.metalfe', cache/'com.apple.gpuarchiver']
for path in graphics_caches: path.mkdir(parents=True, exist_ok=True)


def cache_bytes():
    files = [p for root in graphics_caches for p in root.rglob('*') if p.is_file()]
    if len(files) > 4096: raise ValueError('Graphics cache entry budget')
    return sum(p.stat().st_size for p in files)


initial_cache = cache_bytes()
resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
resource.setrlimit(resource.RLIMIT_FSIZE, (128*1024*1024, 128*1024*1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
quote = lambda p: '"' + p.replace('\\', '\\\\').replace('"', '\\"') + '"'
policy = '''(version 1)(deny default)(import "system.sb")
(allow iokit-open (iokit-user-client-class "AGXDeviceUserClient") (iokit-user-client-class "AGXSharedUserClient")
 (iokit-user-client-class "IOSurfaceRootUserClient"))
(allow process*) (allow file-read-metadata) (allow sysctl-read) (allow mach-lookup)
(allow file-map-executable (subpath "/System") (subpath "/usr") (subpath "/bin") (subpath %s))
(allow file-read* (subpath "/System") (subpath "/usr") (subpath "/bin")
 (literal "/dev/null") (literal "/dev/random") (literal "/dev/urandom") (subpath %s) (subpath %s) (literal %s))
(allow file-write* (subpath %s) (literal "/dev/null"))
''' % (quote(app), quote(app), quote(work), quote(project), quote(work))
for path in graphics_caches:
    policy += '(allow file-read* file-write* file-issue-extension (subpath %s))\n' % quote(str(path))
policy += '(allow file-issue-extension (require-all (extension-class "com.apple.app-sandbox.read") (subpath %s)))\n' % quote(app)
child = subprocess.Popen(['/usr/bin/sandbox-exec', '-p', policy, engine, '--background',
    '--factory-startup', '--disable-autoexec', '--threads', '2', project, '--python-exit-code', '1', '--python', worker, '--', work],
    env={'PATH': '/usr/bin:/bin', 'HOME': work, 'TMPDIR': work, 'PYTHONDONTWRITEBYTECODE': '1'})
started = time.monotonic(); peak = 0
while child.poll() is None:
    data = subprocess.check_output(['/bin/ps', '-axo', 'pid,ppid,rss'], text=True)
    records = [tuple(map(int, line.split())) for line in data.splitlines()[1:] if len(line.split()) == 3]
    descendants = {os.getpid()}
    for _ in range(16):
        before = len(descendants)
        descendants.update(pid for pid, ppid, rss in records if ppid in descendants)
        if before == len(descendants): break
    rss = sum(rss*1024 for pid, ppid, rss in records if pid in descendants)
    peak = max(peak, rss)
    elapsed = time.monotonic()-started
    growth = max(0, cache_bytes()-initial_cache)
    metrics = {'wall_seconds': elapsed, 'peak_rss_bytes': peak, 'memory_limit_bytes': 1024**3,
               'wall_limit_seconds': 60, 'network': 'denied', 'credentials': 'cleared',
               'graphics_cache_paths': [str(p) for p in graphics_caches],
               'graphics_cache_growth_bytes': growth, 'graphics_cache_growth_limit_bytes': 128*1024*1024}
    (Path(work)/'render-metrics.json').write_text(json.dumps(metrics))
    if os.getppid() != parent or elapsed > 60 or rss > 1024**3 or growth > 128*1024*1024:
        os.killpg(os.getpgrp(), signal.SIGKILL)
    time.sleep(.2)
sys.exit(child.returncode)
