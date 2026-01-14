# Deploying to GCP Cloud Run Jobs

This guide explains how to deploy AutoDiscovery as a GCP Cloud Run Job.

## Prerequisites

1. Install Google Cloud CLI: https://cloud.google.com/sdk/docs/install
2. Authenticate with GCP:
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```
3. Enable required APIs:
   ```bash
   gcloud services enable cloudbuild.googleapis.com run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
   ```
4. **GitHub Access**: Create a GitHub Personal Access Token with `repo` access to private repositories:
   - Go to https://github.com/settings/tokens/new
   - Select `repo` scope (required to access `allenai/asta-autodiscovery`)
   - Generate token and save it securely

## Step 1: Create Artifact Registry Repository

Create a Docker repository in Artifact Registry:

```bash
gcloud artifacts repositories create autodiscovery \
    --repository-format=docker \
    --location=us-west1 \
    --description="AutoDiscovery container images"
```

**Important**: Configure Docker authentication for Artifact Registry:

```bash
gcloud auth configure-docker us-west1-docker.pkg.dev
```

**This command must be run:**
- Once per machine/workstation
- After logging in with a new GCP account
- Before attempting to push images to Artifact Registry

Verify the repository was created:

```bash
gcloud artifacts repositories list --location=us-west1
```

## Step 2: Set Up GitHub Authentication

This project depends on private GitHub repositories, so you need to provide authentication during the Docker build.

**Option A: Using Cloud Build (Recommended)**

Store your GitHub token in Secret Manager:

```bash
echo -n "YOUR_GITHUB_TOKEN" | gcloud secrets create autodiscovery-github-token --data-file=-

# Or from .github_token
cat .github_token | gcloud secrets create autodiscovery-github-token --data-file=-
```

Grant Cloud Build access to the secret:

```bash
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format="value(projectNumber)")
gcloud secrets add-iam-policy-binding autodiscovery-github-token \
    --member=serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor
```

Build and push using the provided `cloudbuild.yaml`:

```bash
gcloud builds submit --config=cloudbuild.yaml
```

The `cloudbuild.yaml` file securely mounts the GitHub token during the build without exposing it in the image layers.

**Option B: Local Build**

If you prefer to build locally:

```bash
# Create a temporary token file
echo "YOUR_GITHUB_TOKEN" > .github_token

# Build with the secret mounted
docker build --platform linux/amd64 \
    --secret id=github_token,src=.github_token \
    -t us-west1-docker.pkg.dev/ai2-aristo/autodiscovery/autodiscovery:latest .

# Push to Artifact Registry (requires Docker authentication - see Step 1)
docker push us-west1-docker.pkg.dev/ai2-aristo/autodiscovery/autodiscovery:latest

# Clean up the token file
rm .github_token
```

**Notes**:
- The `.github_token` file is already in `.dockerignore` and will never be included in the image
- If you get "Unauthenticated request" errors when pushing, ensure you've run `gcloud auth configure-docker us-west1-docker.pkg.dev` (see Step 1)

## Step 3: Configure Secrets

Before creating the job, set up your OpenAI API key in Secret Manager:

```bash
# Create the secret (one-time setup)
echo -n "your-openai-api-key" | gcloud secrets create autodiscovery-openai-key --data-file=-
```

Grant the Cloud Run default service account access to the secret:

```bash
# Get your project number
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format="value(projectNumber)")

# Grant access to the secret
gcloud secrets add-iam-policy-binding autodiscovery-openai-key \
    --member=serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor
```

**Why this is needed**: Cloud Run Jobs use the default compute service account (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`), which needs explicit permission to access secrets in Secret Manager. Without this step, you'll get a "Permission denied" error when creating the job.

**Note**: Secrets are configured at the **job level** (not at execution time). Once configured, they're automatically available to every execution of the job.

## Step 4: Create Cloud Run Job

Create the Cloud Run Job with secrets configured:

```bash
gcloud run jobs create autodiscovery-job \
    --image us-west1-docker.pkg.dev/ai2-aristo/autodiscovery/autodiscovery:latest \
    --region us-west1 \
    --set-secrets OPENAI_API_KEY=autodiscovery-openai-key:latest \
    --memory 4Gi \
    --cpu 2 \
    --max-retries 0 \
    --task-timeout 7d
```

**Configuration Options**:
- `--set-secrets`: References secrets from Secret Manager (format: `ENV_VAR_NAME=secret-name:version`)
- `--set-env-vars`: Sets literal environment variables (format: `KEY=value,KEY2=value2`)
- `--task-timeout`: Maximum execution time (supports `s`, `m`, `h`, `d` - max is `7d`)
- `--memory`: Memory allocation (e.g., `512Mi`, `2Gi`, `8Gi`)
- `--cpu`: CPU allocation (e.g., `1`, `2`, `4`, `8`)

**Verify the job configuration**:
```bash
gcloud run jobs describe autodiscovery-job --region us-west1
```

## Step 5: Execute the Job

Execute the job with your custom arguments. **Secrets and environment variables configured in Step 4 are automatically included**:

```bash
gcloud run jobs execute autodiscovery-job \
    --region us-west1 \
    --args="--work_dir=/tmp/work,--out_dir=/tmp/outputs,--dataset_metadata=discoverybench/real/test/nls_ses/metadata_0.json,--n_experiments=4,--model=gpt-4o,--belief_model=gpt-4o"
```

**Optional**: Override or add environment variables for a specific execution:
```bash
gcloud run jobs execute autodiscovery-job \
    --region us-west1 \
    --update-env-vars DEBUG=true,LOG_LEVEL=verbose \
    --args="--your-args-here"
```

**Note**: You cannot override secrets at execution time - they must be updated at the job level using `gcloud run jobs update`.

## Step 6: Using Datasets from Cloud Storage

Cloud Run Jobs support mounting Cloud Storage buckets directly as volumes, making bucket contents accessible as regular filesystem directories.

### Upload Dataset to Cloud Storage

```bash
# Create a bucket (if needed)
gsutil mb -l us-west1 gs://your-bucket-name

# Upload your dataset
gsutil cp -r discoverybench/real/test/nls_ses gs://your-bucket-name/datasets/
```

### Grant Storage Permissions

The Cloud Run service account needs read access to your bucket:

```bash
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format="value(projectNumber)")

# Grant Storage Object Viewer role
gsutil iam ch serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com:roles/storage.objectViewer gs://your-bucket-name
```

### Mount the Bucket to Your Job

Add a volume mount when creating or updating the job:

```bash
# When creating a new job
gcloud run jobs create autodiscovery-job \
    --image us-west1-docker.pkg.dev/YOUR_PROJECT_ID/autodiscovery/autodiscovery:latest \
    --region us-west1 \
    --set-secrets OPENAI_API_KEY=autodiscovery-openai-key:latest \
    --add-volume name=datasets,type=cloud-storage,bucket=your-bucket-name \
    --add-volume-mount volume=datasets,mount-path=/mnt/gcs \
    --memory 4Gi \
    --cpu 2 \
    --task-timeout 7d

# Or update an existing job
gcloud run jobs update autodiscovery-job \
    --region us-west1 \
    --add-volume name=datasets,type=cloud-storage,bucket=your-bucket-name \
    --add-volume-mount volume=datasets,mount-path=/mnt/gcs
```

**Volume Options:**
- `name`: Identifier for the volume
- `type=cloud-storage`: Specifies GCS volume
- `bucket`: Your GCS bucket name
- `mount-path`: Where the bucket appears in container (e.g., `/mnt/gcs`)

### Execute Job with Mounted Dataset

The bucket contents are available at the mount path. Reference files relative to that path:

```bash
gcloud run jobs execute autodiscovery-job \
    --region us-west1 \
    --args="--dataset_metadata=/mnt/gcs/datasets/nls_ses/metadata_0.json,--n_experiments=16,--model=gpt-4o"
```

### Read-Only Mounts (Recommended)

For safety, mount datasets as read-only:

```bash
gcloud run jobs update autodiscovery-job \
    --region us-west1 \
    --add-volume name=datasets,type=cloud-storage,bucket=your-bucket-name,readonly=true \
    --add-volume-mount volume=datasets,mount-path=/mnt/gcs
```

### Important Considerations

- **No code changes needed** - bucket appears as a regular directory
- **Network dependent** - slower than local disk, suitable for datasets <1GB
- **No file locking** - don't write to the same file from multiple jobs concurrently
- **Cold start impact** - mount adds slight startup time (fails if >30 seconds)
- **Memory usage** - uses container memory for caching (~40-100 MB)

### Mounting Multiple Buckets

You can mount multiple buckets at different paths:

```bash
gcloud run jobs update autodiscovery-job \
    --region us-west1 \
    --add-volume name=datasets,type=cloud-storage,bucket=datasets-bucket \
    --add-volume-mount volume=datasets,mount-path=/mnt/datasets \
    --add-volume name=outputs,type=cloud-storage,bucket=outputs-bucket \
    --add-volume-mount volume=outputs,mount-path=/mnt/outputs
```

## Step 7: Store Outputs in Cloud Storage

To persist outputs beyond the job execution, you have two options:

### Option A: Mount Output Bucket (Recommended)

Mount a writable GCS bucket and write outputs directly to it:

```bash
# Mount an output bucket
gcloud run jobs update autodiscovery-job \
    --region us-west1 \
    --add-volume name=outputs,type=cloud-storage,bucket=your-outputs-bucket \
    --add-volume-mount volume=outputs,mount-path=/mnt/outputs

# Run job with output directory in mounted path
gcloud run jobs execute autodiscovery-job \
    --region us-west1 \
    --args="--out_dir=/mnt/outputs,--dataset_metadata=/mnt/gcs/datasets/nls_ses/metadata_0.json,--n_experiments=16"
```

**Note**: The service account needs `roles/storage.objectCreator` or `roles/storage.objectUser` for write access:

```bash
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format="value(projectNumber)")
gsutil iam ch serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com:roles/storage.objectUser gs://your-outputs-bucket
```

### Option B: Copy Outputs After Execution

Write to local storage during execution, then copy to GCS. Requires modifying your code or adding a wrapper script:

```bash
# Add this to your job execution or as a wrapper script
gsutil -m cp -r /tmp/outputs/* gs://YOUR_BUCKET_NAME/outputs/
```

## Updating Job Configuration

To update an existing job's configuration (secrets, environment variables, memory, timeout, etc.):

```bash
# Update secrets
gcloud run jobs update autodiscovery-job \
    --region us-west1 \
    --set-secrets OPENAI_API_KEY=autodiscovery-openai-key:latest

# Update environment variables
gcloud run jobs update autodiscovery-job \
    --region us-west1 \
    --set-env-vars KEY1=value1,KEY2=value2

# Update memory and CPU
gcloud run jobs update autodiscovery-job \
    --region us-west1 \
    --memory 16Gi \
    --cpu 8

# Update timeout
gcloud run jobs update autodiscovery-job \
    --region us-west1 \
    --task-timeout 1d

# Update the image
gcloud run jobs update autodiscovery-job \
    --region us-west1 \
    --image us-west1-docker.pkg.dev/ai2-aristo/autodiscovery/autodiscovery:latest
```

**View secrets in Google Cloud Console**:
- Navigate to: https://console.cloud.google.com/security/secret-manager
- You can view secret names and metadata, but not the actual values (for security)

## Providing Datasets

For datasets, you have several options:

### Option 1: Include in Docker Image
Add datasets to the Dockerfile (increases image size):

```dockerfile
COPY discoverybench ./discoverybench
COPY blade ./blade
```

### Option 2: Download at Runtime
Modify the job to download datasets from Cloud Storage or Git when it starts:

```bash
# In your job startup or in the Dockerfile
RUN git clone https://github.com/allenai/discoverybench.git temp_db && \
    cp -r temp_db/discoverybench discoverybench && \
    rm -rf temp_db
```

### Option 3: Use Cloud Storage FUSE
Mount datasets from Cloud Storage using gcsfuse for large datasets.

## Monitoring and Logs

View job executions:
```bash
gcloud run jobs executions list --job autodiscovery-job --region us-west1
```

View logs for a specific execution:
```bash
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=autodiscovery-job" --limit 50 --format json
```

Or use the Cloud Console: https://console.cloud.google.com/run/jobs

## Example: Full Workflow

```bash
# Set variables
export PROJECT_ID=your-project-id
export REGION=us-west1
export IMAGE=us-west1-docker.pkg.dev/${PROJECT_ID}/autodiscovery/autodiscovery:latest

# Create Artifact Registry repository (first time only)
gcloud artifacts repositories create autodiscovery \
    --repository-format=docker \
    --location=${REGION} \
    --description="AutoDiscovery container images"

# Configure Docker authentication (required for pushing images)
gcloud auth configure-docker us-west1-docker.pkg.dev

# One-time setup: Store secrets in Secret Manager
echo -n "YOUR_GITHUB_TOKEN" | gcloud secrets create github-token --data-file=-
echo -n "YOUR_OPENAI_API_KEY" | gcloud secrets create autodiscovery-openai-key --data-file=-

# Grant Cloud Build access to GitHub token
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")
gcloud secrets add-iam-policy-binding github-token \
    --member=serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor

# Grant Cloud Run default service account access to OpenAI key
gcloud secrets add-iam-policy-binding autodiscovery-openai-key \
    --member=serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor

# Build and push using cloudbuild.yaml (handles GitHub auth)
gcloud builds submit --config=cloudbuild.yaml

# Create job (first time only)
gcloud run jobs create autodiscovery-job \
    --image ${IMAGE} \
    --region ${REGION} \
    --set-secrets OPENAI_API_KEY=autodiscovery-openai-key:latest \
    --memory 8Gi \
    --cpu 4 \
    --max-retries 0 \
    --task-timeout 2h

# Execute with custom parameters
# Note: Secrets configured above are automatically included in every execution
gcloud run jobs execute autodiscovery-job \
    --region ${REGION} \
    --args="--dataset_metadata=discoverybench/real/test/nls_ses/metadata_0.json,--n_experiments=8,--model=gpt-4o"
```

## Cost Optimization Tips

1. Use `--max-retries 0` to avoid unnecessary retries on failure
2. Set appropriate `--task-timeout` based on expected runtime
3. Use smaller CPU/memory if your workload allows
4. Use preemptible instances for non-critical jobs
5. Store datasets in Cloud Storage and download only what's needed

## Troubleshooting

**Issue**: "Unauthenticated request" or "permission denied" when pushing to Artifact Registry
- Error message: `denied: Unauthenticated request. Unauthenticated requests do not have permission "artifactregistry.repositories.uploadArtifacts"`
- **Solution 1**: Configure Docker authentication:
  ```bash
  gcloud auth configure-docker us-west1-docker.pkg.dev
  ```
- **Solution 2**: Verify the repository exists and you have access:
  ```bash
  gcloud artifacts repositories list --location=us-west1
  ```
  If `autodiscovery` is not listed, create it:
  ```bash
  gcloud artifacts repositories create autodiscovery \
      --repository-format=docker \
      --location=us-west1 \
      --description="AutoDiscovery container images"
  ```
  If the list command fails entirely, you don't have sufficient GCP permissions on the project.
- **Solution 3**: Verify your current GCP account and project:
  ```bash
  gcloud config list
  ```
  Ensure you're logged in with the correct account and project is set to `ai2-aristo` (or your project ID).

**Issue**: "Permission denied on secret" when creating Cloud Run Job
- Error message: `Permission denied on secret: projects/.../secrets/autodiscovery-openai-key/versions/latest for Revision service account ... The service account used must be granted the 'Secret Manager Secret Accessor' role`
- **Cause**: The Cloud Run default compute service account doesn't have permission to access your secret
- **Solution**: Grant the service account access to the secret (see Step 3):
  ```bash
  PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format="value(projectNumber)")
  gcloud secrets add-iam-policy-binding autodiscovery-openai-key \
      --member=serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
      --role=roles/secretmanager.secretAccessor
  ```
- **Verify the binding**:
  ```bash
  gcloud secrets get-iam-policy autodiscovery-openai-key
  ```

**Issue**: Docker build fails with "could not read Username for 'https://github.com'"
- You need to provide GitHub authentication (see Step 2)
- Ensure your GitHub token has `repo` scope
- For Cloud Build: verify the secret exists: `gcloud secrets versions access latest --secret=github-token`
- For local build: make sure you're using `--secret id=github_token,src=.github_token`

**Issue**: Cloud Build cannot access github-token secret
- Grant Cloud Build service account access to the secret:
  ```bash
  PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)")
  gcloud secrets add-iam-policy-binding github-token \
      --member=serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com \
      --role=roles/secretmanager.secretAccessor
  ```

**Issue**: Job times out
- Increase `--task-timeout` value
- Check logs for performance bottlenecks

**Issue**: Out of memory
- Increase `--memory` allocation
- Optimize data loading in your code

**Issue**: Cannot access datasets
- Ensure datasets are properly included in the image or accessible from Cloud Storage
- Check file paths in your arguments

**Issue**: OpenAI API key not working
- Verify the secret exists: `gcloud secrets versions access latest --secret=autodiscovery-openai-key`
- Check IAM permissions for the Cloud Run service account:
  ```bash
  gcloud run services add-iam-policy-binding autodiscovery-job \
      --member=serviceAccount:YOUR_SERVICE_ACCOUNT \
      --role=roles/secretmanager.secretAccessor \
      --region=us-west1
  ```
