# Synthesus 4.0: 5TB Google Drive Parameter Cloud Strategy

## Status: ACTIVE (Pivoting to Service Account)

This document outlines the architecture and implementation for using a 5TB Google Drive as the infinite-memory foundation for the Synthesus 4.0 framework.

---

## 1. Objective
Enable Synthesus to offload billions of parameters, episodic memories, and character state shards to a persistent, massive cloud backend while maintaining sub-millisecond local inference speeds.

## 2. Architecture: Hybrid Cache & Sync
To balance speed and storage, we use a dual-layer approach:
- **Hot Layer (Local)**: Real-time reads and writes occur in a local PostgreSQL database or in-memory cache.
- **Cold Layer (Cloud)**: A background worker (`DriveSyncWorker`) periodically batches local data, compresses it, and syncs it to the 5TB Google Drive folder.
- **Bootstrap Hook**: Upon system restart, if the local cache is empty, the system automatically pulls the latest shards from Google Drive to restore the AI's "long-term memory."

## 3. Integration Strategy Pivot
We have encountered authentication bottlenecks using the standard OAuth 2.0 User Flow (browser-based), specifically regarding headless environment redirects and Google's 2FA loops in isolated Linux environments.

**Current Solution**: **Google Service Account Integration**
- **Identity**: Synthesus will operate as a dedicated Service Account.
- **Access**: The user shares the 5TB Drive folder (`1_fCFGR34kZEbCPSd2ojiKX0s_ongOta4`) with the Service Account email.
- **Auth**: A static `service_account.json` key file replaces the interactive browser login, enabling 24/7 background synchronization without security code interruptions.

## 4. Current Progress (Current Session)
- **Character Intelligence**: Transitioned all characters from templated responses to a **Generative Dual-Hemisphere reasoning model**.
- **System Stability**: Fixed a critical `NameError` in the `EmulationTool` that was blocking system initialization.
- **Drive Backend**: Implemented `cloud/drive_backend.py` with full upload/download capabilities.
- **API Extension**: Updated `api/parameter_cloud_v2.py` with the synchronization worker and manual trigger endpoints.

## 5. Next Steps for User
1. **Create Service Account**: Generate a JSON key in the Google Cloud Console.
2. **Share Folder**: Share the 5TB folder with the Service Account email as "Editor."
3. **Upload Key**: Place the key file in the framework root as `service_account.json`.
4. **Initiate Sync**: The system will automatically detect the key and begin the initial population pass.
