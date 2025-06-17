#!/usr/bin/env bash
# start_splitter.sh — download from S3 with retry, run splitter.py,
#                     then upload each well file back to S3 with retry
set -euo pipefail

###############################################################################
# 0. Arguments and retry configuration
###############################################################################
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <s3_uri>" >&2
  exit 1
fi
S3_URI="$1"
ENDPOINT="https://s3.braingeneers.gi.ucsc.edu"

# Retry configuration
MAX_RETRIES=5
RETRY_COUNT=0
SUCCESS=0

###############################################################################
# 1. AWS CLI tuning for flaky links
###############################################################################
aws configure set default.s3.max_concurrent_requests 2
aws configure set default.s3.multipart_chunksize      128MB
aws configure set default.s3.connect_timeout          120
aws configure set default.s3.read_timeout             900

# Enhanced retry configuration for AWS CLI
aws configure set default.retry_mode adaptive
aws configure set default.max_attempts 10
aws configure set default.cli_read_timeout 0
aws configure set default.cli_connect_timeout 60

# Diagnostic information
echo "=== Diagnostic Information ==="
echo "AWS CLI version: $(aws --version)"
echo "Current AWS config:"
aws configure list
echo "Testing S3 connectivity..."

# Test basic connectivity first
echo "1. Testing endpoint connectivity..."
curl -I "${ENDPOINT}" --connect-timeout 10 || echo "WARNING: Cannot reach endpoint ${ENDPOINT}"

# Skip STS test for S3-compatible services (Ceph doesn't support STS)
echo "2. Skipping AWS STS test (not supported by S3-compatible services)"

# Test S3 listing
echo "3. Testing S3 bucket listing..."
if aws --endpoint "${ENDPOINT}" s3 ls s3://braingeneers/ 2>/dev/null | head -5 >/dev/null; then
    echo "SUCCESS: S3 bucket listing works"
else
    echo "WARNING: S3 bucket listing failed"
fi

# Test specific file access
echo "4. Testing specific file access..."
BUCKET=$(echo "${S3_URI}" | cut -d/ -f3)
KEY=$(echo "${S3_URI}" | cut -d/ -f4-)
echo "   Bucket: ${BUCKET}"
echo "   Key: ${KEY}"
if aws --endpoint "${ENDPOINT}" s3api head-object --bucket "${BUCKET}" --key "${KEY}" 2>/dev/null; then
    echo "SUCCESS: File exists and accessible"
else
    echo "WARNING: Cannot access target file"
fi

echo "==============================="

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
# 4. Download with pv progress bar and retry logic
###############################################################################
# Obtain object size; if forbidden or unavailable, leave SIZE_BYTES empty
BUCKET=$(echo "${S3_URI}" | cut -d/ -f3)
KEY=$(echo  "${S3_URI}" | cut -d/ -f4-)
SIZE_BYTES=$(aws --endpoint "${ENDPOINT}" s3api head-object \
                 --bucket "${BUCKET}" --key "${KEY}" \
                 --query 'ContentLength' --output text 2>/dev/null || echo "")
[[ "${SIZE_BYTES}" == "None" ]] && SIZE_BYTES=""

if [[ -n "${SIZE_BYTES}" ]]; then
  pv_opts=(-s "${SIZE_BYTES}")
else
  pv_opts=()                          # pv will show bytes & rate only
fi

# Download with retry logic
RETRY_COUNT=0
SUCCESS=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo "Downloading ${FILE_NAME} (attempt $((RETRY_COUNT + 1))/${MAX_RETRIES}) …"
    
    if aws --endpoint "${ENDPOINT}" s3 cp "${S3_URI}" - \
       | pv "${pv_opts[@]}" --name "${FILE_NAME}" \
       > "${TARGET_PATH}"; then
        SUCCESS=1
        echo "SUCCESS: Download complete: ${TARGET_PATH}"
        break
    else
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo "FAILED: Download failed. Attempt ${RETRY_COUNT}/${MAX_RETRIES}."
        rm -f "${TARGET_PATH}"  # Remove partial file
        if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
            echo "Retrying in 10 seconds..."
            sleep 10
        fi
    fi
done

if [ $SUCCESS -eq 0 ]; then
    echo "FAILED: Failed to download ${S3_URI} after ${MAX_RETRIES} attempts"
    exit 1
fi

###############################################################################
# 5. Run the splitter
###############################################################################
echo "Launching splitter.py on ${S3_URI}"
python splitter.py "${S3_URI}"

###############################################################################
# 6. Upload each split well file back to S3 (pv progress bar with retry)
###############################################################################
S3_SPLIT_PREFIX="${S3_URI/original\/data/original\/split}"
S3_SPLIT_DIR="$(dirname "${S3_SPLIT_PREFIX}")"

echo "Uploading split files from ${TARGET_DIR}/split_output to ${S3_SPLIT_DIR}/"

# Track overall upload success
OVERALL_SUCCESS=1

for file in "${TARGET_DIR}/split_output"/*.raw.h5; do
  base=$(basename "${file}")
  dest="${S3_SPLIT_DIR}/${base}"
  size=$(stat --printf="%s" "${file}")

  # Reset retry variables for each file
  RETRY_COUNT=0
  SUCCESS=0
  
  # Upload with retry logic
  while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo "Uploading ${base} (attempt $((RETRY_COUNT + 1))/${MAX_RETRIES}) …"
    
    if pv -s "${size}" --name "${base}" < "${file}" \
       | aws --endpoint "${ENDPOINT}" s3 cp - "${dest}"; then
      SUCCESS=1
      echo "SUCCESS: Successfully uploaded ${base}"
      break
    else
      RETRY_COUNT=$((RETRY_COUNT + 1))
      echo "FAILED: Upload failed for ${base}. Attempt ${RETRY_COUNT}/${MAX_RETRIES}."
      if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
        echo "Retrying in 10 seconds..."
        sleep 10
      fi
    fi
  done

  if [ $SUCCESS -eq 0 ]; then
    echo "FAILED: Failed to upload ${base} after ${MAX_RETRIES} attempts"
    OVERALL_SUCCESS=0
  fi
done

if [ $OVERALL_SUCCESS -eq 1 ]; then
  echo "SUCCESS: All split wells uploaded successfully."
else
  echo "FAILED: Some uploads failed. Check the logs above."
  exit 1
fi
