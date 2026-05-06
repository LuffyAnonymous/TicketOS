#!/bin/bash
pkill -f "nokey@localhost.run" || true

while true; do
    echo "Starting tunnel..."
    stdbuf -oL ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -R 80:localhost:5000 nokey@localhost.run > /tmp/tunnel.log 2>&1 &
    SSH_PID=$!
    
    sleep 5
    URL=$(grep -o 'https://[a-zA-Z0-9]*\.lhr\.life' /tmp/tunnel.log | tail -n 1)
    
    if [ ! -z "$URL" ]; then
        echo "Tunnel started at: $URL"
        python3 -c "import sys, os; sys.path.append(os.getcwd()); from services.telegram_service import send_telegram; send_telegram('🌐 NEW OrderHub Remote URL:\n\n' + '$URL')"
    fi
    
    wait $SSH_PID
    echo "Tunnel disconnected. Restarting in 5 seconds..."
    sleep 5
done
