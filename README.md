# protocol-codegen-cpp

A code generator that takes a JSON protocol definition and produces C++ structs with `serialize` / `deserialize` methods.

## Overview

```
protocol.json  →  protocol-codegen-cpp  →  generated_messages.hpp
                                        →  generated_messages.cpp
```

Each message becomes a C++ struct with:
- A `static constexpr uint32_t ID` identifying the message
- A `serialize() const` method returning `std::vector<uint8_t>`
- A `static deserialize(const std::vector<uint8_t>&)` factory method

## Usage

```sh
python3 generate_protocol.py [-n <namespace>] path_to.json
```

| Option | Default | Description |
|--------|---------|-------------|
| `-n <namespace>` | `ptc` | Namespace wrapping all generated types |

Outputs:
- `generated_messages.hpp`
- `generated_messages.cpp`

## Protocol definition

```json
{
  "endianness": "big",
  "structs": { ... },
  "messages": { ... }
}
```

### Top-level fields

| Field        | Required | Values             | Description                          |
|--------------|----------|--------------------|--------------------------------------|
| `endianness` | yes      | `"big"`, `"little"`| Byte order used for all multi-byte fields |
| `structs`    | no       | object             | Reusable data structures             |
| `messages`   | yes      | object             | The protocol messages                |

### Message fields

| Field        | Required | Description                                  |
|--------------|----------|----------------------------------------------|
| `id`         | yes      | Unique integer identifier (written as first byte) |
| `fields`     | yes      | List of field definitions                    |
| `compressed` | no       | If `true`, payload is LZ4-compressed (requires `liblz4`) |

### Field types

| Type            | C++ type              | Extra keys                                      |
|-----------------|-----------------------|-------------------------------------------------|
| `uint8`–`uint64`| `uint8_t`–`uint64_t`  | —                                               |
| `int8`–`int64`  | `int8_t`–`int64_t`    | —                                               |
| `float`         | `float`               | —                                               |
| `double`        | `double`              | —                                               |
| `string`        | `char[max_length]`    | `max_length` (int, required)                    |
| `fixed_array`   | `T[max_size]`         | `element_type`, `max_size`, a matching `*_count` field |
| `dynamic_array` | `std::vector<T>`      | `element_type`                                  |

> `fixed_array` requires a companion count field in the same message. The generator resolves it automatically from common naming patterns (e.g. `players` → `player_count`).

### Structs

Reusable composite types referenced as `element_type` in arrays. Supported field types inside a struct: all primitives, `string`, and `fixed_array`.

```json
"structs": {
  "PlayerInit": {
    "fields": [
      { "name": "id",   "type": "uint32" },
      { "name": "x",    "type": "float"  },
      { "name": "name", "type": "string", "max_length": 32 }
    ]
  }
}
```

## Example

**protocol.json**
```json
{
  "endianness": "big",
  "messages": {
    "LOGIN": {
      "id": 20,
      "fields": [
        { "name": "username", "type": "string", "max_length": 32 }
      ]
    }
  }
}
```

**Generated C++ (header)**
```cpp
namespace ptc {

struct LOGIN {
    static constexpr uint32_t ID = 20;

    char username[32];

    std::vector<uint8_t> serialize() const;
    static LOGIN deserialize(const std::vector<uint8_t>& data);
};

}  // namespace net
```

**Usage in C++**
```cpp
net::LOGIN msg;
std::strncpy(msg.username, "alice", 32);

std::vector<uint8_t> packet = msg.serialize();
ptc::LOGIN received = ptc::LOGIN::deserialize(packet);
```

## Requirements

- Python 3.8+
- C++17 (for the generated code)
- [liblz4](https://github.com/lz4/lz4) — only if any message uses `"compressed": true`
