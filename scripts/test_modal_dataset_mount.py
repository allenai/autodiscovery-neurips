"""Test script for Modal sandbox dataset mounting."""

import os
import modal
from autodiscovery_modal import ModalSandboxIPythonBackend
from code_execution import IPythonExecutor


def test_mount():
    """Test mounting a specific dataset directory."""

    # Configuration
    app_name = os.environ.get("MODAL_APP_NAME", "asta-autodiscovery")
    bucket = "ai2-autodiscovery"
    secret_name = os.environ.get("MODAL_BUCKET_SECRET", "gcs-autodiscovery")
    bucket_endpoint_url = os.environ.get("GCS_ENDPOINT_URL", "https://storage.googleapis.com")

    # Test case: nls_ses dataset
    # Local path: discoverybench/real/test/nls_ses/nls_ses_processed.csv
    # We want to mount: gs://ai2-autodiscovery/discoverybench/real/test/ at /data
    # So files will be at: /data/nls_ses/nls_ses_processed.csv

    key_prefix = "discoverybench/"
    mount_path = "/data"
    working_dir = "/data/nls_ses"

    print(f"Testing mount configuration:")
    print(f"  Bucket: gs://{bucket}/{key_prefix}")
    print(f"  Mount at: {mount_path}")
    print(f"  Working directory: {working_dir}")
    print()

    # Create backend
    bucket_secret = modal.Secret.from_name(secret_name)
    backend = ModalSandboxIPythonBackend.for_bucket_prefix(
        app_name=app_name,
        bucket=bucket,
        key_prefix=key_prefix,
        mount_path=mount_path,
        read_only=True,
        bucket_endpoint_url=bucket_endpoint_url,
        bucket_secret=bucket_secret,
        env={"TEST": "true"},
    )

    executor = IPythonExecutor(backend)

    # Test 1: List what's at mount_path
    print("=" * 60)
    print("Test 1: List contents of mount path")
    print("=" * 60)
    code = f"""
import os
from pathlib import Path

print(f"Contents of {mount_path}:")
for item in sorted(Path('{mount_path}').iterdir()):
    print(f"  {{item.name}}")
"""
    result = executor.run_cell(code)
    print(result["stdout"])
    if not result["success"]:
        print(f"ERROR: {result.get('error', 'Unknown error')}")
    print()

    # Test 2: Try to change to working directory and list files
    print("=" * 60)
    print("Test 2: Change to working directory and list files")
    print("=" * 60)
    code = f"""
import os

try:
    os.chdir('{working_dir}')
    print(f"Successfully changed to: {{os.getcwd()}}")
    print(f"\\nFiles in {{os.getcwd()}}:")
    for file in sorted(os.listdir('.')):
        print(f"  {{file}}")
except FileNotFoundError as e:
    print(f"ERROR: {{e}}")
    print(f"\\nLet's check if the directory exists:")
    print(f"  os.path.exists('{working_dir}'): {{os.path.exists('{working_dir}')}}")
    print(f"\\nLet's check what's at {mount_path}:")
    for item in os.listdir('{mount_path}'):
        full_path = os.path.join('{mount_path}', item)
        is_dir = os.path.isdir(full_path)
        print(f"  {{item}} {{'(dir)' if is_dir else '(file)'}}")
"""
    result = executor.run_cell(code)
    print(result["stdout"])
    if not result["success"]:
        print(f"ERROR: {result.get('error', 'Unknown error')}")
    print()

    # Test 3: Try to load the dataset file
    print("=" * 60)
    print("Test 3: Try to access dataset file")
    print("=" * 60)
    code = f"""
import os

os.chdir('{working_dir}')
target_file = 'nls_ses_processed.csv'

if os.path.exists(target_file):
    print(f"✓ Found {{target_file}}")
    print(f"  Size: {{os.path.getsize(target_file)}} bytes")
else:
    print(f"✗ {{target_file}} not found in {{os.getcwd()}}")
    print(f"\\nAvailable files:")
    for f in os.listdir('.'):
        print(f"  {{f}}")
"""
    result = executor.run_cell(code)
    print(result["stdout"])
    if not result["success"]:
        print(f"ERROR: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    test_mount()
