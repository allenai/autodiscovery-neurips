from autodiscovery_modal import ModalSandboxIPythonBackend
from code_execution import IPythonExecutor
import logging
import modal
import os


logging.basicConfig(level=logging.INFO, format="%(message)s")
app_name = os.environ.get("MODAL_APP_NAME", "asta-autodiscovery")
bucket = os.environ.get("GCS_BUCKET", "ai2-autodiscovery")
key_prefix = os.environ.get("GCS_PREFIX", "samples/")
read_only = os.environ.get("GCS_READ_ONLY", "true").lower() == "true"
bucket_endpoint_url = os.environ.get("GCS_ENDPOINT_URL", "https://storage.googleapis.com")
mount_path = "/data"

secret_name = os.environ.get("MODAL_BUCKET_SECRET", "gcs-autodiscovery")
if not secret_name:
    raise ValueError("Set MODAL_BUCKET_SECRET to a Modal Secret with GCS credentials.")

bucket_secret = modal.Secret.from_name(secret_name)
backend = ModalSandboxIPythonBackend.for_bucket_prefix(
    app_name=app_name,
    bucket=bucket,
    key_prefix=key_prefix,
    mount_path=mount_path,
    read_only=read_only,
    bucket_endpoint_url=bucket_endpoint_url,
    bucket_secret=bucket_secret,
    env={"SMOKE_TEST": "true"},
)

executor = IPythonExecutor(backend)
result = executor.run_cell("import os; print(os.listdir('/data'))")

print(result["stdout"])