#!/bin/bash

# Ora Bot Kill and Restart Script
# This script kills existing instances and starts the bot fresh
source src/bin/activate
clear
echo "🔍 Checking for existing Ora Bot instances..."

# Find and kill existing Python processes running main.py
PIDS=$(ps aux | grep 'python.*main.py' | grep -v grep | awk '{print $2}')

if [ -n "$PIDS" ]; then
    echo "📍 Found running instances: $PIDS"
    echo "⏹️  Killing existing processes..."
    
    for PID in $PIDS; do
        echo "  🔄 Killing PID: $PID"
        kill -9 "$PID" 2>/dev/null
    done
    
    echo "✅ All instances killed"
else
    echo "ℹ️  No running instances found"
fi

# Remove lock file if it exists
if [ -f "/tmp/ora_ads.lock" ]; then
    echo "🔓 Removing lock file..."
    rm -f /tmp/ora_ads.lock
    echo "✅ Lock file removed"
fi

# Wait a moment for processes to fully terminate
echo "⏳ Waiting for processes to terminate..."
sleep 2

# Check if any processes are still running
REMAINING=$(ps aux | grep 'python.*main.py' | grep -v grep | wc -l)
if [ "$REMAINING" -gt 0 ]; then
    echo "⚠️  Warning: Some processes may still be running"
    echo "🔍 Checking again..."
    ps aux | grep 'python.*main.py' | grep -v grep
else
    echo "✅ All processes successfully terminated"
fi

echo ""
echo "🚀 Starting Ora Bot..."
echo "=========================="

# Start the bot
python main.py
