# UART File Transfer Feature

## Overview

This feature enables secure file transfer (typically ZIP archives) from a PC to the device via UART with robust error checking:

- **Block-level verification**: CRC32 checksum for each data block
- **File-level verification**: MD5 hash for entire file
- **Automatic retry**: Failed blocks are retried up to 3 times
- **Progress tracking**: Real-time progress display

## Architecture

```
┌─────────────────┐                          ┌──────────────────┐
│  PC (Sender)    │                          │ Device (Receiver)│
│                 │                          │                  │
│ send_file_uart  │ ──── UART (38400) ────>  │ uart_control.py  │
│     .py         │                          │                  │
└─────────────────┘                          └──────────────────┘
```

## Protocol

Files are transferred using JSON commands over UART (38400 baud by default):
- **file_start**: Initialize transfer with file metadata (name, size, MD5)
- **file_block**: Send data blocks (650 bytes each, Base64 encoded, CRC32 verified)
- **file_end**: Finalize transfer with MD5 verification
- **file_cancel**: Abort transfer

For complete protocol specification, see [PROTOCOL_SPECIFICATION.md](PROTOCOL_SPECIFICATION.md)

## Usage

### Receiver Side (Device)

The file transfer receiver is integrated into `uart_control.py` (version 3.1.0+):

```bash
# No special configuration needed
# Just run uart_control.py as usual
python uart_control.py
```

Received files are saved to `./tmp/<filename>` (relative to current directory)

### Sender Side (PC)

Use the standalone `send_file_uart.py` tool:

#### Basic Usage
```bash
# Windows
python send_file_uart.py firmware.zip --port COM3

# Linux/macOS
python send_file_uart.py firmware.zip --port /dev/ttyUSB0
```

#### Advanced Options
```bash
python send_file_uart.py <file> [options]

Options:
  --port PORT        UART port (default: COM3)
  --baudrate RATE    Baud rate (default: 38400)
  --timeout SEC      Response timeout in seconds (default: 5)
  -h, --help         Show help message
```

#### Examples
```bash
# Send with different baud rate
python send_file_uart.py update.zip --port COM5 --baudrate 115200

# Linux with custom timeout
python send_file_uart.py data.zip --port /dev/ttyUSB0 --timeout 10
```

## Performance

### Transfer Time Estimation

| File Size | Blocks | Est. Time @ 38400 baud |
|-----------|--------|------------------------|
| 100 KB    | 158    | ~38 seconds            |
| 500 KB    | 788    | ~3 minutes             |
| 1 MB      | 1613   | ~6.2 minutes           |
| 5 MB      | 8026   | ~30-34 minutes         |

**Note**: Actual time depends on UART baud rate, block retry rate, device processing speed, and system overhead.

## Error Handling

### Common Errors

| Error | Reason | Solution |
|-------|--------|----------|
| `transfer_in_progress` | Another transfer is active | Wait or cancel existing transfer |
| `disk_full` | Not enough space on device | Free up space on ./tmp |
| `crc_mismatch` | Data corruption during transfer | Automatic retry (up to 3 times) |
| `md5_mismatch` | File corrupted or incomplete | Restart transfer |
| `timeout` | Device not responding | Check UART connection |

### Retry Logic

- **Per-block retries**: Up to 3 attempts per block
- **Consecutive error limit**: Abort after 5 consecutive block failures
- **Automatic**: No manual intervention needed for transient errors

## Logging

### Sender Side (PC)
```
✓ Connected to COM3 at 38400 baud
⏳ Calculating MD5 hash...
✓ MD5: 5d41402abc4b2a76b9719d911017c592
📤 Step 1: Initiating file transfer...
✓ Device ready
📤 Step 2: Transferring file blocks...
  Progress: 50/1613 blocks (3.1%)
  Progress: 100/1613 blocks (6.2%)
  ...
✓ All 1613 blocks sent successfully
📤 Step 3: Finalizing transfer...
✓ Transfer completed successfully!
```

### Receiver Side (Device)
Check `log/uart_log.txt`:
```
[INFO]: File transfer started: firmware.zip, 1613 blocks
[INFO]: File transfer progress: 50/1613 (3.1%)
[INFO]: File transfer progress: 100/1613 (6.2%)
...
[INFO]: File transfer completed successfully: ./tmp/firmware.zip (1048576 bytes, MD5: 5d41...)
```

## Troubleshooting

### Transfer Fails Immediately
1. Check UART port is correct
2. Verify baud rate matches on both sides
3. Ensure uart_control.py is running on device
4. Check device has enough disk space

### Frequent CRC Errors
1. Check UART cable quality
2. Reduce baud rate
3. Check for electrical interference
4. Verify device is not under heavy load

### Transfer Hangs
1. Check timeout setting (increase if needed)
2. Verify device is responsive
3. Check UART buffer sizes
4. Monitor device logs for errors

### MD5 Mismatch
1. This indicates data corruption despite CRC checks
2. Retry the entire transfer
3. Check for systemic issues (cable, power, etc.)

## Notes

- Files are saved to `./tmp/<filename>` on the device
- JSON commands coexist with legacy commands (e.g., `?Asset`, `Profile|1`)
- For technical details and protocol specification, see [PROTOCOL_SPECIFICATION.md](PROTOCOL_SPECIFICATION.md)
