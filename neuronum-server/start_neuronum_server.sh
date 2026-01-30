#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="venv"
VLLM_LOG_FILE="vllm_server.log"
VLLM_PID_FILE=".vllm_pid"
SERVER_LOG_FILE="server.log"
SERVER_PID_FILE=".server_pid"
PLATFORM=""  # "nvidia" or "apple_silicon"

detect_platform() {
    echo "Detecting hardware platform..."

    if [[ "$(uname)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
        PLATFORM="apple_silicon"
        echo "Platform: Apple Silicon (macOS ARM64) → Using Ollama"
    else
        PLATFORM="nvidia"
        echo "Platform: Linux/NVIDIA GPU → Using vLLM"
    fi
}

show_logo() {
    local CYAN='\033[38;5;44m'
    local RESET='\033[0m'

    # Get terminal width, default to 80 if not available
    local term_width=$(tput cols 2>/dev/null || echo 80)
    local logo_width=80
    local padding=$(( (term_width - logo_width) / 2 ))

    # Ensure padding is not negative
    if [ $padding -lt 0 ]; then
        padding=0
    fi

    local spaces=$(printf '%*s' "$padding" '')

    echo -e "${CYAN}"
    echo ""
    while IFS= read -r line; do
        echo "${spaces}${line}"
    done << 'EOF'
                         .,:;+**?%%%SSSSSS%%%??*+;:,.
                     .;*%#@@@@@@@@@@@@@@@@@@@@@@@@@@#S?+,
                     :#@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@*
                      .:+?S#@@@@@@@@@@@@@@@@@@@@@@#S?*:.
                 .++,      .,::;+**????????**+;;:,.      ,++.
                 %@@@?,                                :%@@@%.
                ;@@@@@#;                              *@@@@@@;
                %@@@@@@@,                            +@@@@@@@?
                S@@@@@@@?                           .#@@@@@@@S
                S@@@@@@@?                           .#@@@@@@@S
                %@@@@@@@:                            *@@@@@@@%
                +@@@@@@+                             .?@@@@@@+
                .S@@@S:                                ;S@@@S.
                 ,??;.               ....               .;??,
                        .,:;+*??%%SSSSSSSSSSS%%?**+;:,.
                     ;%S#@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#%+.
                     ;%#@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#S*.
                       .,:+?%%S###@@@@@@@@@@###SS%?*;:.
                               ..,,,::::::,,,...
EOF
    echo ""
    echo "${spaces}   *****************************************************************************"
    echo "${spaces}   *****************************************************************************"
    echo "${spaces}   **                                                                         **"
    echo "${spaces}   **                    Neuronum - The Agentic Webserver                     **"
    echo "${spaces}   **                                                                         **"
    echo "${spaces}   **   ┌─────────────────────────────────────────────────────────────────┐   **"
    echo "${spaces}   **   │   Repository: github.com/neuronumcybernetics/neuronum-server    │   **"
    echo "${spaces}   **   │   Contact:    welcome@neuronum.net                              │   **"
    echo "${spaces}   **   │   Version:    2025.12.0.dev12                                   │   **"
    echo "${spaces}   **   └─────────────────────────────────────────────────────────────────┘   **"
    echo "${spaces}   **                                                                         **"
    echo "${spaces}   *****************************************************************************"
    echo "${spaces}   *****************************************************************************"
    echo ""
    echo -e "${RESET}"
}

check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        echo "Python $PYTHON_VERSION found"
        return 0
    else
        echo "Error: Python 3 is not installed. Please install Python 3.8 or higher."
        exit 1
    fi
}

create_venv() {
    echo "Setting up virtual environment..."

    if [ -d "$VENV_DIR" ]; then
        echo "Virtual environment already exists at $VENV_DIR"
        read -p "Do you want to recreate it? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Removing existing virtual environment..."
            rm -rf "$VENV_DIR"
        else
            echo "Using existing virtual environment"
            return 0
        fi
    fi

    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created at $VENV_DIR"
}

activate_venv() {
    echo "Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
    echo "Virtual environment activated"
}

install_dependencies() {
    echo "Installing dependencies..."

    echo -n "Upgrading pip... "
    pip install --upgrade pip --quiet
    echo "✓"

    if [ "$PLATFORM" == "apple_silicon" ]; then
        if [ ! -f "requirements_mac.txt" ]; then
            echo "Error: requirements_mac.txt not found"
            exit 1
        fi
        echo -n "Installing macOS dependencies from requirements_mac.txt... "
        pip install -r requirements_mac.txt --quiet
        echo "✓"
    else
        if [ ! -f "requirements.txt" ]; then
            echo "Error: requirements.txt not found"
            exit 1
        fi
        echo -n "Installing dependencies from requirements.txt... "
        pip install -r requirements.txt --quiet
        echo "✓"
    fi

    echo "All dependencies installed"
}

check_config() {
    echo "Checking configuration..."

    if [ ! -f "server.config" ]; then
        echo "Error: server.config not found"
        exit 1
    fi

    NEURONUM_DIR="$HOME/.neuronum"
    if [ ! -d "$NEURONUM_DIR" ] || [ ! -f "$NEURONUM_DIR/.env" ] || [ ! -f "$NEURONUM_DIR/private_key.pem" ]; then
        echo "Error: No Cell credentials found in $NEURONUM_DIR"
        echo "Please run 'neuronum create-cell' or 'neuronum connect-cell' first"
        exit 1
    fi

    echo "Cell credentials found in $NEURONUM_DIR"
    echo "Configuration file validated"
}

wait_for_model_download() {
    echo "Monitoring vLLM startup (this may take a while for large models)..."
    echo ""

    local vllm_host=$(python3 -c "from config import VLLM_HOST; print(VLLM_HOST)" 2>/dev/null)
    local vllm_port=$(python3 -c "from config import VLLM_PORT; print(VLLM_PORT)" 2>/dev/null)

    # Stream the log in real-time so user sees everything
    tail -f "$VLLM_LOG_FILE" 2>/dev/null &
    local tail_pid=$!

    # Wait until server is ready or process dies
    while true; do
        # Check if vLLM process died
        if [ -f "$VLLM_PID_FILE" ]; then
            local pid=$(cat "$VLLM_PID_FILE")
            if ! ps -p "$pid" > /dev/null 2>&1; then
                kill "$tail_pid" 2>/dev/null || true
                wait "$tail_pid" 2>/dev/null || true
                echo ""
                echo "Error: vLLM process died. Check $VLLM_LOG_FILE"
                return 1
            fi
        fi

        # Check if server is ready
        if curl -s -f "http://${vllm_host}:${vllm_port}/health" > /dev/null 2>&1; then
            kill "$tail_pid" 2>/dev/null || true
            wait "$tail_pid" 2>/dev/null || true
            echo ""
            echo "vLLM server is ready!"
            return 0
        fi

        sleep 2
    done
}

wait_for_vllm_ready() {
    local max_attempts=120
    local attempt=0

    local vllm_host=$(python3 -c "from config import VLLM_HOST; print(VLLM_HOST)")
    local vllm_port=$(python3 -c "from config import VLLM_PORT; print(VLLM_PORT)")
    local vllm_url="http://${vllm_host}:${vllm_port}/health"

    echo "Waiting for vLLM model to load and be ready..."
    echo "Health check endpoint: $vllm_url"

    while [ $attempt -lt $max_attempts ]; do
        # Check if vLLM process is still running
        if [ -f "$VLLM_PID_FILE" ]; then
            local pid=$(cat "$VLLM_PID_FILE")
            if ! ps -p "$pid" > /dev/null 2>&1; then
                echo "Error: vLLM process died. Check $VLLM_LOG_FILE for details."
                return 1
            fi
        fi

        if command -v curl &> /dev/null; then
            if curl -s -f "$vllm_url" > /dev/null 2>&1; then
                echo "vLLM server is ready and accepting requests"
                return 0
            fi
        elif command -v wget &> /dev/null; then
            if wget -q --spider "$vllm_url" 2>/dev/null; then
                echo "vLLM server is ready and accepting requests"
                return 0
            fi
        else
            echo "Warning: Neither curl nor wget found. Skipping health check."
            return 0
        fi

        attempt=$((attempt + 1))
        echo "Attempt $attempt/$max_attempts: Model still loading..."
        sleep 5
    done

    echo "Warning: vLLM server did not become ready after $((max_attempts * 5)) seconds"
    echo "The model may still be loading. Check $VLLM_LOG_FILE for details."
    return 1
}

start_vllm() {
    echo "Starting vLLM server..."

    if [ -f "$VLLM_PID_FILE" ]; then
        OLD_PID=$(cat "$VLLM_PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            echo "vLLM server is already running (PID: $OLD_PID)"
            read -p "Do you want to restart it? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "Stopping existing vLLM server..."
                kill "$OLD_PID" 2>/dev/null || true
                sleep 2
            else
                echo "Using existing vLLM server"
                return 0
            fi
        fi
    fi

    echo "Starting vLLM server in background..."
    echo "Log file: $VLLM_LOG_FILE"

    nohup python start_vllm_server.py > "$VLLM_LOG_FILE" 2>&1 &
    VLLM_PID=$!
    echo "$VLLM_PID" > "$VLLM_PID_FILE"

    echo "Checking if vLLM process started (PID: $VLLM_PID)..."
    sleep 3

    if ! ps -p "$VLLM_PID" > /dev/null 2>&1; then
        echo "Error: vLLM server process failed to start. Check $VLLM_LOG_FILE for details."
        exit 1
    fi

    echo "vLLM process running (PID: $VLLM_PID)"

    # Stream log and wait for server to be ready (handles both download and loading)
    wait_for_model_download
}

start_ollama() {
    echo "Setting up Ollama..."

    # Check if Ollama is installed
    if ! command -v ollama &> /dev/null; then
        echo "Error: Ollama is not installed."
        echo "Install it from: https://ollama.com/download"
        echo "  or run: brew install ollama"
        exit 1
    fi

    echo "Ollama found: $(ollama --version 2>/dev/null || echo 'installed')"

    # Check if Ollama is already running
    if curl -s -f "http://127.0.0.1:11434/api/tags" > /dev/null 2>&1; then
        echo "Ollama is already running"
    else
        echo "Starting Ollama server..."
        ollama serve > /dev/null 2>&1 &
        sleep 3

        if ! curl -s -f "http://127.0.0.1:11434/api/tags" > /dev/null 2>&1; then
            echo "Error: Failed to start Ollama server"
            exit 1
        fi
        echo "Ollama server started"
    fi

    # Pull the model if not already available
    local ollama_model=$(python3 -c "from config import OLLAMA_MODEL_NAME; print(OLLAMA_MODEL_NAME)" 2>/dev/null)
    if [ -z "$ollama_model" ]; then
        ollama_model="llama3.2:3b"
    fi

    echo "Checking model: $ollama_model"

    # Check if model is already pulled
    if ollama list 2>/dev/null | grep -q "$ollama_model"; then
        echo "Model '$ollama_model' is already available"
    else
        echo "Pulling model '$ollama_model' (this may take a while)..."
        ollama pull "$ollama_model"
        echo "Model '$ollama_model' pulled successfully"
    fi

    echo "Ollama ready with model: $ollama_model"
}

start_server() {
    echo "Starting Neuronum Server..."

    if [ -f "$SERVER_PID_FILE" ]; then
        OLD_PID=$(cat "$SERVER_PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            echo "Neuronum Server is already running (PID: $OLD_PID)"
            read -p "Do you want to restart it? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "Stopping existing Neuronum Server..."
                kill "$OLD_PID" 2>/dev/null || true
                sleep 2
            else
                echo "Using existing Neuronum Server"
                return 0
            fi
        fi
    fi

    echo "Starting Neuronum Server in background..."
    echo "Log file: $SERVER_LOG_FILE"

    nohup python neuronum_server.py > "$SERVER_LOG_FILE" 2>&1 &
    SERVER_PID=$!
    echo "$SERVER_PID" > "$SERVER_PID_FILE"

    echo "Waiting for Neuronum Server to start (PID: $SERVER_PID)..."
    sleep 3

    if ps -p "$SERVER_PID" > /dev/null 2>&1; then
        echo "Neuronum Server started successfully (PID: $SERVER_PID)"
        echo "You can now safely close this terminal session"
        echo "To view logs: tail -f $SERVER_LOG_FILE"
        echo "To stop the server: neuronum stop-agent"
    else
        echo "Error: Neuronum Server failed to start. Check $SERVER_LOG_FILE for details."
        exit 1
    fi
}

cleanup() {
    if [ $? -ne 0 ]; then
        echo "Cleanup (error occurred)..."

        if [ -f "$SERVER_PID_FILE" ]; then
            SERVER_PID=$(cat "$SERVER_PID_FILE")
            if ps -p "$SERVER_PID" > /dev/null 2>&1; then
                echo "Stopping Neuronum Server (PID: $SERVER_PID)..."
                kill "$SERVER_PID" 2>/dev/null || true
            fi
            rm -f "$SERVER_PID_FILE"
        fi

        if [ -f "$VLLM_PID_FILE" ]; then
            VLLM_PID=$(cat "$VLLM_PID_FILE")
            if ps -p "$VLLM_PID" > /dev/null 2>&1; then
                echo "Stopping vLLM server (PID: $VLLM_PID)..."
                kill "$VLLM_PID" 2>/dev/null || true
            fi
            rm -f "$VLLM_PID_FILE"
        fi

        echo "Cleanup complete"
    fi
}

trap cleanup ERR

main() {
    echo "Neuronum Server Setup"
    echo ""

    detect_platform
    check_python
    create_venv
    activate_venv
    install_dependencies
    check_config

    if [ "$PLATFORM" == "apple_silicon" ]; then
        start_ollama
    else
        start_vllm
    fi

    start_server

    echo ""
    show_logo
}

main
