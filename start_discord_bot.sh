#!/bin/bash

# Directory where the bot is located
BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_SCRIPT="discord_poker_bot.py"
PID_FILE="$BOT_DIR/discord_bot.pid"
LOG_DIR="$BOT_DIR/logs"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Function to check if bot is running
is_bot_running() {
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# Function to start the bot
start_bot() {
    echo "Starting Discord bot..."
    
    # Activate virtual environment if it exists
    if [ -d "env" ]; then
        source env/bin/activate
    fi
    
    # Start the bot in background
    nohup python3 "$BOT_SCRIPT" > "$LOG_DIR/discord_bot.log" 2>&1 & echo $! > "$PID_FILE"
    
    # Wait a moment to check if process is still running
    sleep 2
    if is_bot_running; then
        echo "Discord bot started successfully! (PID: $(cat "$PID_FILE"))"
        echo "Logs are being written to: $LOG_DIR/discord_bot.log"
    else
        echo "Failed to start Discord bot. Check logs for details."
        rm -f "$PID_FILE"
        exit 1
    fi
}

# Function to stop the bot
stop_bot() {
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        echo "Stopping Discord bot (PID: $pid)..."
        kill "$pid"
        rm -f "$PID_FILE"
        echo "Discord bot stopped."
    else
        echo "No running Discord bot found."
    fi
}

# Function to show status
status_bot() {
    if is_bot_running; then
        echo "Discord bot is running (PID: $(cat "$PID_FILE"))"
        echo "Log file: $LOG_DIR/discord_bot.log"
    else
        echo "Discord bot is not running"
    fi
}

# Command line argument handling
case "$1" in
    start)
        if is_bot_running; then
            echo "Discord bot is already running! (PID: $(cat "$PID_FILE"))"
            exit 1
        fi
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        stop_bot
        sleep 2
        start_bot
        ;;
    status)
        status_bot
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac

exit 0 