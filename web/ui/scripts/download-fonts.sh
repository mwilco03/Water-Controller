#!/bin/bash
#
# Download fonts for air-gapped deployment
# Run this script during build or before deploying to isolated network
#
# Usage: ./scripts/download-fonts.sh
#

set -e

FONT_DIR="$(dirname "$0")/../public/fonts"
mkdir -p "$FONT_DIR"

echo "Downloading fonts for air-gapped deployment..."

# Inter font (Google Fonts)
INTER_VERSION="3.19"
INTER_BASE="https://github.com/rsms/inter/releases/download/v${INTER_VERSION}"

echo "Downloading Inter font..."
curl -sL "${INTER_BASE}/Inter-${INTER_VERSION}.zip" -o /tmp/inter.zip
unzip -qo /tmp/inter.zip -d /tmp/inter

# Copy woff2 files (smallest, best compression)
cp /tmp/inter/Inter\ Desktop/Inter-Regular.otf "$FONT_DIR/" 2>/dev/null || true
cp /tmp/inter/Inter\ Web/Inter-Regular.woff2 "$FONT_DIR/" 2>/dev/null || true
cp /tmp/inter/Inter\ Web/Inter-Regular.woff "$FONT_DIR/" 2>/dev/null || true
cp /tmp/inter/Inter\ Web/Inter-Medium.woff2 "$FONT_DIR/" 2>/dev/null || true
cp /tmp/inter/Inter\ Web/Inter-Medium.woff "$FONT_DIR/" 2>/dev/null || true
cp /tmp/inter/Inter\ Web/Inter-SemiBold.woff2 "$FONT_DIR/" 2>/dev/null || true
cp /tmp/inter/Inter\ Web/Inter-SemiBold.woff "$FONT_DIR/" 2>/dev/null || true
cp /tmp/inter/Inter\ Web/Inter-Bold.woff2 "$FONT_DIR/" 2>/dev/null || true
cp /tmp/inter/Inter\ Web/Inter-Bold.woff "$FONT_DIR/" 2>/dev/null || true

rm -rf /tmp/inter /tmp/inter.zip

# JetBrains Mono font
JBM_VERSION="2.304"
JBM_BASE="https://github.com/JetBrains/JetBrainsMono/releases/download/v${JBM_VERSION}"

echo "Downloading JetBrains Mono font..."
curl -sL "${JBM_BASE}/JetBrainsMono-${JBM_VERSION}.zip" -o /tmp/jbmono.zip
unzip -qo /tmp/jbmono.zip -d /tmp/jbmono

# Copy woff2 files
cp /tmp/jbmono/fonts/webfonts/JetBrainsMono-Regular.woff2 "$FONT_DIR/" 2>/dev/null || true
cp /tmp/jbmono/fonts/webfonts/JetBrainsMono-Medium.woff2 "$FONT_DIR/" 2>/dev/null || true
cp /tmp/jbmono/fonts/webfonts/JetBrainsMono-SemiBold.woff2 "$FONT_DIR/" 2>/dev/null || true

rm -rf /tmp/jbmono /tmp/jbmono.zip

echo "Fonts downloaded to: $FONT_DIR"
ls -la "$FONT_DIR"/*.woff2 2>/dev/null || echo "Note: woff2 files may need manual download"

echo ""
echo "Done! Fonts are ready for air-gapped deployment."
