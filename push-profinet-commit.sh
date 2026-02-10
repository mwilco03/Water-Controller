#!/bin/bash
# Push the PROFINET cyclic data exchange commit to origin
# Run this after logging in with your GitHub credentials
#
# Commit: c746b1d feat(profinet): complete PROFINET cyclic data exchange (17 bugs fixed)
# 18 files changed, 2731 insertions(+), 366 deletions(-)

set -e
cd /opt/water-controller

echo "=== Current state ==="
git log --oneline -3
echo ""
git status
echo ""

echo "=== Pushing to origin/main ==="
git push origin main

echo ""
echo "=== Done! Verify at: https://github.com/mwilco03/Water-Controller ==="
