This directory holds ONLY the encrypted Garmin history archive, `history.enc`.
The decrypted SQLite database must never be committed. GitHub Actions decrypts
and uses the archive only on its temporary runner. Treat the STRIDE_ARCHIVE_KEY
GitHub Actions secret as a sensitive recovery key.
