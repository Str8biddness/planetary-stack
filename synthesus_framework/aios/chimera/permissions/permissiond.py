#!/usr/bin/env python3
import json
import os
import subprocess
from pathlib import Path

class PermissionSystem:
    def __init__(self):
        self.permissions_file = "/opt/chimera/permissions/approved.json"
        self.load_permissions()
    
    def load_permissions(self):
        if Path(self.permissions_file).exists():
            with open(self.permissions_file, 'r') as f:
                self.permissions = json.load(f)
        else:
            self.permissions = {
                "kernel_modification": False,
                "auto_update": False,
                "network_access": True,
                "file_system_rw": True
            }
    
    def save_permissions(self):
        Path(self.permissions_file).parent.mkdir(exist_ok=True)
        with open(self.permissions_file, 'w') as f:
            json.dump(self.permissions, f, indent=2)
    
    def check_permission(self, action):
        return self.permissions.get(action, False)
    
    def request_permission(self, action, reason):
        print(f"Chimera requests permission to: {action}")
        print(f"Reason: {reason}")
        response = input("Grant permission? (y/N): ").lower().strip()
        granted = response == 'y'
        if granted:
            self.permissions[action] = True
            self.save_permissions()
        return granted

permission_system = PermissionSystem()
