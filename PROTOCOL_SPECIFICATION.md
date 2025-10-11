# File Transfer Protocol Specification

## Version: 1.0
## Last Updated: 2025-01-10

---

## 1. Overview

### 1.1 Purpose
This protocol enables reliable file transfer over UART with error detection and recovery.

### 1.2 Key Features
- **JSON-based commands**: Human-readable, easy to debug
- **Dual-layer verification**: CRC32 (per-block) + MD5 (whole-file)
- **Automatic retry**: Up to 3 attempts per failed block
- **Single-session design**: Simplified state management
- **Backward compatible**: Coexists with legacy commands

### 1.3 Use Cases
- Firmware updates
- Configuration file deployment
- Data collection/upload
- Log file retrieval
- Any binary file transfer over UART

---

## 2. Transport Layer

### 2.1 Physical Layer
- **Medium**: UART serial connection
- **Default baud**: 38400 bps (configurable)
- **Data bits**: 8
- **Parity**: None
- **Stop bits**: 1
- **Flow control**: None

### 2.2 Frame Format
```
<JSON_STRING>\n
```

- Each command/response is a single line
- Terminated by newline character (`\n`)
- UTF-8 encoding
- Maximum line length: Limited by UART buffer (typically 4-8 KB)

---

## 3. Command Specification

### 3.1 Command Structure

All commands follow this JSON structure:
```json
{
  "cmd": "command_name",
  "param1": "value1",
  "param2": "value2",
  ...
}
```

### 3.2 Command: `file_start`

**Direction**: Sender → Receiver

**Purpose**: Initialize file transfer session

**Request Format**:
```json
{
  "cmd": "file_start",
  "name": "<filename>",
  "size": <file_size_bytes>,
  "blocks": <total_blocks>,
  "md5": "<md5_hex_string>"
}
```

**Parameters**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cmd` | string | Yes | Must be "file_start" |
| `name` | string | Yes | Filename (basename only, no path) |
| `size` | integer | Yes | Total file size in bytes |
| `blocks` | integer | Yes | Number of data blocks |
| `md5` | string | Yes | MD5 hash (32 hex chars, lowercase) |

**Response Format (Success)**:
```json
{
  "cmd": "file_start",
  "status": "ready"
}
```

**Response Format (Error)**:
```json
{
  "cmd": "file_start",
  "status": "error",
  "reason": "<error_code>"
}
```

**Error Codes**:
- `transfer_in_progress`: Another transfer is already active
- `disk_full`: Insufficient disk space
- Other errors: Exception message returned as string in `reason` field

**Example**:
```json
Request:
{
  "cmd": "file_start",
  "name": "firmware.zip",
  "size": 102400,
  "blocks": 158,
  "md5": "5d41402abc4b2a76b9719d911017c592"
}

Response:
{
  "cmd": "file_start",
  "status": "ready"
}
```

---

### 3.3 Command: `file_block`

**Direction**: Sender → Receiver

**Purpose**: Transfer a single data block

**Request Format**:
```json
{
  "cmd": "file_block",
  "index": <block_index>,
  "crc32": "<crc32_hex>",
  "data": "<base64_data>"
}
```

**Parameters**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cmd` | string | Yes | Must be "file_block" |
| `index` | integer | Yes | Block index (0-based) |
| `crc32` | string | Yes | CRC32 checksum (8 hex chars, lowercase) |
| `data` | string | Yes | Base64-encoded block data |

**Block Size**:
- Raw data: 650 bytes (last block may be smaller)
- Base64 encoded: ~867 bytes
- JSON total size: ~934 bytes (within 1000-byte limit)
- Last block: File_size % 650 bytes

**Response Format (Success)**:
```json
{
  "cmd": "file_block",
  "index": <block_index>,
  "status": "ok"
}
```

**Response Format (Error - Retryable)**:
```json
{
  "cmd": "file_block",
  "index": <block_index>,
  "status": "error",
  "reason": "<error_code>",
  "retry": true
}
```

**Response Format (Error - Fatal)**:
```json
{
  "cmd": "file_block",
  "index": <block_index>,
  "status": "error",
  "reason": "<error_code>",
  "retry": false
}
```

**Error Codes**:
- `no_active_transfer`: No file_start command received (fatal)
- `invalid_base64`: Base64 decoding failed (retryable)
- `crc_mismatch`: CRC32 verification failed (retryable)
- `out_of_order`: Block received out of sequence (fatal)
- `write_failed`: Disk write error (fatal)

**Example**:
```json
Request:
{
  "cmd": "file_block",
  "index": 0,
  "crc32": "a3b5c7d9",
  "data": "UEsDBBQAAAAIAP1eMVf..."
}

Response (Success):
{
  "cmd": "file_block",
  "index": 0,
  "status": "ok"
}

Response (CRC Error):
{
  "cmd": "file_block",
  "index": 0,
  "status": "error",
  "reason": "crc_mismatch",
  "retry": true
}
```

---

### 3.4 Command: `file_end`

**Direction**: Sender → Receiver

**Purpose**: Finalize transfer and verify integrity

**Request Format**:
```json
{
  "cmd": "file_end"
}
```

**Response Format (Success)**:
```json
{
  "cmd": "file_end",
  "status": "success",
  "md5": "<calculated_md5>",
  "path": "<saved_file_path>",
  "size": <final_size_bytes>
}
```

**Response Format (Error)**:
```json
{
  "cmd": "file_end",
  "status": "error",
  "reason": "<error_code>",
  "expected": "<expected_md5>",
  "actual": "<calculated_md5>"
}
```

**Error Codes**:
- `no_active_transfer`: No transfer in progress
- `incomplete_transfer`: Not all blocks received
- `md5_mismatch`: File integrity check failed
- Other errors: Exception message returned as string in `reason` field

**Example**:
```json
Request:
{
  "cmd": "file_end"
}

Response (Success):
{
  "cmd": "file_end",
  "status": "success",
  "md5": "5d41402abc4b2a76b9719d911017c592",
  "path": "./tmp/firmware.zip",
  "size": 102400
}

Response (MD5 Mismatch):
{
  "cmd": "file_end",
  "status": "error",
  "reason": "md5_mismatch",
  "expected": "5d41402abc4b2a76b9719d911017c592",
  "actual": "7f89a3b2c4d5e6f71234567890abcdef"
}
```

---

### 3.5 Command: `file_cancel`

**Direction**: Sender → Receiver

**Purpose**: Abort ongoing transfer

**Request Format**:
```json
{
  "cmd": "file_cancel"
}
```

**Response Format**:
```json
{
  "cmd": "file_cancel",
  "status": "cancelled"
}
```

**Side Effects**:
- Temporary file deleted
- Transfer state reset
- No partial file saved

**Example**:
```json
Request:
{
  "cmd": "file_cancel"
}

Response:
{
  "cmd": "file_cancel",
  "status": "cancelled"
}
```

---

## 4. Transfer Flow

### 4.1 State Machine

```
┌──────────┐
│   IDLE   │
└─────┬────┘
      │ file_start
      ▼
┌──────────┐
│  READY   │
└─────┬────┘
      │ file_block
      ▼
┌──────────┐
│RECEIVING │◄──┐
└─────┬────┘   │ file_block (more blocks)
      │        │
      ├────────┘
      │ file_end
      ▼
┌──────────┐
│VERIFYING │
└─────┬────┘
      │
      ├───► SUCCESS ──► IDLE
      │
      └───► ERROR ────► IDLE

      * file_cancel from any state → IDLE
```

### 4.2 Typical Success Flow

```
Sender                          Receiver
  │                                │
  │ 1. Calculate file MD5          │
  │ 2. Split into blocks           │
  │                                │
  ├──── file_start ───────────────>│
  │                                ├─ Allocate temp file
  │                                ├─ Check disk space
  │<──── ready response ───────────┤
  │                                │
  ├──── file_block(0) ────────────>│
  │                                ├─ Decode Base64
  │                                ├─ Verify CRC32
  │                                ├─ Write to disk
  │<──── ok response ──────────────┤
  │                                │
  ├──── file_block(1) ────────────>│
  │<──── ok response ──────────────┤
  │                                │
  │     ... (blocks 2 to N-1)      │
  │                                │
  ├──── file_end ─────────────────>│
  │                                ├─ Close temp file
  │                                ├─ Calculate MD5
  │                                ├─ Verify MD5
  │                                ├─ Rename to final path
  │<──── success response ─────────┤
  │                                │
```

### 4.3 Error Recovery Flow

```
Sender                          Receiver
  │                                │
  ├──── file_block(5) ────────────>│
  │                                ├─ CRC mismatch!
  │<──── error/retry ──────────────┤
  │                                │
  ├──── file_block(5) [retry 1] ─>│
  │                                ├─ CRC mismatch!
  │<──── error/retry ──────────────┤
  │                                │
  ├──── file_block(5) [retry 2] ─>│
  │                                ├─ CRC OK
  │<──── ok response ──────────────┤
  │                                │
  │     Continue normal flow       │
```

---

## 5. Data Formats

### 5.1 CRC32 Calculation

**Algorithm**: IEEE 802.3 CRC32

**Python Implementation**:
```python
import zlib

def calculate_crc32(data: bytes) -> str:
    """Calculate CRC32 and return as 8-char hex string"""
    crc = zlib.crc32(data) & 0xffffffff
    return format(crc, '08x')
```

**Example**:
```python
data = b"Hello, World!"
crc32 = calculate_crc32(data)
# Result: "ec4ac3d0"
```

### 5.2 MD5 Calculation

**Algorithm**: MD5 hash (RFC 1321)

**Python Implementation**:
```python
import hashlib

def calculate_md5(file_path: str) -> str:
    """Calculate MD5 of entire file"""
    md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            md5.update(chunk)
    return md5.hexdigest()
```

**Example**:
```python
md5 = calculate_md5("firmware.zip")
# Result: "5d41402abc4b2a76b9719d911017c592"
```

### 5.3 Base64 Encoding

**Standard**: RFC 4648

**Python Implementation**:
```python
import base64

def encode_block(data: bytes) -> str:
    """Encode binary data to Base64 string"""
    return base64.b64encode(data).decode('ascii')

def decode_block(b64_str: str) -> bytes:
    """Decode Base64 string to binary data"""
    return base64.b64decode(b64_str)
```

---

## 6. Error Handling

### 6.1 Retry Strategy

**Block-level retries**:
- Maximum attempts: 3 per block
- Retry on: `crc_mismatch`, `invalid_base64`
- No retry on: `write_failed`, `disk_full`

**Consecutive error limit**:
- Abort if 5 consecutive blocks fail
- Prevents infinite retry loops

**Sender-side logic**:
```python
for retry in range(MAX_RETRIES):
    send_block()
    response = wait_response()

    if response.status == "ok":
        break
    elif response.retry == True:
        continue  # Try again
    else:
        abort_transfer()  # Fatal error
```

### 6.2 Timeout Handling

**Response timeouts**:
- `file_start`: 10 seconds
- `file_block`: 5 seconds
- `file_end`: 30 seconds (MD5 calculation)

**Sender behavior on timeout**:
1. Retry command (up to MAX_RETRIES)
2. If still no response, abort transfer
3. Optionally send `file_cancel`

### 6.3 Recovery from Interruption

**Current implementation**: No automatic recovery

**Manual recovery**:
1. Sender sends `file_cancel`
2. Wait for confirmation
3. Restart entire transfer

**Future enhancement**: Add resume capability

---

## 7. Performance Characteristics

### 7.1 Throughput Calculation

**Theoretical calculation:**
```
Block size (raw):        650 bytes
Block size (Base64):     867 bytes
Command overhead:        ~67 bytes
Response overhead:       ~50 bytes

Total bytes per block:   984 bytes
Bits per block:          7872 bits

At 38400 baud:
Time per block:          7872 / 38400 ≈ 0.205 seconds
Theoretical throughput:  650 / 0.205 ≈ 3.2 KB/s

For 1 MB file:
Blocks needed:           1613
Theoretical time:        1613 × 0.205 ≈ 331 seconds ≈ 5.5 minutes
```

**Actual test results (38400 baud):**
```
Test file:               1,577,513 bytes (1.5 MB)
Blocks sent:             2427
Transfer time:           794.8 seconds ≈ 13.2 minutes
Actual throughput:       1.9 KB/s

For 1 MB file (measured):
Actual time:             ~529 seconds ≈ 8.8 minutes
```

**Performance gap analysis:**
```
Theoretical time for 1 MB:  331 seconds
Actual time for 1 MB:       529 seconds
Overhead:                   +198 seconds (+60%)
```

**Overhead sources:**
- Receiver processing time (JSON parsing, Base64 decode, CRC32 calculation)
- UART buffer delays and flow control
- Round-trip acknowledgment latency
- File I/O operations (write, flush)
- MD5 calculation during file_end (up to several seconds for large files)

---

## 8. Compatibility

**Backward compatible with legacy commands**:
- JSON commands detected via `"cmd"` field
- Legacy commands (e.g., `?Asset`, `Profile|N`) unaffected
- Requires receiver version 3.1.0+

---

## 9. References

- RFC 4648: Base64 encoding
- RFC 1321: MD5 hash
- IEEE 802.3: CRC32 algorithm
- JSON specification: RFC 8259

---

## Appendix A: Command Summary

| Command | Direction | Purpose |
|---------|-----------|---------|
| `file_start` | S→R | Initialize transfer |
| `file_block` | S→R | Send data block |
| `file_end` | S→R | Finalize transfer |
| `file_cancel` | S→R | Abort transfer |

S = Sender (PC), R = Receiver (Device)

## Appendix B: Error Code Reference

| Code | Retryable | Description |
|------|-----------|-------------|
| `transfer_in_progress` | No | Transfer already active |
| `disk_full` | No | Insufficient disk space |
| `no_active_transfer` | No | No transfer started |
| `invalid_base64` | Yes | Base64 decode failed |
| `crc_mismatch` | Yes | Block CRC error |
| `out_of_order` | No | Block out of sequence |
| `write_failed` | No | Disk write error |
| `incomplete_transfer` | No | Missing blocks |
| `md5_mismatch` | No | File MD5 verification failed |

---

**End of Specification**
