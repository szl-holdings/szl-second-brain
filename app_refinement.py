# SPDX-License-Identifier: Apache-2.0
"""Compatibility entry point; all web routes use the canonical application."""
from second_brain.web import app

if __name__ == "__main__":
    from second_brain.web import main
    main()
