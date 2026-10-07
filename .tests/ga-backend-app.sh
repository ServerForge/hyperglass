#!/usr/bin/env bash

LOG_FILE="$HOME/hyperglass-ci.log"
touch /tmp/hyperglass.log

. .venv/bin/activate

echo "[INFO] Starting setup..."
python3 -m hyperglass.console setup &>$LOG_FILE

if [[ ! $? == 0 ]]; then
    echo "[ERROR] Failed to set up hyperglass."
    cat $LOG_FILE
    exit 1
else
    echo "[SUCCESS] Setup completed."
fi

echo "[INFO] Copying directives.yaml file..."
cp ./.tests/directives.yaml $HOME/hyperglass/directives.yaml

echo "[INFO] Copying devices.yaml file..."
cp ./.tests/devices.yaml $HOME/hyperglass/devices.yaml

echo "[INFO] Starting UI build."
python3 -m hyperglass.console build-ui &>$LOG_FILE

if [[ ! $? == 0 ]]; then
    echo "[ERROR] Failed to build hyperglass ui."
    cat /tmp/hyperglass.log
    cat $LOG_FILE
    exit 1
else
    echo "[SUCCESS] UI build completed."
fi

echo "[INFO] Starting hyperglass..."
python3 -m hyperglass.console start &>$LOG_FILE &
HYPERGLASS_PID=$!
trap 'kill $HYPERGLASS_PID 2>/dev/null' EXIT

# Wait for hyperglass to respond, failing if it exits or doesn't respond within 2 minutes.
STATUS="000"
for _ in $(seq 1 60); do
    if ! kill -0 $HYPERGLASS_PID 2>/dev/null; then
        break
    fi
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001)
    if [[ ! "$STATUS" == "000" ]]; then
        break
    fi
    sleep 2
done

if [[ "$STATUS" == "000" ]]; then
    echo "[ERROR] Failed to start hyperglass."
    cat /tmp/hyperglass.log
    cat $LOG_FILE
    exit 1
else
    echo "[SUCCESS] Started hyperglass."
fi

echo "[INFO] Running HTTP test..."
echo "[INFO] Status code: $STATUS"

if [[ ! "$STATUS" == "200" ]]; then
    echo "[ERROR] HTTP test failed."
    cat /tmp/hyperglass.log
    cat $LOG_FILE
    exit 1
fi

echo "[SUCCESS] Tests ran successfully."
exit 0
