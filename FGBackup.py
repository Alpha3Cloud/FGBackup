#!/usr/bin/env python3
"""
Fortinet Backup CLI Tool
A standalone command-line tool for backing up Fortinet firewall configurations.
"""

import os
import sys
import yaml
import json
import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click
import paramiko
from colorama import init, Fore, Style
from getpass import getpass

# Initialize colorama for cross-platform colored output
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fortinet_backup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class FortinetSSHClient:
    """SSH client for connecting to Fortinet devices."""
    
    def __init__(self, host: str, username: str, password: str, port: int = 22, timeout: int = 30):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.ssh = None
        self.shell = None
    
    def connect(self) -> bool:
        """Establish SSH connection to Fortinet device."""
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            click.echo(f"{Fore.YELLOW}Connecting to {self.host}:{self.port}...")
            
            self.ssh.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=self.timeout,
                allow_agent=False,
                look_for_keys=False
            )
            
            # Create interactive shell for FortiOS
            self.shell = self.ssh.invoke_shell()
            
            # Wait for initial prompt and clear it
            self._wait_for_prompt()
            
            click.echo(f"{Fore.GREEN}✓ Connected successfully to {self.host}")
            logger.info(f"Successfully connected to {self.host}")
            return True
            
        except Exception as e:
            click.echo(f"{Fore.RED}✗ Connection failed to {self.host}: {str(e)}")
            logger.error(f"Connection failed to {self.host}: {str(e)}")
            return False
    
    def disconnect(self):
        """Close SSH connection."""
        if self.shell:
            self.shell.close()
        if self.ssh:
            self.ssh.close()
        click.echo(f"{Fore.BLUE}Disconnected from {self.host}")
    
    def _wait_for_prompt(self, timeout: int = 10) -> str:
        """Wait for command prompt and return output."""
        output = ""
        start_time = datetime.now()
        
        while True:
            if self.shell.recv_ready():
                data = self.shell.recv(1024).decode('utf-8', errors='ignore')
                output += data
                
                # Look for common FortiOS prompts
                if any(prompt in output for prompt in ['# ', '$ ', '> ', 'login:', 'Password:']):
                    break
            
            if (datetime.now() - start_time).seconds > timeout:
                break
        
        return output
    
    def execute_command(self, command: str, timeout: int = 30, show_progress: bool = False) -> Tuple[bool, str]:
        """Execute command on Fortinet device."""
        try:
            if not self.shell:
                return False, "No active SSH connection"
            
            # Send command
            self.shell.send(command + '\n')
            
            # Initialize tracking
            output = ""
            start_time = datetime.now()
            last_size = 0
            
            if show_progress:
                click.echo(f"{Fore.YELLOW}📥 Downloading configuration data...")
            
            while True:
                if self.shell.recv_ready():
                    data = self.shell.recv(4096).decode('utf-8', errors='ignore')
                    output += data
                    
                    # Show simple progress
                    if show_progress and len(output) > last_size + 5000:  # Every 5KB
                        click.echo(f"{Fore.CYAN}   Downloaded: {len(output):,} bytes...")
                        last_size = len(output)
                        
                    # Handle pagination - look for "--More--" prompt
                    if "--More--" in data:
                        click.echo(f"{Fore.YELLOW}📄 Handling pagination...")
                        self.shell.send(' ')  # Send space to continue
                        continue
                    
                    # Check if command completed (look for prompt)
                    if output.strip().endswith('#') or output.strip().endswith('$'):
                        break
                
                # Check timeout
                if (datetime.now() - start_time).seconds > timeout:
                    click.echo(f"{Fore.RED}⏰ Command timeout reached")
                    break
                    
                # Small delay to prevent excessive CPU usage
                time.sleep(0.01)
            
            if show_progress:
                click.echo(f"{Fore.GREEN}✅ Download complete: {len(output):,} bytes")
            
            return True, output
            
        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}")
            return False, str(e)
    
    def get_system_info(self) -> Dict:
        """Get basic system information."""
        info = {}
        
        # Get system status
        success, output = self.execute_command("get system status")
        if success:
            for line in output.split('\n'):
                if 'Version:' in line:
                    info['version'] = line.split(':', 1)[1].strip()
                elif 'Serial-Number:' in line:
                    info['serial'] = line.split(':', 1)[1].strip()
                elif 'Hostname:' in line:
                    info['hostname'] = line.split(':', 1)[1].strip()
        
        return info
    
    def backup_configuration(self, backup_type: str = 'full') -> Tuple[bool, str, Dict]:
        """Backup Fortinet configuration."""
        try:
            # Configure console settings to disable pagination
            click.echo(f"{Fore.YELLOW}⚙️  Configuring console...")
            self.execute_command("config system console")
            self.execute_command("set output standard")
            self.execute_command("end")
            
            # Determine backup command
            if backup_type == 'full':
                command = "show full-configuration"
            else:
                command = "show"
            
            click.echo(f"{Fore.CYAN}🚀 Executing backup command: {command}")
            click.echo(f"{Fore.YELLOW}Large configurations may take several minutes...")
            
            # Execute backup command with progress
            success, config_data = self.execute_command(command, timeout=120, show_progress=True)
            
            if not success:
                return False, "Failed to execute backup command", {}
            
            # Get system info
            click.echo(f"{Fore.YELLOW}📊 Gathering system information...")
            system_info = self.get_system_info()
            
            # Clean configuration data
            click.echo(f"{Fore.YELLOW}🧹 Processing configuration...")
            config_data = self._clean_config_output(config_data)
            
            if len(config_data.strip()) < 100:
                return False, "Configuration data seems incomplete", {}
            
            click.echo(f"{Fore.GREEN}✅ Configuration backup completed ({len(config_data):,} bytes)")
            return True, config_data, system_info
            
        except Exception as e:
            logger.error(f"Backup failed: {str(e)}")
            return False, str(e), {}
    
    def _clean_config_output(self, output: str) -> str:
        """Clean configuration output by removing command echoes, prompts, and pagination artifacts."""
        lines = output.split('\n')
        cleaned_lines = []
        
        skip_until_config = True
        for line in lines:
            line_stripped = line.strip()
            
            # Skip until we find the actual configuration
            if skip_until_config:
                if line_stripped.startswith('#config-version=') or line_stripped.startswith('config '):
                    skip_until_config = False
                    cleaned_lines.append(line)
                continue
            
            # Skip command prompts, echoes, and pagination artifacts
            if (line_stripped.endswith('#') or 
                line_stripped.endswith('$') or 
                line_stripped.startswith('show') or
                line_stripped == '--More--' or
                'Handling pagination...' in line_stripped or
                'Downloaded:' in line_stripped):
                continue
            
            # Skip empty lines at the beginning but keep them in config
            if line_stripped or cleaned_lines:
                cleaned_lines.append(line)
        
        # Remove trailing empty lines
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()
        
        return '\n'.join(cleaned_lines)


class BackupManager:
    """Manages backup files and operations."""
    
    def __init__(self, base_path: str = "./backups"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
        
    def save_backup(self, device_name: str, config_data: str, backup_type: str, 
                   system_info: Dict) -> Tuple[bool, str]:
        """Save backup to file with metadata."""
        try:
            click.echo(f"{Fore.YELLOW}💾 Saving backup...")
            
            # Create device directory
            device_path = self.base_path / self._sanitize_filename(device_name)
            device_path.mkdir(exist_ok=True)
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{device_name}_{backup_type}_{timestamp}.cfg"
            filepath = device_path / filename
            
            # Calculate checksum
            checksum = hashlib.sha256(config_data.encode()).hexdigest()
            
            # Save configuration file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(config_data)
            
            # Create metadata
            metadata = {
                'device_name': device_name,
                'backup_type': backup_type,
                'timestamp': timestamp,
                'filename': filename,
                'file_size': len(config_data),
                'checksum': checksum,
                'system_info': system_info
            }
            
            # Save metadata file
            metadata_file = filepath.with_suffix('.json')
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, default=str)
            
            click.echo(f"{Fore.GREEN}✓ Backup saved: {filepath}")
            click.echo(f"{Fore.CYAN}  File size: {len(config_data):,} bytes")
            click.echo(f"{Fore.CYAN}  Checksum: {checksum[:16]}...")
            
            logger.info(f"Backup saved for {device_name}: {filepath}")
            return True, str(filepath)
            
        except Exception as e:
            click.echo(f"{Fore.RED}✗ Failed to save backup: {str(e)}")
            logger.error(f"Failed to save backup: {str(e)}")
            return False, str(e)
    
    def list_backups(self, device_name: str = None) -> List[Dict]:
        """List available backups."""
        backups = []
        
        if device_name:
            # List backups for specific device
            device_path = self.base_path / self._sanitize_filename(device_name)
            if device_path.exists():
                backups.extend(self._scan_device_backups(device_path, device_name))
        else:
            # List all backups
            for device_dir in self.base_path.iterdir():
                if device_dir.is_dir():
                    backups.extend(self._scan_device_backups(device_dir, device_dir.name))
        
        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x['timestamp'], reverse=True)
        return backups
    
    def _scan_device_backups(self, device_path: Path, device_name: str) -> List[Dict]:
        """Scan device directory for backups."""
        backups = []
        
        for metadata_file in device_path.glob("*.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Check if corresponding config file exists
                config_file = metadata_file.with_suffix('.cfg')
                if config_file.exists():
                    metadata['config_file'] = str(config_file)
                    metadata['metadata_file'] = str(metadata_file)
                    backups.append(metadata)
                    
            except Exception as e:
                logger.warning(f"Failed to read metadata {metadata_file}: {str(e)}")
                continue
        
        return backups
    
    def verify_backup(self, config_file: str) -> Tuple[bool, str]:
        """Verify backup integrity."""
        try:
            config_path = Path(config_file)
            metadata_path = config_path.with_suffix('.json')
            
            if not config_path.exists():
                return False, "Configuration file not found"
            
            if not metadata_path.exists():
                return False, "Metadata file not found"
            
            # Read metadata
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # Read and verify config file
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = f.read()
            
            # Calculate current checksum
            current_checksum = hashlib.sha256(config_data.encode()).hexdigest()
            stored_checksum = metadata.get('checksum', '')
            
            if current_checksum == stored_checksum:
                return True, "Backup integrity verified"
            else:
                return False, f"Checksum mismatch: expected {stored_checksum[:16]}..., got {current_checksum[:16]}..."
                
        except Exception as e:
            return False, str(e)
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem safety."""
        import re
        # Replace invalid characters with underscores
        return re.sub(r'[<>:"/\\|?*]', '_', filename)


def load_config(config_file: str) -> Dict:
    """Load device configuration from YAML file."""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        click.echo(f"{Fore.RED}✗ Failed to load config file {config_file}: {str(e)}")
        return {}


def create_sample_config():
    """Create a sample configuration file."""
    sample_config = {
        'devices': [
            {
                'name': 'firewall-01',
                'host': '192.168.1.1',
                'username': 'admin',
                'password': 'password123',
                'port': 22
            },
            {
                'name': 'firewall-02', 
                'host': '192.168.1.2',
                'username': 'admin',
                'password': 'password123',
                'port': 22
            }
        ],
        'backup_settings': {
            'default_type': 'full',
            'backup_path': './backups',
            'timeout': 60
        }
    }
    
    with open('devices.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(sample_config, f, default_flow_style=False)
    
    click.echo(f"{Fore.GREEN}✓ Sample configuration created: devices.yaml")


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """
    Fortinet Backup CLI Tool
    
    A command-line tool for backing up Fortinet firewall configurations.
    """
    pass


@cli.command()
@click.option('--host', required=True, help='Fortinet device IP address')
@click.option('--username', required=True, help='Username for SSH connection')
@click.option('--password', help='Password for SSH connection (will prompt if not provided)')
@click.option('--port', default=22, help='SSH port (default: 22)')
@click.option('--type', 'backup_type', default='full', 
              type=click.Choice(['full', 'config']),
              help='Backup type (default: full)')
@click.option('--output', help='Output directory (default: ./backups)')
@click.option('--timeout', default=30, help='SSH timeout in seconds (default: 30)')
def backup(host, username, password, port, backup_type, output, timeout):
    """Backup a single Fortinet device."""
    
    if not password:
        password = getpass("Password: ")
    
    # Initialize backup manager
    backup_manager = BackupManager(output or "./backups")
    
    # Create SSH client
    client = FortinetSSHClient(host, username, password, port, timeout)
    
    try:
        # Connect to device
        if not client.connect():
            sys.exit(1)
        
        # Perform backup
        success, config_data, system_info = client.backup_configuration(backup_type)
        
        if success:
            device_name = system_info.get('hostname', host.replace('.', '_'))
            backup_manager.save_backup(device_name, config_data, backup_type, system_info)
            click.echo(f"{Fore.GREEN}✓ Backup completed successfully")
        else:
            click.echo(f"{Fore.RED}✗ Backup failed: {config_data}")
            sys.exit(1)
            
    finally:
        client.disconnect()


@cli.command()
@click.option('--config', default='devices.yaml', help='Configuration file (default: devices.yaml)')
@click.option('--device', help='Backup specific device only')
@click.option('--type', 'backup_type', default='full',
              type=click.Choice(['full', 'config']),
              help='Backup type (default: full)')
@click.option('--parallel', is_flag=True, help='Run backups in parallel (use with caution)')
def backup_all(config, device, backup_type, parallel):
    """Backup multiple devices from configuration file."""
    
    # Load configuration
    config_data = load_config(config)
    if not config_data:
        click.echo(f"{Fore.YELLOW}💡 Use 'python FGBackup.py init' to create a sample configuration")
        sys.exit(1)
    
    devices = config_data.get('devices', [])
    backup_settings = config_data.get('backup_settings', {})
    
    # Filter devices if specified
    if device:
        devices = [d for d in devices if d.get('name') == device]
        if not devices:
            click.echo(f"{Fore.RED}✗ Device '{device}' not found in configuration")
            sys.exit(1)
    
    if not devices:
        click.echo(f"{Fore.RED}✗ No devices found in configuration")
        sys.exit(1)
    
    # Initialize backup manager
    backup_path = backup_settings.get('backup_path', './backups')
    backup_manager = BackupManager(backup_path)
    
    # Process devices
    success_count = 0
    total_count = len(devices)
    
    click.echo(f"{Fore.CYAN}Starting backup for {total_count} device(s)...")
    
    for device_config in devices:
        device_name = device_config.get('name', 'unknown')
        click.echo(f"\n{Fore.YELLOW}{'='*50}")
        click.echo(f"{Fore.YELLOW}Processing device: {device_name}")
        click.echo(f"{Fore.YELLOW}{'='*50}")
        
        # Create SSH client
        client = FortinetSSHClient(
            host=device_config['host'],
            username=device_config['username'],
            password=device_config.get('password', ''),
            port=device_config.get('port', 22),
            timeout=backup_settings.get('timeout', 30)
        )
        
        try:
            # Connect and backup
            if client.connect():
                success, config_data, system_info = client.backup_configuration(backup_type)
                
                if success:
                    backup_manager.save_backup(device_name, config_data, backup_type, system_info)
                    success_count += 1
                    click.echo(f"{Fore.GREEN}✓ {device_name}: Backup completed")
                else:
                    click.echo(f"{Fore.RED}✗ {device_name}: Backup failed - {config_data}")
            else:
                click.echo(f"{Fore.RED}✗ {device_name}: Connection failed")
                
        except Exception as e:
            click.echo(f"{Fore.RED}✗ {device_name}: Error - {str(e)}")
            
        finally:
            client.disconnect()
    
    # Summary
    click.echo(f"\n{Fore.CYAN}{'='*50}")
    click.echo(f"{Fore.CYAN}Backup Summary")
    click.echo(f"{Fore.CYAN}{'='*50}")
    click.echo(f"Total devices: {total_count}")
    click.echo(f"{Fore.GREEN}Successful: {success_count}")
    click.echo(f"{Fore.RED}Failed: {total_count - success_count}")


@cli.command()
@click.option('--device', help='List backups for specific device only')
@click.option('--path', default='./backups', help='Backup directory (default: ./backups)')
def list_backups(device, path):
    """List available backup files."""
    
    backup_manager = BackupManager(path)
    backups = backup_manager.list_backups(device)
    
    if not backups:
        if device:
            click.echo(f"{Fore.YELLOW}No backups found for device: {device}")
        else:
            click.echo(f"{Fore.YELLOW}No backups found in: {path}")
        return
    
    # Display backups in table format
    click.echo(f"\n{Fore.CYAN}Available Backups:")
    click.echo(f"{Fore.CYAN}{'='*80}")
    
    header = f"{'Device':<15} {'Type':<6} {'Timestamp':<17} {'Size':<10} {'Checksum':<10}"
    click.echo(f"{Fore.WHITE}{header}")
    click.echo(f"{Fore.CYAN}{'-'*80}")
    
    for backup in backups:
        device_name = backup.get('device_name', 'unknown')[:14]
        backup_type = backup.get('backup_type', 'unknown')[:5]
        timestamp = backup.get('timestamp', 'unknown')[:16]
        file_size = f"{backup.get('file_size', 0):,}"[:9]
        checksum = backup.get('checksum', 'unknown')[:9]
        
        row = f"{device_name:<15} {backup_type:<6} {timestamp:<17} {file_size:<10} {checksum:<10}"
        click.echo(row)
    
    click.echo(f"{Fore.CYAN}{'-'*80}")
    click.echo(f"Total: {len(backups)} backup(s)")


@cli.command()
@click.argument('backup_file')
def verify(backup_file):
    """Verify backup file integrity."""
    
    backup_manager = BackupManager()
    success, message = backup_manager.verify_backup(backup_file)
    
    if success:
        click.echo(f"{Fore.GREEN}✓ {message}")
    else:
        click.echo(f"{Fore.RED}✗ {message}")
        sys.exit(1)


@cli.command()
@click.option('--host', required=True, help='Fortinet device IP address')
@click.option('--username', required=True, help='Username for SSH connection')
@click.option('--password', help='Password for SSH connection')
@click.option('--port', default=22, help='SSH port (default: 22)')
def test(host, username, password, port):
    """Test connection to Fortinet device."""
    
    if not password:
        password = getpass("Password: ")
    
    client = FortinetSSHClient(host, username, password, port)
    
    try:
        if client.connect():
            # Get system info
            system_info = client.get_system_info()
            
            click.echo(f"{Fore.GREEN}✓ Connection test successful!")
            click.echo(f"{Fore.CYAN}Device Information:")
            for key, value in system_info.items():
                if key != 'interfaces_config':  # Skip large interface config
                    click.echo(f"  {key}: {value}")
        else:
            click.echo(f"{Fore.RED}✗ Connection test failed")
            sys.exit(1)
            
    finally:
        client.disconnect()


@cli.command()
def init():
    """Create a sample configuration file."""
    
    if os.path.exists('devices.yaml'):
        if not click.confirm(f"{Fore.YELLOW}devices.yaml already exists. Overwrite?"):
            return
    
    create_sample_config()


if __name__ == '__main__':
    cli()