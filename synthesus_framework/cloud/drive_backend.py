import os
import io
import json
import logging
from typing import Dict, List, Optional, Any
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

logger = logging.getLogger("drive_backend")

SCOPES = ['https://www.googleapis.com/auth/drive.file']

class DriveBackend:
    """Handles interaction with Google Drive for Parameter Cloud storage."""

    def __init__(self, folder_id: str, token_path: str = "token.json"):
        self.folder_id = folder_id
        self.token_path = token_path
        self.creds = self._load_credentials()
        self.service = build('drive', 'v3', credentials=self.creds)

    def _load_credentials(self):
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                raise Exception("Google Drive credentials not found or invalid. Run scripts/auth_gdrive.py")
        return creds

    def list_files(self) -> List[Dict[str, str]]:
        """List files in the configured folder."""
        query = f"'{self.folder_id}' in parents and trashed = false"
        results = self.service.files().list(q=query, fields="files(id, name)").execute()
        return results.get('files', [])

    def download_file(self, file_name: str) -> Optional[bytes]:
        """Download a file by name from the configured folder."""
        files = self.list_files()
        file_id = next((f['id'] for f in files if f['name'] == file_name), None)
        
        if not file_id:
            return None

        request = self.service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        return fh.getvalue()

    def upload_file(self, file_name: str, content: bytes, mime_type: str = 'application/octet-stream'):
        """Upload or update a file in the configured folder."""
        files = self.list_files()
        file_id = next((f['id'] for f in files if f['name'] == file_name), None)

        media = MediaFileUpload(
            io.BytesIO(content), 
            mimetype=mime_type, 
            resumable=True
        )

        if file_id:
            # Update existing
            self.service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
        else:
            # Create new
            file_metadata = {
                'name': file_name,
                'parents': [self.folder_id]
            }
            self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

    def delete_file(self, file_name: str):
        """Delete a file by name."""
        files = self.list_files()
        file_id = next((f['id'] for f in files if f['name'] == file_name), None)
        if file_id:
            self.service.files().delete(fileId=file_id).execute()
