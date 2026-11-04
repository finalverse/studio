# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Isolated interpreter entry; external networking never runs in Blender threads."""
from pathlib import Path
import resource
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
resource.setrlimit(resource.RLIMIT_FSIZE, (2*1024*1024, 2*1024*1024))


def timeout(_signal, _frame):
    raise TimeoutError('Provider wall limit')


signal.signal(signal.SIGALRM, timeout)
signal.alarm(120)
from finalverse_creation.providers import main
main()
