# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
import sys
from .gui import run_gui
from .cli import main as cli_main

def main():
    if len(sys.argv) > 1:
        # If command line arguments are provided, run CLI
        cli_main()
    else:
        # Otherwise, run GUI
        run_gui()

if __name__ == '__main__':
    main() 