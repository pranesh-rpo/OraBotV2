#!/bin/bash

# Ora Ads Bot Manager
# Quick script to manage bot instances

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BOT_NAME="Ora Ads"
LOCK_FILE="/tmp/ora_ads.lock"
PID_FILE="$SCRIPT_DIR/bot.pid"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}    Ora Ads Bot Manager${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
}

check_status() {
    if [ -f "$LOCK_FILE" ]; then
        PID=$(cat "$LOCK_FILE" 2>/dev/null)
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Bot is running (PID: $PID)${NC}"
            return 0
        else
            echo -e "${YELLOW}⚠️  Lock file exists but process not found${NC}"
            echo -e "${YELLOW}   Cleaning stale lock...${NC}"
            rm -f "$LOCK_FILE"
            return 1
        fi
    else
        echo -e "${RED}❌ Bot is not running${NC}"
        return 1
    fi
}

start_bot() {
    echo -e "${BLUE}Starting $BOT_NAME...${NC}"
    
    if check_status > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Bot is already running!${NC}"
        return 1
    fi
    
    cd "$SCRIPT_DIR"
    
    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}⚠️  Virtual environment not found. Creating...${NC}"
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
    else
        source venv/bin/activate
    fi
    
    # Check if .env exists
    if [ ! -f ".env" ]; then
        echo -e "${RED}❌ .env file not found!${NC}"
        echo -e "${YELLOW}💡 Copy .env.example to .env and configure it${NC}"
        return 1
    fi
    
    # Start bot in background
    nohup python3 main.py > logs/bot.log 2>&1 &
    BOT_PID=$!
    echo $BOT_PID > "$PID_FILE"
    
    sleep 2
    
    if ps -p $BOT_PID > /dev/null; then
        echo -e "${GREEN}✅ Bot started successfully (PID: $BOT_PID)${NC}"
        echo -e "${BLUE}💡 View logs: tail -f logs/bot.log${NC}"
    else
        echo -e "${RED}❌ Failed to start bot${NC}"
        echo -e "${YELLOW}💡 Check logs/bot.log for errors${NC}"
        return 1
    fi
}

stop_bot() {
    echo -e "${BLUE}Stopping $BOT_NAME...${NC}"
    
    if [ -f "$LOCK_FILE" ]; then
        PID=$(cat "$LOCK_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${YELLOW}Sending SIGTERM to PID $PID...${NC}"
            kill -15 "$PID"
            
            # Wait for graceful shutdown
            for i in {1..10}; do
                if ! ps -p "$PID" > /dev/null 2>&1; then
                    echo -e "${GREEN}✅ Bot stopped gracefully${NC}"
                    rm -f "$LOCK_FILE" "$PID_FILE"
                    return 0
                fi
                sleep 1
            done
            
            # Force kill if still running
            echo -e "${YELLOW}⚠️  Forcing shutdown...${NC}"
            kill -9 "$PID" 2>/dev/null
            rm -f "$LOCK_FILE" "$PID_FILE"
            echo -e "${GREEN}✅ Bot stopped (forced)${NC}"
        else
            echo -e "${YELLOW}⚠️  Process not found, cleaning lock file${NC}"
            rm -f "$LOCK_FILE" "$PID_FILE"
        fi
    else
        echo -e "${RED}❌ Bot is not running${NC}"
    fi
}

restart_bot() {
    echo -e "${BLUE}Restarting $BOT_NAME...${NC}"
    stop_bot
    sleep 2
    start_bot
}

view_logs() {
    if [ ! -f "logs/bot.log" ]; then
        echo -e "${RED}❌ Log file not found${NC}"
        return 1
    fi
    
    echo -e "${BLUE}Viewing logs (Ctrl+C to exit)...${NC}"
    tail -f logs/bot.log
}

kill_all() {
    echo -e "${YELLOW}⚠️  Killing all bot instances...${NC}"
    
    # Find all python processes running main.py
    PIDS=$(pgrep -f "python.*main.py")
    
    if [ -z "$PIDS" ]; then
        echo -e "${YELLOW}No bot processes found${NC}"
    else
        for PID in $PIDS; do
            echo -e "${YELLOW}Killing PID: $PID${NC}"
            kill -9 "$PID" 2>/dev/null
        done
        echo -e "${GREEN}✅ All instances killed${NC}"
    fi
    
    # Clean lock files
    rm -f "$LOCK_FILE" "$PID_FILE"
}

show_menu() {
    print_header
    check_status
    echo ""
    echo -e "${BLUE}Commands:${NC}"
    echo "  start     - Start the bot"
    echo "  stop      - Stop the bot"
    echo "  restart   - Restart the bot"
    echo "  status    - Check bot status"
    echo "  logs      - View live logs"
    echo "  kill-all  - Force kill all instances"
    echo "  help      - Show this menu"
    echo ""
}

# Create logs directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/logs"

# Main command handling
case "$1" in
    start)
        print_header
        start_bot
        ;;
    stop)
        print_header
        stop_bot
        ;;
    restart)
        print_header
        restart_bot
        ;;
    status)
        print_header
        check_status
        ;;
    logs)
        view_logs
        ;;
    kill-all)
        print_header
        kill_all
        ;;
    help|"")
        show_menu
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $1${NC}"
        show_menu
        exit 1
        ;;
esac