"""Local setup only. Preserve ADC used by other projects on this machine."""
import shutil
import subprocess
from google.oauth2.credentials import Credentials


def cloud_credentials():
    executable = shutil.which('gcloud.cmd') or shutil.which('gcloud')
    if not executable:
        raise RuntimeError('Install Google Cloud CLI and sign in first')
    result = subprocess.run([executable, 'auth', 'print-access-token'],
                            capture_output=True, text=True, check=True)
    return Credentials(token=result.stdout.strip())
