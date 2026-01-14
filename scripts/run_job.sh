#!/bin/bash
# Execute an AutoDiscovery job on Cloud Run
#
# This script runs a Cloud Run job that was previously set up using setup_job.sh.
# It automatically configures paths for metadata, output, and dataset files.
#
# Usage:
#   ./scripts/run_job.sh <userid> <jobid>
#
# Example:
#   ./scripts/run_job.sh reecea job1
#
# After the job completes, view and download results:
#
#   # List all output files
#   gsutil ls gs://ai2-autodiscovery/users/reecea/jobs/job1/output/
#
#   # List output files recursively
#   gsutil ls -r gs://ai2-autodiscovery/users/reecea/jobs/job1/output/
#
#   # Download all outputs to local directory
#   gsutil -m cp -r gs://ai2-autodiscovery/users/reecea/jobs/job1/output/ ./local_output/
#
#   # Download a specific file
#   gsutil cp gs://ai2-autodiscovery/users/reecea/jobs/job1/output/results.json ./results.json
#
#   # View a specific file without downloading
#   gsutil cat gs://ai2-autodiscovery/users/reecea/jobs/job1/output/log.txt
#
# View job execution logs:
#   gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=autodiscovery-job" --limit 50

set -e

# Check arguments
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <userid> <jobid>"
    echo "Example: $0 reecea job1"
    exit 1
fi

USERID=$1
JOBID=$2

# Configuration
PROJECT_ID=$(gcloud config get-value project)
REGION="us-west1"
JOB_NAME="autodiscovery-job"
BUCKET="ai2-autodiscovery"

# Construct paths
JOB_BASE="users/${USERID}/jobs/${JOBID}"
METADATA_PATH="/mnt/gcs/${JOB_BASE}/metadata.json"
OUTPUT_PATH="/mnt/gcs/${JOB_BASE}/output"
BUCKET_PATH="gs://${BUCKET}/${JOB_BASE}/data"

echo "========================================="
echo "Executing AutoDiscovery Job"
echo "========================================="
echo "User: ${USERID}"
echo "Job ID: ${JOBID}"
echo "Metadata: ${METADATA_PATH}"
echo "Output: ${OUTPUT_PATH}"
echo "Data bucket: ${BUCKET_PATH}"
echo ""

# Verify the bucket paths exist
echo "Verifying GCS paths..."
if ! gsutil ls "gs://${BUCKET}/${JOB_BASE}/metadata.json" &>/dev/null; then
    echo "ERROR: Metadata file not found at gs://${BUCKET}/${JOB_BASE}/metadata.json"
    exit 1
fi

if ! gsutil ls "gs://${BUCKET}/${JOB_BASE}/data/" &>/dev/null; then
    echo "ERROR: Data directory not found at gs://${BUCKET}/${JOB_BASE}/data/"
    exit 1
fi

echo "Paths verified!"
echo ""

# Execute the job
echo "Executing Cloud Run Job..."
gcloud run jobs execute ${JOB_NAME} \
    --region ${REGION} \
    --args="--dataset_metadata=${METADATA_PATH},--out_dir=${OUTPUT_PATH},--n_experiments=4,--model=gpt-4o,--work_dir=work,--use_modal_sandbox,--bucket_path=${BUCKET_PATH},--no-timestamp_dir"

echo ""
echo "Job execution started!"
echo "View logs: gcloud logging read \"resource.type=cloud_run_job AND resource.labels.job_name=${JOB_NAME}\" --limit 50"
