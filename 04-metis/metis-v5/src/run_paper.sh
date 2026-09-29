#!/bin/bash
cd YOUR_HOME_DIR/metis-v4
set -a; source v4.env; set +a
exec YOUR_HOME_DIR/metis-f2/venv/bin/python -u paper_leverage.py
