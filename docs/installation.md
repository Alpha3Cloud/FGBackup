# Installation and Setup Guide

This guide explains how to install and configure FGBackup.

## Requirements
- Python 3.8+
- FortiGate devices with SSH or API access enabled
- Access credentials (username/password or API token)
- Optional: AWS S3 or Azure Blob for cloud storage

## Installation Steps
1. Clone the repository:
   ```bash
   git clone https://github.com/Alpha3Cloud/FGBackup.git
   cd FGBackup
   ```

2. Set up a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Configure your devices and storage:
   - Edit `config/devices.yml` to list your FortiGate devices.
   - Update `config/storage.yml` for local or cloud backup targets.

4. Run a test backup:
   ```bash
   python fgbackup.py --test
   ```

5. Set up a scheduled job (Linux example with cron):
   ```bash
   crontab -e
   # Add:
   0 2 * * * /path/to/venv/bin/python /path/to/FGBackup/fgbackup.py --all-devices
   ```

FGBackup is now set up to run automated backups.
