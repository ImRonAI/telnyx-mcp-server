#!/usr/bin/env python3
"""
Secure secrets management for Telnyx MCP Server
Handles secure storage and retrieval of API keys and other sensitive data
"""

import os
import json
import base64
import logging
from typing import Dict, Optional, Any
from pathlib import Path
import hashlib
import hmac
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

class SecretsManager:
    """Secure secrets management for MCP server"""
    
    def __init__(self, secrets_file: Optional[str] = None):
        self.secrets_file = Path(secrets_file) if secrets_file else Path.home() / '.telnyx-mcp' / 'secrets.enc'
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Get or create master key from environment
        self.master_key = self._get_or_create_master_key()
        self.cipher = self._create_cipher(self.master_key)
    
    def _get_or_create_master_key(self) -> bytes:
        """Get master key from environment or create new one"""
        # Try to get from environment first
        env_key = os.environ.get('TELNYX_MCP_MASTER_KEY')
        if env_key:
            return base64.urlsafe_b64decode(env_key.encode())
        
        # Check if key file exists
        key_file = self.secrets_file.parent / '.master_key'
        if key_file.exists():
            try:
                with open(key_file, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"Could not read master key file: {e}")
        
        # Generate new master key
        logger.info("Generating new master key for secrets encryption")
        master_key = Fernet.generate_key()
        
        # Save to file with restricted permissions
        try:
            key_file.touch(mode=0o600)  # Read/write for owner only
            with open(key_file, 'wb') as f:
                f.write(master_key)
            logger.info(f"Master key saved to {key_file}")
            logger.info("To use the same key in other environments, set TELNYX_MCP_MASTER_KEY:")
            logger.info(f"export TELNYX_MCP_MASTER_KEY={base64.urlsafe_b64encode(master_key).decode()}")
        except Exception as e:
            logger.warning(f"Could not save master key to file: {e}")
        
        return master_key
    
    def _create_cipher(self, key: bytes) -> Fernet:
        """Create cipher for encryption/decryption"""
        return Fernet(key)
    
    def _load_secrets(self) -> Dict[str, Any]:
        """Load and decrypt secrets from file"""
        if not self.secrets_file.exists():
            return {}
        
        try:
            with open(self.secrets_file, 'rb') as f:
                encrypted_data = f.read()
            
            if not encrypted_data:
                return {}
            
            decrypted_data = self.cipher.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        
        except Exception as e:
            logger.error(f"Failed to load secrets: {e}")
            return {}
    
    def _save_secrets(self, secrets: Dict[str, Any]) -> None:
        """Encrypt and save secrets to file"""
        try:
            json_data = json.dumps(secrets, indent=2).encode()
            encrypted_data = self.cipher.encrypt(json_data)
            
            # Write with restricted permissions
            self.secrets_file.touch(mode=0o600)  # Read/write for owner only
            with open(self.secrets_file, 'wb') as f:
                f.write(encrypted_data)
            
            logger.info(f"Secrets saved to {self.secrets_file}")
        
        except Exception as e:
            logger.error(f"Failed to save secrets: {e}")
            raise
    
    def set_secret(self, key: str, value: str, description: Optional[str] = None) -> None:
        """Set a secret value"""
        secrets = self._load_secrets()
        
        secrets[key] = {
            'value': value,
            'description': description or f'Secret value for {key}',
            'created_at': str(datetime.now()),
            'hash': hashlib.sha256(value.encode()).hexdigest()[:16]  # For verification
        }
        
        self._save_secrets(secrets)
        logger.info(f"Secret '{key}' has been set")
    
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a secret value"""
        # First try environment variable
        env_value = os.environ.get(key)
        if env_value:
            return env_value
        
        # Then try encrypted secrets file
        secrets = self._load_secrets()
        secret_data = secrets.get(key)
        
        if secret_data and isinstance(secret_data, dict):
            return secret_data.get('value')
        elif secret_data:
            # Legacy format - just the value
            return secret_data
        
        return default
    
    def list_secrets(self) -> Dict[str, Dict[str, Any]]:
        """List all stored secrets (without values)"""
        secrets = self._load_secrets()
        
        # Return metadata without actual values
        return {
            key: {
                'description': data.get('description', 'No description') if isinstance(data, dict) else 'Legacy secret',
                'created_at': data.get('created_at', 'Unknown') if isinstance(data, dict) else 'Unknown',
                'has_value': bool(data),
                'hash': data.get('hash', 'N/A') if isinstance(data, dict) else 'N/A'
            }
            for key, data in secrets.items()
        }
    
    def delete_secret(self, key: str) -> bool:
        """Delete a secret"""
        secrets = self._load_secrets()
        
        if key in secrets:
            del secrets[key]
            self._save_secrets(secrets)
            logger.info(f"Secret '{key}' has been deleted")
            return True
        
        return False
    
    def validate_telnyx_api_key(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Validate Telnyx API key format and basic connectivity"""
        if not api_key:
            api_key = self.get_secret('TELNYX_API_KEY')
        
        validation_result = {
            'valid': False,
            'key_present': bool(api_key),
            'format_valid': False,
            'connectivity_test': 'not_tested',
            'issues': [],
            'recommendations': []
        }
        
        if not api_key:
            validation_result['issues'].append('API key is not set')
            validation_result['recommendations'].append('Set TELNYX_API_KEY environment variable or use secrets manager')
            return validation_result
        
        # Check format
        if api_key.startswith('KEY') and len(api_key) >= 20:
            validation_result['format_valid'] = True
        else:
            validation_result['issues'].append('API key format appears invalid (should start with "KEY" and be at least 20 characters)')
            validation_result['recommendations'].append('Verify API key is copied correctly from Telnyx dashboard')
        
        # Test connectivity (optional, requires network access)
        try:
            import requests
            response = requests.get(
                'https://api.telnyx.com/v2/',
                headers={'Authorization': f'Bearer {api_key}'},
                timeout=10
            )
            
            if response.status_code == 200:
                validation_result['connectivity_test'] = 'success'
                validation_result['valid'] = True
            elif response.status_code == 401:
                validation_result['connectivity_test'] = 'unauthorized'
                validation_result['issues'].append('API key authentication failed')
                validation_result['recommendations'].append('Verify API key is correct and has proper permissions')
            else:
                validation_result['connectivity_test'] = 'error'
                validation_result['issues'].append(f'Unexpected API response: {response.status_code}')
                
        except ImportError:
            validation_result['connectivity_test'] = 'skipped_no_requests'
        except Exception as e:
            validation_result['connectivity_test'] = 'network_error'
            validation_result['issues'].append(f'Network connectivity test failed: {str(e)}')
        
        if validation_result['format_valid'] and not validation_result['issues']:
            validation_result['valid'] = True
        
        return validation_result
    
    def setup_environment(self) -> Dict[str, str]:
        """Setup environment variables from secrets"""
        secrets = self._load_secrets()
        env_vars = {}
        
        for key, data in secrets.items():
            if isinstance(data, dict):
                value = data.get('value')
            else:
                value = data  # Legacy format
            
            if value:
                env_vars[key] = value
                os.environ[key] = value
        
        return env_vars

def main():
    """CLI interface for secrets management"""
    import argparse
    from datetime import datetime
    
    parser = argparse.ArgumentParser(description='Telnyx MCP Server Secrets Manager')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Set secret command
    set_parser = subparsers.add_parser('set', help='Set a secret value')
    set_parser.add_argument('key', help='Secret key name')
    set_parser.add_argument('value', help='Secret value')
    set_parser.add_argument('--description', help='Secret description')
    
    # Get secret command
    get_parser = subparsers.add_parser('get', help='Get a secret value')
    get_parser.add_argument('key', help='Secret key name')
    get_parser.add_argument('--show-value', action='store_true', help='Show actual secret value')
    
    # List secrets command
    list_parser = subparsers.add_parser('list', help='List all secrets')
    list_parser.add_argument('--json', action='store_true', help='Output in JSON format')
    
    # Delete secret command
    delete_parser = subparsers.add_parser('delete', help='Delete a secret')
    delete_parser.add_argument('key', help='Secret key name')
    delete_parser.add_argument('--confirm', action='store_true', help='Skip confirmation prompt')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate Telnyx API key')
    validate_parser.add_argument('--key', help='API key to validate (default: from secrets/env)')
    
    # Setup command
    setup_parser = subparsers.add_parser('setup', help='Setup environment variables from secrets')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = SecretsManager()
    
    if args.command == 'set':
        manager.set_secret(args.key, args.value, args.description)
        print(f"Secret '{args.key}' has been set")
    
    elif args.command == 'get':
        value = manager.get_secret(args.key)
        if value:
            if args.show_value:
                print(value)
            else:
                print(f"Secret '{args.key}' is set (use --show-value to display)")
        else:
            print(f"Secret '{args.key}' not found")
    
    elif args.command == 'list':
        secrets = manager.list_secrets()
        if args.json:
            print(json.dumps(secrets, indent=2))
        else:
            if secrets:
                print("Stored secrets:")
                for key, info in secrets.items():
                    print(f"  • {key}: {info['description']} (created: {info['created_at']})")
            else:
                print("No secrets stored")
    
    elif args.command == 'delete':
        if not args.confirm:
            response = input(f"Delete secret '{args.key}'? [y/N]: ")
            if response.lower() != 'y':
                print("Cancelled")
                return
        
        if manager.delete_secret(args.key):
            print(f"Secret '{args.key}' has been deleted")
        else:
            print(f"Secret '{args.key}' not found")
    
    elif args.command == 'validate':
        result = manager.validate_telnyx_api_key(args.key)
        print(f"\nTelnyx API Key Validation Results:")
        print(f"Key present: {'✅' if result['key_present'] else '❌'}")
        print(f"Format valid: {'✅' if result['format_valid'] else '❌'}")
        print(f"Connectivity test: {result['connectivity_test']}")
        print(f"Overall valid: {'✅' if result['valid'] else '❌'}")
        
        if result['issues']:
            print("\nIssues:")
            for issue in result['issues']:
                print(f"  • {issue}")
        
        if result['recommendations']:
            print("\nRecommendations:")
            for rec in result['recommendations']:
                print(f"  • {rec}")
    
    elif args.command == 'setup':
        env_vars = manager.setup_environment()
        print(f"Set {len(env_vars)} environment variables from secrets")
        for key in env_vars.keys():
            print(f"  • {key}")

if __name__ == "__main__":
    main()