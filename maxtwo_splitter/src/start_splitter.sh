#!/usr/bin/env bash
# start_splitter.sh — download from S3 with a pv progress bar, run splitter.py,
#                     then upload each well file back to S3 (also with pv)
set -euo pipefail

###############################################################################
# 0. Arguments
###############################################################################
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <s3_uri>" >&2
  exit 1
fi
S3_URI="$1"
ENDPOINT="https://s3.braingeneers.gi.ucsc.edu"

###############################################################################
# 1. AWS CLI tuning for flaky links
###############################################################################
aws configure set default.s3.max_concurrent_requests 2
aws configure set default.s3.multipart_chunksize      128MB
aws configure set default.s3.connect_timeout          120
aws configure set default.s3.read_timeout             900

###############################################################################
# 2. Target paths
###############################################################################
TARGET_DIR="/data"
mkdir -p "${TARGET_DIR}"
FILE_NAME="$(basename "${S3_URI}")"
TARGET_PATH="${TARGET_DIR}/${FILE_NAME}"

###############################################################################
# 3. Ensure pv is installed
###############################################################################
if ! command -v pv >/dev/null 2>&1; then
  echo "pv not found; installing…" >&2
  apt-get update -qq && apt-get install -y -qq pv
fi

###############################################################################
# 4. Download with pv progress bar (works in TTY and non-TTY)
###############################################################################
# Obtain object size; if forbidden or unavailable, leave SIZE_BYTES empty
BUCKET=$(echo "${S3_URI}" | cut -d/ -f3)
KEY=$(echo  "${S3_URI}" | cut -d/ -f4-)
SIZE_BYTES=$(aws --endpoint "${ENDPOINT}" s3api head-object \
                 --bucket "${BUCKET}" --key "${KEY}" \
                 --query 'ContentLength' --output text 2>/dev/null || echo "")
[[ "${SIZE_BYTES}" == "None" ]] && SIZE_BYTES=""

echo "Downloading ${FILE_NAME} …"
if [[ -n "${SIZE_BYTES}" ]]; then
  pv_opts=(-s "${SIZE_BYTES}")
else
  pv_opts=()                          # pv will show bytes & rate only
fi

aws --endpoint "${ENDPOINT}" s3 cp "${S3_URI}" - \
| pv "${pv_opts[@]}" --name "${FILE_NAME}" \
> "${TARGET_PATH}"

echo "Download complete: ${TARGET_PATH}"

###############################################################################
# 5. Run the splitter
###############################################################################
echo "Launching splitter.py on ${S3_URI}"
python splitter.py "${S3_URI}"

###############################################################################
# 6. Upload each split well file back to S3 (pv progress bar)
###############################################################################
S3_SPLIT_PREFIX="${S3_URI/original\/data/original\/split}"
S3_SPLIT_DIR="$(dirname "${S3_SPLIT_PREFIX}")"

echo "Uploading split files from ${TARGET_DIR}/split_output to ${S3_SPLIT_DIR}/"

for file in "${TARGET_DIR}/split_output"/*.raw.h5; do
  base=$(basename "${file}")
  dest="${S3_SPLIT_DIR}/${base}"
  size=$(stat --printf="%s" "${file}")

  echo "Uploading ${base} …"
  pv -s "${size}" --name "${base}" < "${file}" \
  | aws --endpoint "${ENDPOINT}" s3 cp - "${dest}"
done

echo "All split wells uploaded."
