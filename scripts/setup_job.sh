#!/bin/bash
# Setup a new AutoDiscovery job in GCS
#
# This script uploads dataset files and metadata to GCS in a structured directory
# for a specific user and job ID.
#
# Usage:
#   ./scripts/setup_job.sh <userid> <jobid> <local_data_path> [metadata_file]
#
# Arguments:
#   local_data_path - Can be either:
#                     - A directory: uploads all files in the directory
#                     - A single file: uploads only that file
#
# Examples:
#   # Upload entire directory
#   ./scripts/setup_job.sh reecea job1 ./discoverybench/nls_ses/ ./metadata.json
#
#   # Upload single file
#   ./scripts/setup_job.sh reecea job1 ./discoverybench/nls_ses/data.csv ./metadata.json
#
# This creates the following structure in GCS:
#   gs://ai2-autodiscovery/users/reecea/jobs/job1/
#   ├── data/                    # Dataset files (mounted in Modal sandbox)
#   │   ├── nls_ses_processed.csv
#   │   └── ...
#   ├── metadata.json            # Metadata file
#   └── output/                  # Output directory (created empty)
#
# After setup, run the job with:
#   ./scripts/run_job.sh reecea job1

set -e

# Check arguments
if [ "$#" -lt 3 ]; then
    echo "Usage: $0 <userid> <jobid> <local_data_path> [metadata_file]"
    echo ""
    echo "Arguments:"
    echo "  userid          - User identifier (e.g., reecea)"
    echo "  jobid           - Job identifier (e.g., job1)"
    echo "  local_data_path - Local directory or file containing dataset"
    echo "  metadata_file   - (Optional) Local path to metadata.json"
    echo ""
    echo "Examples:"
    echo "  $0 reecea job1 ./discoverybench/nls_ses/ ./metadata.json"
    echo "  $0 reecea job1 ./discoverybench/nls_ses/data.csv ./metadata.json"
    exit 1
fi

USERID=$1
JOBID=$2
LOCAL_DATA_DIR=$3
METADATA_FILE=${4:-""}

# Configuration
BUCKET="ai2-autodiscovery"
JOB_BASE="users/${USERID}/jobs/${JOBID}"

echo "========================================="
echo "Setting up AutoDiscovery Job in GCS"
echo "========================================="
echo "User: ${USERID}"
echo "Job ID: ${JOBID}"
echo "GCS Base: gs://${BUCKET}/${JOB_BASE}/"
echo ""

# Create the output directory
echo "Creating output directory..."
gsutil -q ls "gs://${BUCKET}/${JOB_BASE}/output/" 2>/dev/null || \
    echo "placeholder" | gsutil cp - "gs://${BUCKET}/${JOB_BASE}/output/.placeholder"

# Upload data (file or directory)
echo "Uploading data..."

# Check if LOCAL_DATA_DIR is a file or directory
if [ -f "$LOCAL_DATA_DIR" ]; then
    # Upload single file
    echo "Uploading single file: $(basename "$LOCAL_DATA_DIR")"
    gsutil cp "${LOCAL_DATA_DIR}" "gs://${BUCKET}/${JOB_BASE}/data/"
    echo "File uploaded to gs://${BUCKET}/${JOB_BASE}/data/$(basename "$LOCAL_DATA_DIR")"
elif [ -d "$LOCAL_DATA_DIR" ]; then
    # Upload entire directory
    echo "Uploading directory: $LOCAL_DATA_DIR"
    gsutil -m cp -r "${LOCAL_DATA_DIR}"/* "gs://${BUCKET}/${JOB_BASE}/data/"
    echo "Directory uploaded to gs://${BUCKET}/${JOB_BASE}/data/"
else
    echo "ERROR: Path not found: $LOCAL_DATA_DIR"
    exit 1
fi

# Upload metadata if provided
if [ -n "$METADATA_FILE" ]; then
    if [ ! -f "$METADATA_FILE" ]; then
        echo "WARNING: Metadata file not found: $METADATA_FILE"
    else
        echo "Uploading metadata..."
        gsutil cp "${METADATA_FILE}" "gs://${BUCKET}/${JOB_BASE}/metadata.json"
        echo "Metadata uploaded to gs://${BUCKET}/${JOB_BASE}/metadata.json"
    fi
fi

echo ""
echo "========================================="
echo "Setup complete!"
echo "========================================="
echo ""
echo "GCS Structure:"
gsutil ls -r "gs://${BUCKET}/${JOB_BASE}/"
echo ""
echo "To run this job:"
echo "./scripts/run_job.sh ${USERID} ${JOBID}"
