# Usage Guide

This guide explains how to run backups, track success, and restore configurations.

## Running Backups
- To back up a single device:
  ```bash
  python fgbackup.py --device <device_name>
  ```

- To back up all devices:
  ```bash
  python fgbackup.py --all-devices
  ```

- To run with verbose logging:
  ```bash
  python fgbackup.py --all-devices --verbose
  ```

## Tracking Success
- Logs are stored in the `logs/` directory by default.
- Failed backups trigger alerts (via email, Slack, or Teams if configured).
- You can view backup history using:
  ```bash
  python fgbackup.py --history
  ```

## Restoring Configurations
1. Identify the desired backup from the `backups/` folder (or cloud storage).
2. Push the backup to the device:
   ```bash
   python fgbackup.py --restore <device_name> --file backups/device_name/config-YYYYMMDD.conf
   ```
3. FGBackup will validate and apply the configuration.

## Notes
- Always validate the diff before restoring:
  ```bash
  python fgbackup.py --diff <device_name> --file backups/device_name/config-YYYYMMDD.conf
  ```
