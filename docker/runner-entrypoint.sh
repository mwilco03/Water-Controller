#!/bin/bash
# GitHub Actions Runner Entrypoint
# Registers the runner and starts it

set -e

# Required environment variables
: "${GITHUB_OWNER:?GITHUB_OWNER is required}"
: "${GITHUB_REPO:?GITHUB_REPO is required}"
: "${GITHUB_TOKEN:?GITHUB_TOKEN is required}"

# Optional configuration
RUNNER_NAME="${RUNNER_NAME:-$(hostname)}"
RUNNER_LABELS="${RUNNER_LABELS:-wtc-deploy}"
RUNNER_WORKDIR="${RUNNER_WORKDIR:-_work}"

echo "============================================"
echo "GitHub Actions Self-Hosted Runner"
echo "============================================"
echo "Repository: ${GITHUB_OWNER}/${GITHUB_REPO}"
echo "Runner Name: ${RUNNER_NAME}"
echo "Labels: ${RUNNER_LABELS}"
echo "============================================"

# Get registration token from GitHub API
echo "Obtaining registration token..."
REG_TOKEN=$(curl -sX POST \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/runners/registration-token" \
    | jq -r '.token')

if [ "$REG_TOKEN" == "null" ] || [ -z "$REG_TOKEN" ]; then
    echo "ERROR: Failed to get registration token"
    echo "Make sure your GITHUB_TOKEN has the required permissions:"
    echo "  - repo (full control)"
    echo "  - admin:repo_hook or Administration: Read and write"
    exit 1
fi

# Configure the runner (if not already configured)
if [ ! -f .runner ]; then
    echo "Configuring runner..."
    ./config.sh \
        --url "https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}" \
        --token "${REG_TOKEN}" \
        --name "${RUNNER_NAME}" \
        --labels "${RUNNER_LABELS}" \
        --work "${RUNNER_WORKDIR}" \
        --unattended \
        --replace
else
    echo "Runner already configured"
fi

# Cleanup function to deregister runner on exit
cleanup() {
    echo ""
    echo "Caught signal, removing runner..."
    ./config.sh remove --token "${REG_TOKEN}" || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start the runner
echo "Starting runner..."
./run.sh &

# Wait for runner process
wait $!
