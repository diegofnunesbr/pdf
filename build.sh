#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

docker build -t pdf:local .
docker save pdf:local | sudo k0s ctr images import -
