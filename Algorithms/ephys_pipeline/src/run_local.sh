#!/usr/bin/env bash
# run_local.sh - Simple local testing version (no S3)
# Usage: ./run_local.sh /path/to/your/data.h5

set -e  # Exit on error

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Input validation
if [ $# -eq 0 ]; then
    echo "Usage: $0 /path/to/data.h5"
    echo "Example: $0 /Users/noah/data/experiment.raw.h5"
    exit 1
fi

INPUT_FILE="$1"
echo "Looking for file: $INPUT_FILE"

if [ ! -f "$INPUT_FILE" ]; then
    echo "ERROR: File not found: $INPUT_FILE"
    echo "Current directory: $(pwd)"
    echo "Please provide the full path to your data file"
    exit 1
fi

echo "File found!"

# Extract data name and input directory
DATA_NAME=$(basename "${INPUT_FILE}" | sed -E 's/\.(raw\.)?h5$|\.nwb$//')
INPUT_DIR=$(dirname "$(realpath "${INPUT_FILE}")")
echo "Processing: $DATA_NAME"
echo "Output will be saved to: ${INPUT_DIR}"

# Create local working directory in the same folder as the data
WORK_DIR="${INPUT_DIR}/SpikeSorting_temp"
echo "Using working directory: ${WORK_DIR}"
mkdir -p "${WORK_DIR}"

# Copy input file to expected location (as a file, not into a directory)
echo "Copying input file to ${WORK_DIR}/Trace..."
cp "${INPUT_FILE}" "${WORK_DIR}/Trace"

# Run Kilosort2
echo "Starting Kilosort2 processing..."
cd "${WORK_DIR}"
SPIKE_SORTING_DIR="${WORK_DIR}" python "${SCRIPT_DIR}/kilosort2_simplified.py" "$DATA_NAME"

# Check if processing succeeded
if [ $? -ne 0 ]; then
    echo "ERROR: Kilosort2 processing failed"
    exit 1
fi

# Save results to same folder as input data
TEMP_OUTPUT_DIR="${WORK_DIR}/inter/sorted/kilosort2"
if [ -d "$TEMP_OUTPUT_DIR" ]; then
    echo "Creating output zip..."
    cd "$TEMP_OUTPUT_DIR"
    zip -r "${DATA_NAME}_phy.zip" *

    # Move zip to input data directory
    mv "${DATA_NAME}_phy.zip" "${INPUT_DIR}/"

    echo "Results saved to: ${INPUT_DIR}/${DATA_NAME}_phy.zip"

    # Clean up temporary files
    echo "Cleaning up temporary files..."
    cd "${INPUT_DIR}"
    rm -rf "${WORK_DIR}"

    echo "Kilosort2 pipeline completed successfully!"
else
    echo "ERROR: Expected output folder not found: $TEMP_OUTPUT_DIR"
    exit 1
fi
