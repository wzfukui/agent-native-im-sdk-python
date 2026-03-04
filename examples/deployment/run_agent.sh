#!/bin/bash
# Agent runner script with auto-restart and logging

# Configuration
AGENT_NAME="smart-assistant"
AGENT_DIR="/opt/agents/$AGENT_NAME"
LOG_DIR="/var/log/agents"
PID_FILE="/var/run/$AGENT_NAME.pid"

# Create directories if needed
mkdir -p "$LOG_DIR"
mkdir -p "$AGENT_DIR/memory"

# Function to check if agent is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

# Function to start the agent
start_agent() {
    if is_running; then
        echo "Agent is already running (PID: $(cat $PID_FILE))"
        return 1
    fi

    echo "Starting $AGENT_NAME..."

    # Activate virtual environment if exists
    if [ -f "$AGENT_DIR/venv/bin/activate" ]; then
        source "$AGENT_DIR/venv/bin/activate"
    fi

    # Export environment variables
    export BOT_TOKEN=$(cat "$AGENT_DIR/.env" | grep BOT_TOKEN | cut -d '=' -f2)
    export OPENAI_API_KEY=$(cat "$AGENT_DIR/.env" | grep OPENAI_API_KEY | cut -d '=' -f2)
    export AGENT_BASE_URL=${AGENT_BASE_URL:-"http://localhost:9800"}

    # Start the agent with logging
    nohup python3 "$AGENT_DIR/agent.py" \
        >> "$LOG_DIR/$AGENT_NAME.log" 2>&1 &

    echo $! > "$PID_FILE"
    echo "Agent started (PID: $(cat $PID_FILE))"
    echo "Logs: tail -f $LOG_DIR/$AGENT_NAME.log"
}

# Function to stop the agent
stop_agent() {
    if ! is_running; then
        echo "Agent is not running"
        return 1
    fi

    echo "Stopping $AGENT_NAME..."
    PID=$(cat "$PID_FILE")
    kill "$PID"

    # Wait for graceful shutdown
    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done

    # Force kill if still running
    if kill -0 "$PID" 2>/dev/null; then
        echo "Force stopping..."
        kill -9 "$PID"
    fi

    rm -f "$PID_FILE"
    echo "Agent stopped"
}

# Function to restart the agent
restart_agent() {
    stop_agent
    sleep 2
    start_agent
}

# Function to show status
status() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo "Agent $AGENT_NAME is running (PID: $PID)"
        echo "Memory usage: $(ps -o rss= -p $PID | awk '{print $1/1024 " MB"}')"
        echo "CPU usage: $(ps -o %cpu= -p $PID)%"
        echo "Uptime: $(ps -o etime= -p $PID)"
    else
        echo "Agent $AGENT_NAME is not running"
    fi
}

# Function to tail logs
logs() {
    tail -f "$LOG_DIR/$AGENT_NAME.log"
}

# Main command handler
case "$1" in
    start)
        start_agent
        ;;
    stop)
        stop_agent
        ;;
    restart)
        restart_agent
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac