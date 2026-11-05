"""Generate a new encryption key for the GitHub Actions secret STRIDE_ARCHIVE_KEY.
Run locally, never commit or share the output.
"""
from cryptography.fernet import Fernet
print('\nPaste the following value into GitHub Actions repository secret STRIDE_ARCHIVE_KEY:')
print(Fernet.generate_key().decode())
print('\nSave it securely. You will need it to decrypt any previous sync history after a key rotation.\n')
