#!/usr/bin/env bash
set -e
cd /f/spl3/srs_diagrams
for f in diagram_*.mmd; do
  base="${f%.mmd}"
  echo "Rendering $f -> $base.png"
  npx -y @mermaid-js/mermaid-cli -i "$f" -o "$base.png" -b transparent -s 2
done
echo "ALL_DONE"
