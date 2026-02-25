#!/bin/bash
set -e

# Enable the monitoring loop when running as the full agent.
# When AGENT_AUTO_MONITOR is not set (e.g. dev/frontend-only), the API
# starts without health checks, diagnosis, recovery, or Telegram notifications.
export AGENT_AUTO_MONITOR=true

uvicorn agent.api:app --host 0.0.0.0 --port ${AGENT_PORT:-8001}
