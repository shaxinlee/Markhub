#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markhub backend entrypoint.

Run with:
    python backend/server.py --port 8787
"""

from __future__ import annotations

from features.layout_analysis import main


if __name__ == "__main__":
    raise SystemExit(main())
