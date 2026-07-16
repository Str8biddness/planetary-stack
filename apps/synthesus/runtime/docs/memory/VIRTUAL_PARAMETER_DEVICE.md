# Virtual Parameter Device

The Virtual Parameter Device (VPD) treats Knowledge Cloud parameters as virtual
hardware mapped into the VMM. The cloud remains the backing store; the guest and
C++ reasoning modules see a stable MMIO-style register block.

## Device Model

`synthesus::kernel::vmm::VirtualParameterDevice` implements the VMM
`MMIODevice` interface and defaults to this physical window:

| Offset | Name | Access | Meaning |
| --- | --- | --- | --- |
| `0x00` | `MAGIC` | RO | `0x56504431` (`VPD1`) |
| `0x08` | `VERSION` | RO | Selected parameter version |
| `0x10` | `PARAMETER_COUNT` | RO | Number of mapped parameters |
| `0x18` | `SELECTED_INDEX` | RW | Active parameter slot |
| `0x20` | `SELECTED_SIZE` | RO | Active parameter byte length |
| `0x28` | `DATA_OFFSET` | RW | Read cursor within active parameter |
| `0x30` | `DATA_LENGTH` | RW | Optional read limit; `0` means unrestricted |
| `0x38` | `KEY_HASH` | RO | Host hash of active parameter key |
| `0x40` | `STATUS` | RO | `1` when a selected parameter is available |
| `0x100..` | `DATA_WINDOW` | RO | Parameter bytes |

The VMM dispatches `KVM_EXIT_MMIO` to registered devices. A guest read outside
normal RAM at `0xF0000000 + offset` is serviced by VPD when the address falls in
the VPD range.

## EmulEngine Integration

`EmulEngine` recognizes parameter targets when:

- `EmulConfig.target_hardware` starts with `parameter:` or `param:`
- `optimization_flags` contains `parameter` or `vpd`
- the target name contains `knowledge_parameter`

For those targets, `EmulEngine` calls the installed parameter lookup callback,
stores the returned bytes in VPD, and registers the device with the VMM before
guest execution.

Python bridge example:

```python
engine = _synthesus_kernel.EmulEngine()
engine.set_parameter_lookup(lambda key: cloud.fetch_parameter(key))

config = _synthesus_kernel.EmulConfig()
config.target_hardware = "parameter:lore/ironhaven_watch"
config.optimization_flags = ["vpd"]

engine.initialize()
engine.generate_abstraction(config)
engine.run_abstraction()
```

## Hex-View Dump API

The AIOS server exposes the active VPD state through:

```text
GET /api/kernel/vpd/dump
```

The endpoint is authenticated with the same `X-API-Key` contract as other AIOS
kernel endpoints. It returns a JSON snapshot from
`VirtualParameterDevice::dump()`:

```json
{
  "device": "VirtualParameterDevice",
  "base_address": 4026531840,
  "base_address_hex": "0x00000000F0000000",
  "size": 8192,
  "data_window_offset": 256,
  "data_window_offset_hex": "0x0000000000000100",
  "parameter_count": 1,
  "registers": [
    {
      "name": "MAGIC",
      "offset": 0,
      "offset_hex": "0x0000000000000000",
      "absolute_address": 4026531840,
      "absolute_address_hex": "0x00000000F0000000",
      "value": 1448100913,
      "value_hex": "0x0000000056504431",
      "access": "ro"
    }
  ],
  "selected_parameter": {
    "available": true,
    "index": 0,
    "key": "lore/ironhaven_watch",
    "version": 1,
    "size": 128,
    "data_offset": 0,
    "data_length": 0,
    "bytes": [86, 80, 68],
    "hex": "565044"
  }
}
```

Schema proposal:

| Field | Type | Meaning |
| --- | --- | --- |
| `device` | string | Stable device name, currently `VirtualParameterDevice` |
| `base_address` / `base_address_hex` | integer / string | MMIO base, default `0xF0000000` |
| `size` | integer | Mapped MMIO window size in bytes |
| `data_window_offset` / `data_window_offset_hex` | integer / string | Offset where parameter bytes begin |
| `parameter_count` | integer | Number of mapped parameters |
| `registers[]` | array | Register snapshots with `name`, `offset`, `absolute_address`, `value`, hex mirrors, and `access` |
| `selected_parameter` | object | Active parameter metadata and exported byte window |
| `selected_parameter.bytes` | integer array | Raw selected bytes as JSON-safe unsigned byte values |
| `selected_parameter.hex` | string | Same selected bytes as contiguous uppercase hex for hex-view rendering |

## Reasoning Module Access

C++ reasoning modules such as `reasoning/ppbrs.cpp` should use a small
host-side adapter instead of hard-coding cloud clients. The adapter can read
from the same `VirtualParameterDevice` instance in unit tests and from MMIO in
guest/sandbox execution.

Recommended shape:

```cpp
struct VpdMmioView {
    volatile uint64_t* regs;
    volatile uint8_t* data;

    uint64_t count() const { return regs[0x10 / 8]; }
    void select(uint64_t index) const { regs[0x18 / 8] = index; }
    uint64_t selected_size() const { return regs[0x20 / 8]; }
    uint8_t byte_at(uint64_t offset) const {
        regs[0x28 / 8] = offset;
        return data[0];
    }
};
```

For `ppbrs.cpp`, the practical first use is reading a selected parameter vector
as a weight table or token-prior blob before scoring patterns. Keep PPBRS
source-compatible by making the adapter optional:

- no VPD attached: existing in-memory pattern scoring path
- VPD attached: read parameter bytes from the MMIO view and apply them as
  confidence priors or pattern weights

That keeps Python orchestration and synchronous tests intact while allowing the
same reasoning code to run against virtual hardware inside the VMM.
