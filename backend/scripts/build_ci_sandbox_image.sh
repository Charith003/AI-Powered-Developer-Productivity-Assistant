#!/usr/bin/env bash
set -euo pipefail

job_name="${1:?provide a CI job name}"
registry_name="devpilot-ci-registry-${job_name}"
image_tag="localhost:5000/devpilot/test-sandbox-python:ci-${job_name}"
evidence_dir="${SANDBOX_EVIDENCE_DIR:-${GITHUB_WORKSPACE:-.}/sandbox-evidence}"
mkdir -p "$evidence_dir"

cleanup() {
  docker rm --force "$registry_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run --detach --name "$registry_name" --publish 5000:5000 registry:2.8.3
for attempt in {1..30}; do
  if curl --fail --silent http://localhost:5000/v2/ >/dev/null; then
    break
  fi
  if [[ "$attempt" = 30 ]]; then
    echo "Temporary CI registry did not become ready" >&2
    exit 1
  fi
  sleep 1
done

docker build --pull --tag "$image_tag" \
  --file infra/test-sandbox-python/Dockerfile infra/test-sandbox-python
docker image inspect --format '{{json .Config}}' "$image_tag" \
  > "$evidence_dir/${job_name}-image-config.json"
python - "$evidence_dir/${job_name}-image-config.json" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert config.get("User") == "10001:10001", config.get("User")
assert config.get("WorkingDir") == "/workspace", config.get("WorkingDir")
PY

docker push "$image_tag" 2>&1 | tee "$evidence_dir/${job_name}-image-push.log"
digest="$(sed -n 's/.*digest: \(sha256:[0-9a-f]\{64\}\).*/\1/p' \
  "$evidence_dir/${job_name}-image-push.log" | tail -n 1)"
test -n "$digest"
image="${image_tag}@${digest}"
docker pull "$image"
docker image inspect --format '{{json .RepoDigests}}' "$image" \
  | tee "$evidence_dir/${job_name}-image-repodigests.json"
python - "$image" "$digest" "$evidence_dir/${job_name}-image-repodigests.json" <<'PY'
import json
import sys
from pathlib import Path

image, digest, evidence_path = sys.argv[1:]
repo_digests = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
assert image in repo_digests, repo_digests
assert image.endswith("@" + digest), image
PY
printf '%s\n' "$image" | tee "$evidence_dir/${job_name}-image-reference.txt"
printf '%s\n' "$digest" | tee "$evidence_dir/${job_name}-image-digest.txt"
echo "TEST_SANDBOX_IMAGE=$image" >> "$GITHUB_ENV"

# This localhost registry exists only for this hosted CI job. Production workers
# must use a separately approved persistent registry reference and digest.
