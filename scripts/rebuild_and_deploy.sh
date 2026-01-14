#!/bin/bash
set -e

# Configuration
PROJECT_ID=$(gcloud config get-value project)
REGION="us-west1"
IMAGE="us-west1-docker.pkg.dev/${PROJECT_ID}/autodiscovery/autodiscovery:latest"
JOB_NAME="autodiscovery-job"
BUCKET="ai2-autodiscovery"

echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Image: ${IMAGE}"
echo "Job: ${JOB_NAME}"
echo ""

# Step 1: Build and push image using Cloud Build
echo "========================================="
echo "Step 1: Building and pushing Docker image"
echo "========================================="
gcloud builds submit --config=cloudbuild.yaml

echo ""
echo "========================================="
echo "Step 2: Updating Cloud Run Job with GCS mount"
echo "========================================="
gcloud run jobs update ${JOB_NAME} \
    --region ${REGION} \
    --image ${IMAGE} \
    --add-volume name=job-storage,type=cloud-storage,bucket=${BUCKET} \
    --add-volume-mount volume=job-storage,mount-path=/mnt/gcs

echo ""
echo "Note: GCS bucket '${BUCKET}' is now mounted at /mnt/gcs/"

echo ""
echo "========================================="
echo "Deployment complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Setup a new job:    ./scripts/setup_job.sh <userid> <jobid> <local_data_dir> [metadata_file]"
echo "2. Run the job:        ./scripts/run_job.sh <userid> <jobid>"
echo ""
echo "Example:"
echo "  ./scripts/setup_job.sh reecea job1 ./discoverybench/nls_ses/ ./metadata.json"
echo "  ./scripts/run_job.sh reecea job1"
