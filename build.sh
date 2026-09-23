#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

docker build -t image-to-pdf:local .
docker save image-to-pdf:local | sudo k0s ctr images import -
