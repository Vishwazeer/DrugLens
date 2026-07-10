#!/usr/bin/env bash

# Exit on error
set -e

echo "=== DrugLens AMD Pod Setup ==="

# 1. Verify ROCm / AMD GPU
echo "Checking AMD GPU status..."
if command -v rocm-smi &> /dev/null; then
    rocm-smi
else
    echo "WARNING: rocm-smi not found. Checking rocminfo..."
    if command -v rocminfo &> /dev/null; then
        rocminfo | grep -i "Name:" | head -n 5
    else
        echo "ERROR: Neither rocm-smi nor rocminfo found. Are ROCm drivers installed?"
    fi
fi

# 2. Load env variables from .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "ERROR: .env file not found. Please create it first."
    exit 1
fi

if [ -z "$HF_TOKEN" ]; then
    echo "ERROR: HF_TOKEN is not set in .env."
    exit 1
fi

# 3. HF Login
echo "Logging into Hugging Face..."
pip install -q huggingface_hub
huggingface-cli login --token "$HF_TOKEN" --add-to-git-credential

# 4. Choose Execution Path
echo ""
echo "Select execution mode:"
echo "1) Docker Compose (Requires Docker + ROCm container support)"
echo "2) Native Python/vLLM (Recommended for pre-configured AMD Pods)"
read -p "Enter choice [1-2]: " choice

if [ "$choice" == "1" ]; then
    echo "Starting services via Docker Compose..."
    docker compose --profile gpu up --build -d
    echo "Services started in background. Check logs with 'docker compose logs -f'"
else
    # Native Python setup
    echo "Installing vllm..."
    pip install vllm -q

    # Use tmux or screen if available, otherwise runs in bg
    echo "Starting MedGemma on port 8001..."
    nohup python3 -m vllm.entrypoints.openai.api_server \
        --model google/medgemma-4b-it \
        --port 8001 \
        --max-model-len 4096 \
        --gpu-memory-utilization 0.45 > medgemma.log 2>&1 &
    
    echo "Starting TxGemma on port 8002..."
    nohup python3 -m vllm.entrypoints.openai.api_server \
        --model google/txgemma-2b-it \
        --port 8002 \
        --max-model-len 2048 \
        --gpu-memory-utilization 0.45 > txgemma.log 2>&1 &

    echo "=== Models starting in background ==="
    echo "Monitor MedGemma logs: tail -f medgemma.log"
    echo "Monitor TxGemma logs:  tail -f txgemma.log"
fi
