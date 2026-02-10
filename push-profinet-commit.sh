#!/bin/bash
# Push all PROFINET commits to origin
# Run this after logging in with your GitHub credentials
#
# Commits (3 ahead of origin):
#   c746b1d feat(profinet): complete PROFINET cyclic data exchange (17 bugs fixed)
#   2a5628b New diag files
#   f50bb34 fix(profinet): enable full module Connect with IOCR buffer reallocation

set -e
cd /opt/water-controller

echo "=== Current state ==="
git log --oneline -5
echo ""
git status
echo ""

echo "=== Pushing to origin/main ==="
git push origin main

echo ""
echo "=== Done! Verify at: https://github.com/mwilco03/Water-Controller ==="
