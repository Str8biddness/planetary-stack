# Control Plane API Documentation

## Overview

The Control Plane provides REST endpoints for device onboarding and approval management in Synthesus. It is designed for integration with a future cross-platform "Synthesus Console" app (desktop/mobile) that allows admin users to manage device enrollments and resolve approvals.

**Feature Flag**: The control plane is gated by the `ENABLE_CONTROL_PLANE` environment variable. Set `ENABLE_CONTROL_PLANE=true` to enable. Defaults to `false` for safety; all endpoints are disabled when off. This is experimental and may change.

**Base URL**: When enabled, endpoints are mounted under `/control/` on the main Synthesus server (e.g., `http://localhost:5000/control/devices`).

## Endpoints

### GET /control/devices

Lists discovered devices.

**Response (JSON)**:
```json
{
  "devices": [
    {
      "id": "string",
      "name": "string",
      "type": "string (e.g., 'emulator', 'container')",
      "status": "string (e.g., 'discovered', 'enrolled')",
      "capabilities": ["string"] (e.g., ["run_experiment", "collect_metrics"])
    }
  ]
}
```

### POST /control/enroll

Starts enrollment for a device, creating a pending approval.

**Request Body (JSON)**:
```json
{
  "device_id": "string",
  "requested_scopes": ["string"] (e.g., ["run_container_experiment", "collect_metrics"])
}
```

**Response (JSON)**:
```json
{
  "approval_id": "string",
  "message": "Enrollment started, pending approval."
}
```

**Errors**: 404 if device not found, 400 if scopes invalid.

### GET /control/approvals

Lists pending approvals.

**Response (JSON)**:
```json
{
  "approvals": [
    {
      "id": "string",
      "device_id": "string",
      "description": "string (e.g., 'Enroll device for emulation experiments')",
      "requested_scopes": ["string"],
      "status": "pending"
    }
  ]
}
```

### POST /control/approvals

Resolves an approval.

**Request Body (JSON)**:
```json
{
  "approval_id": "string",
  "decision": "approve" | "deny",
  "remember_policy": {
    "duration_days": 30,
    "auto_approve_similar": true
  }  // optional
}
```

**Response (JSON)**:
```json
{
  "message": "Approval resolved.",
  "device_id": "string"
}
```

**Errors**: 404 if approval not found, 400 if decision invalid.

## Security Notes

- All requests require authentication (future console app will handle login).
- Approvals are admin-only; decisions must be made via console.
- No real device actions occur until approval; onboarding is virtual/emulated only.
