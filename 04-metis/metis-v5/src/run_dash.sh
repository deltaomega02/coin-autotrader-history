#!/bin/bash
cd YOUR_HOME_DIR/metis-v4
set -a; source v4.env; set +a
exec YOUR_HOME_DIR/ATHENA/athena/bin/python -m streamlit run dashboard.py \
  --server.port 8501 --server.address 0.0.0.0 --server.headless true \
  --browser.gatherUsageStats false
