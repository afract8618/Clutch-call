#!/bin/sh
# Runs before the Xcode project is generated: bundles the web game and builds the icon catalog.
set -e
cd "$(dirname "$0")"
rm -rf web && mkdir -p web
cp ../index.html ../drives_auto.json ../icon-192.png ../icon-512.png ../apple-touch-icon.png ../favicon-32.png ../manifest.webmanifest web/
mkdir -p Assets.xcassets/AppIcon.appiconset
cp ../icon-1024.png Assets.xcassets/AppIcon.appiconset/AppIcon.png
cat > Assets.xcassets/Contents.json <<'JSON'
{ "info" : { "author" : "xcode", "version" : 1 } }
JSON
cat > Assets.xcassets/AppIcon.appiconset/Contents.json <<'JSON'
{
  "images" : [
    { "filename" : "AppIcon.png", "idiom" : "universal", "platform" : "ios", "size" : "1024x1024" }
  ],
  "info" : { "author" : "xcode", "version" : 1 }
}
JSON
