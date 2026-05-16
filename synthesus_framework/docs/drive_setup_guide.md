# Synthesus Google Drive Parameter Cloud — Setup Guide

To use your 5TB Google Drive as a Parameter Cloud, you must authorize Synthesus to access your Drive files.

## 1. Create a Google Cloud Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project named `Synthesus-Parameter-Cloud`.

## 2. Enable Google Drive API
1. In the sidebar, go to **APIs & Services** > **Library**.
2. Search for "Google Drive API" and click **Enable**.

## 3. Configure OAuth Consent Screen
1. Go to **APIs & Services** > **OAuth consent screen**.
2. Choose **External** user type and click **Create**.
3. Fill in the required fields (App name: `Synthesus`, User support email, etc.).
4. Under **Scopes**, click **Add or Remove Scopes**. Add `https://www.googleapis.com/auth/drive.file`.
5. Add your own email to the **Test users** list.

## 4. Create OAuth 2.0 Credentials
1. Go to **APIs & Services** > **Credentials**.
2. Click **Create Credentials** > **OAuth client ID**.
3. Choose **Desktop app** as the application type.
4. Name it `Synthesus CLI`.
5. Click **Create**, then download the JSON file.
6. Rename the downloaded file to `credentials.json`.
7. Move this file to the project root: `Synthesus_4.0/synthesus_framework/credentials.json`.

## 5. Authorize Synthesus
Run the authentication script inside the debian environment:
```bash
proot-distro login debian -- /data/data/com.termux/files/home/Synthesus_4.0/synthesus_framework/venv_debian/bin/python /data/data/com.termux/files/home/Synthesus_4.0/synthesus_framework/scripts/auth_gdrive.py
```
Follow the link in your browser, log in with your Google account, and grant permission. This will generate a `token.json` file which Synthesus will use for subsequent cloud operations.
