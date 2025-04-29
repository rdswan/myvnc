# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0
try:
    import msal
    print("MSAL is installed")
except ImportError:
    print("MSAL is not installed") 