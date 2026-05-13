"""Generate C++ serialization/deserialization code from a JSON protocol definition."""

import json
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

# Type Information: Centralizes all type metadata

TYPE_INFO: Dict[str, Tuple[int, str]] = {
    "uint8": (1, "uint8_t"),
    "int8": (1, "int8_t"),
    "uint16": (2, "uint16_t"),
    "int16": (2, "int16_t"),
    "uint32": (4, "uint32_t"),
    "int32": (4, "int32_t"),
    "uint64": (8, "uint64_t"),
    "int64": (8, "int64_t"),
    "float": (4, "float"),
    "double": (8, "double"),
}

TYPE_MAP = {name: info[1] for name, info in TYPE_INFO.items()}


# Helper Functions


def indent(code: str, level: int = 1) -> str:
    """Indent code by level*4 spaces. Preserves trailing newlines without adding trailing spaces."""
    indent_str = "    " * level
    stripped = code.rstrip("\n")
    trailing = "\n" * (len(code) - len(stripped))
    return indent_str + stripped.replace("\n", "\n" + indent_str) + trailing


def get_type_bytes(field_type: str) -> int:
    """Get the size in bytes for a type."""
    return TYPE_INFO.get(field_type, (0, ""))[0]


def get_c_type(field_type: str) -> str:
    """Get the C++ type name for a type."""
    return TYPE_INFO.get(field_type, (0, ""))[1]


def load_protocol(json_path: str) -> dict:
    """Load and parse JSON protocol file."""
    try:
        with open(json_path, encoding="utf-8") as file:
            return json.load(file)
    except ValueError as e:
        print(f"invalid file: {e}")
        sys.exit(1)


# Validate


def validate_string_field(field: dict) -> bool:
    """Validate a string field has required properties."""
    if (
        "max_length" not in field
        or not isinstance(field["max_length"], int)
        or field["max_length"] <= 0
    ):
        print(f"Error: field '{field['name']}' has invalid 'max_length'")
        return False
    return True


def validate_array_element_type(
    element_type: str, field_name: str, structs: dict, allow_string: bool = True
) -> bool:
    """Validate that element_type is a valid type."""
    if element_type in TYPE_MAP or element_type in structs:
        return True
    if allow_string and element_type == "string":
        return True
    print(f"Error: Unknown element_type '{element_type}' in array field '{field_name}'")
    return False


def validate_fixed_array(field: dict, structs: dict) -> bool:
    """Validate a fixed_array field."""
    if "element_type" not in field or "max_size" not in field:
        print(
            f"Error: fixed_array field '{field['name']}' missing 'element_type' or 'max_size'"
        )
        return False

    element_type = field["element_type"]
    if not validate_array_element_type(element_type, field["name"], structs):
        return False

    if not isinstance(field["max_size"], int) or field["max_size"] <= 0:
        print(f"Error: Invalid max_size for fixed_array '{field['name']}'")
        return False

    return True


def validate_dynamic_array(field: dict, structs: dict) -> bool:
    """Validate a dynamic_array field."""
    if "element_type" not in field:
        print(f"Error: dynamic_array field '{field['name']}' missing 'element_type'")
        return False

    element_type = field["element_type"]
    return validate_array_element_type(element_type, field["name"], structs)


def validate_field(field: dict, structs: dict) -> bool:
    """Validate a single field definition."""
    if not isinstance(field, dict) or "name" not in field or "type" not in field:
        return False

    if not isinstance(field["name"], str) or not isinstance(field["type"], str):
        return False

    field_type = field["type"]

    if field_type in TYPE_MAP:
        return True
    if field_type == "string":
        return validate_string_field(field)
    if field_type == "fixed_array":
        return validate_fixed_array(field, structs)
    if field_type == "dynamic_array":
        return validate_dynamic_array(field, structs)

    print(f"Error: Unknown type '{field_type}' for field '{field['name']}'")
    return False


def is_valid_msg(msg: dict, list_id: list, structs: dict) -> bool:
    """Check if a packet definition is valid."""
    if "id" not in msg or not isinstance(msg["id"], int):
        return False

    if msg["id"] in list_id:
        return False

    if "fields" not in msg or not isinstance(msg["fields"], list):
        return False

    if "compressed" in msg and not isinstance(msg["compressed"], bool):
        return False

    return all(validate_field(field, structs) for field in msg["fields"])


def validate_protocol(protocol: dict) -> None:
    """Validate the entire protocol structure."""
    structs = protocol.get("structs", {})

    for struct_name, struct_data in structs.items():
        if "fields" not in struct_data or not isinstance(struct_data["fields"], list):
            print(f"Error: Struct '{struct_name}' missing 'fields'")
            sys.exit(1)

        if not all(validate_field(field, structs) for field in struct_data["fields"]):
            print(f"Error: Invalid field in struct '{struct_name}'")
            sys.exit(1)

    if "messages" not in protocol or not isinstance(protocol["messages"], dict):
        print("Error: No messages defined in protocol")
        sys.exit(1)

    list_id = []
    for msg_name, msg_data in protocol["messages"].items():
        if not is_valid_msg(msg_data, list_id, structs):
            print(f"Error: {msg_name} invalid")
            sys.exit(1)
        list_id.append(msg_data["id"])


def get_endianness(protocol: dict) -> str:
    """Extract and validate endianness from protocol."""
    if "endianness" not in protocol:
        print("Warning: 'endianness' not specified, defaulting to 'big'")
        return "big"

    endianness = protocol["endianness"].lower()
    if endianness not in ["big", "little"]:
        print(f"Error: Invalid endianness '{endianness}'. Must be 'big' or 'little'")
        sys.exit(1)

    return endianness


# Code Generation: Type-specific serialization/deserialization


def write_integer_bytes(field_name: str, num_bytes: int, endianness: str) -> str:
    """Generate unindented code to write an integer in specified endianness."""
    indices = range(num_bytes - 1, -1, -1) if endianness == "big" else range(num_bytes)
    return "".join(
        f"buffer.push_back(({field_name} >> {i * 8}) & 0xFF);\n" for i in indices
    )


def read_integer_bytes(
    field_name: str, num_bytes: int, c_type: str, endianness: str
) -> str:
    """Generate unindented code to read an integer in specified endianness."""
    indices = (
        list(range(num_bytes - 1, -1, -1))
        if endianness == "big"
        else list(range(num_bytes))
    )
    output = f"{field_name} = "
    for i, idx in enumerate(indices):
        if i > 0:
            output += " |\n    "
        output += f"(static_cast<{c_type}>(data[offset + {i}]) << {idx * 8})"
    output += f";\noffset += {num_bytes};\n"
    return output


def generate_type_serialize_code(
    var_name: str, field_type: str, endianness: str
) -> str:
    """Generate unindented serialization code for a primitive type."""
    if field_type not in TYPE_INFO:
        return ""

    num_bytes, _ = TYPE_INFO[field_type]

    if field_type in ("uint8", "int8"):
        return f"buffer.push_back({var_name});\n"

    if field_type in ("float", "double"):
        uint_type = "uint32_t" if field_type == "float" else "uint64_t"
        return (
            f"{{\n"
            f"    {uint_type} temp;\n"
            f"    std::memcpy(&temp, &{var_name}, sizeof({field_type}));\n"
            + indent(write_integer_bytes("temp", num_bytes, endianness), 1)
            + "}\n"
        )

    return write_integer_bytes(var_name, num_bytes, endianness)


def gen_deser_field(var_name: str, field_type: str, endianness: str) -> str:
    """Generate unindented deserialization code for a primitive type.

    Properly handles float/double via uint temp + memcpy to avoid UB.
    """
    if field_type not in TYPE_INFO:
        return ""

    num_bytes, c_type = TYPE_INFO[field_type]

    if field_type in ("uint8", "int8"):
        return f"{var_name} = actual_data[offset];\noffset += 1;\n"

    if field_type in ("float", "double"):
        uint_type = "uint32_t" if field_type == "float" else "uint64_t"
        inner = read_integer_bytes("temp", num_bytes, uint_type, endianness)
        return (
            f"{{\n"
            f"    {uint_type} temp;\n"
            + indent(inner.rstrip("\n"), 1)
            + "\n"
            + f"    std::memcpy(&{var_name}, &temp, sizeof({field_type}));\n"
            f"}}\n"
        )

    return read_integer_bytes(var_name, num_bytes, c_type, endianness)


def find_count_field(field_name: str, fields: list) -> Optional[str]:
    """Find the count field for a fixed_array by common naming patterns."""
    possible_names = [
        field_name.rstrip("s") + "_count",
        field_name[:-3] + "y_count" if field_name.endswith("ies") else None,
        field_name + "_count",
    ]

    for possible_name in possible_names:
        if possible_name is None:
            continue
        if any(f["name"] == possible_name for f in fields):
            return possible_name

    for f in fields:
        if (f["name"].endswith("_count") or f["name"].endswith("count")) and (
            f["name"].replace("_count", "") in field_name or field_name in f["name"]
        ):
            return f["name"]

    return None


# Header and Structure Generation


def generate_struct_definition(
    struct_name: str, struct_data: dict, structs: Optional[dict] = None
) -> str:
    """Generate a data structure definition."""
    structs = structs or {}
    output = f"struct {struct_name} {{\n"

    for field in struct_data["fields"]:
        field_name = field["name"]
        field_type = field["type"]

        if field_type == "string":
            output += f"    char {field_name}[{field['max_length']}];\n"
        elif field_type == "fixed_array":
            element_type = field["element_type"]
            max_size = field["max_size"]
            cpp_type = TYPE_MAP.get(
                element_type, element_type if element_type in structs else "uint8_t"
            )
            output += f"    {cpp_type} {field_name}[{max_size}];\n"
        else:
            output += f"    {TYPE_MAP[field_type]} {field_name};\n"

    output += "};\n\n"
    return output


def generate_struct_declaration(msg_name: str, msg_data: dict, structs: dict) -> str:
    """Generate a struct from a packet definition."""
    output = f"struct {msg_name} {{\n"
    output += f"    static constexpr uint32_t ID = {msg_data['id']};\n\n"

    for field in msg_data["fields"]:
        field_name = field["name"]
        field_type = field["type"]

        if field_type == "string":
            output += f"    char {field_name}[{field['max_length']}];\n"
        elif field_type == "fixed_array":
            element_type = field["element_type"]
            max_size = field["max_size"]

            if element_type == "string":
                if "element_max_length" not in field:
                    print("Error: fixed_array of strings needs 'element_max_length'")
                    sys.exit(1)
                output += f"    char {field_name}[{max_size}][{field['element_max_length']}];\n"
            else:
                cpp_type = TYPE_MAP.get(
                    element_type, element_type if element_type in structs else "uint8_t"
                )
                output += f"    {cpp_type} {field_name}[{max_size}];\n"
        elif field_type == "dynamic_array":
            element_type = field["element_type"]

            if element_type in TYPE_MAP:
                cpp_type = TYPE_MAP[element_type]
            elif element_type in structs:
                cpp_type = element_type
            elif element_type == "string":
                cpp_type = "std::string"
            else:
                cpp_type = "uint8_t"

            output += f"    std::vector<{cpp_type}> {field_name};\n"
        else:
            output += f"    {TYPE_MAP[field_type]} {field_name};\n"

    output += "\n"
    output += "    std::vector<uint8_t> serialize() const;\n"
    output += f"    static {msg_name} deserialize(const std::vector<uint8_t>& data);\n"
    output += "};\n\n"

    return output


def generate_header(protocol: dict, namespace: str = "ptc") -> str:
    """Generate the complete .hpp header file."""
    output = "#pragma once\n"
    output += "#include <cstdint>\n"
    output += "#include <vector>\n"
    output += "#include <cstring>\n"
    output += "#include <string>\n"

    needs_lz4 = any(
        msg.get("compressed", False) for msg in protocol["messages"].values()
    )
    if needs_lz4:
        output += "#include <lz4.h>\n"

    output += f"\nnamespace {namespace} {{\n\n"

    structs = protocol.get("structs", {})
    if structs:
        output += "// ===== Structs =====\n\n"
        for struct_name, struct_data in structs.items():
            output += generate_struct_definition(struct_name, struct_data, structs)

    output += "// ===== Messages =====\n\n"
    for msg_name, msg_data in protocol["messages"].items():
        output += generate_struct_declaration(msg_name, msg_data, structs)

    output += f"}}  // namespace {namespace}\n"
    return output


# Serialization Code Generation


def serialize_field_code(
    var_name: str,
    field_type: str,
    endianness: str,
    max_length: Optional[int] = None,
) -> str:
    """Generate unindented serialization code for a single field."""
    if field_type in TYPE_INFO:
        return generate_type_serialize_code(var_name, field_type, endianness)

    if field_type == "string":
        return (
            f"for (uint32_t i = 0; i < {max_length}; ++i) {{\n"
            f"    buffer.push_back({var_name}[i]);\n"
            f"}}\n"
        )

    return ""


def generate_serialize_impl(
    msg_name: str,
    fields: list,
    endianness: str,
    structs: dict,
    compressed: bool = False,
) -> str:
    """Generate the serialize method implementation."""
    output = f"std::vector<uint8_t> {msg_name}::serialize() const {{\n"

    if compressed:
        output += "    std::vector<uint8_t> uncompressed_buffer;\n"
        output += "    std::vector<uint8_t>& buffer = uncompressed_buffer;\n\n"
    else:
        output += "    std::vector<uint8_t> buffer;\n\n"

    output += "    // Write message ID\n"
    output += indent(write_integer_bytes("ID", 1, endianness), 1)
    output += "\n"

    for field in fields:
        field_name = field["name"]
        field_type = field["type"]

        output += f"    // Write {field_name}\n"

        if field_type == "fixed_array":
            element_type = field["element_type"]
            max_size = field["max_size"]

            count_field = find_count_field(field_name, fields)
            if count_field is None:
                print(f"Error: Cannot find count field for fixed_array '{field_name}'")
                sys.exit(1)

            output += f"    for (uint32_t i = 0; i < {count_field} && i < {max_size}; ++i) {{\n"

            if element_type in structs:
                struct_def = structs[element_type]
                for struct_field in struct_def["fields"]:
                    sf_name = struct_field["name"]
                    sf_type = struct_field["type"]
                    sf_max_length = struct_field.get("max_length")
                    output += indent(
                        serialize_field_code(
                            f"{field_name}[i].{sf_name}",
                            sf_type,
                            endianness,
                            sf_max_length,
                        ),
                        2,
                    )
            else:
                output += indent(
                    serialize_field_code(f"{field_name}[i]", element_type, endianness),
                    2,
                )

            output += "    }\n"

        elif field_type == "dynamic_array":
            element_type = field["element_type"]

            output += "    {\n"
            output += (
                f"        uint32_t size = static_cast<uint32_t>({field_name}.size());\n"
            )
            output += indent(write_integer_bytes("size", 4, endianness), 2)
            output += "    }\n"
            output += f"    for (const auto& elem : {field_name}) {{\n"

            if element_type in structs:
                struct_def = structs[element_type]
                for struct_field in struct_def["fields"]:
                    sf_name = struct_field["name"]
                    sf_type = struct_field["type"]
                    sf_max_length = struct_field.get("max_length")
                    output += indent(
                        serialize_field_code(
                            f"elem.{sf_name}", sf_type, endianness, sf_max_length
                        ),
                        2,
                    )
            else:
                if element_type == "string":
                    # Dynamic string: write length then content
                    output += "        {\n"
                    output += "            uint32_t str_len = static_cast<uint32_t>(elem.size());\n"
                    output += indent(write_integer_bytes("str_len", 4, endianness), 3)
                    output += "            for (char c : elem) {\n"
                    output += "                buffer.push_back(c);\n"
                    output += "            }\n"
                    output += "        }\n"
                else:
                    output += (
                        serialize_field_code("elem", element_type, endianness, True)
                        + "\n"
                    )

            output += "    }\n"

        elif field_type == "string":
            max_len = field["max_length"]
            output += f"    for (uint32_t i = 0; i < {max_len}; ++i) {{\n"
            output += f"        buffer.push_back({field_name}[i]);\n"
            output += "    }\n"

        else:
            output += indent(
                serialize_field_code(field_name, field_type, endianness), 1
            )

        output += "\n"

    if compressed:
        output += "    // Compress the buffer using LZ4\n"
        output += "    std::vector<uint8_t> compressed_buffer;\n"
        output += (
            "    int max_compressed_size = "
            "LZ4_compressBound(static_cast<int>(uncompressed_buffer.size()));\n"
        )
        output += "    compressed_buffer.resize(max_compressed_size + 4);\n\n"

        output += (
            "    uint32_t uncompressed_size = "
            "static_cast<uint32_t>(uncompressed_buffer.size());\n"
        )
        output += "    std::vector<uint8_t> size_bytes;\n"
        output += indent(
            write_integer_bytes("uncompressed_size", 4, endianness).replace(
                "buffer.push_back", "size_bytes.push_back"
            ),
            1,
        )
        output += "    std::memcpy(compressed_buffer.data(), size_bytes.data(), 4);\n\n"

        output += "    int compressed_size = LZ4_compress_default(\n"
        output += "        reinterpret_cast<const char*>(uncompressed_buffer.data()),\n"
        output += "        reinterpret_cast<char*>(compressed_buffer.data() + 4),\n"
        output += "        static_cast<int>(uncompressed_buffer.size()),\n"
        output += "        max_compressed_size\n"
        output += "    );\n\n"

        output += "    if (compressed_size <= 0) {\n"
        output += "        compressed_buffer.resize(4 + uncompressed_buffer.size());\n"
        output += (
            "        std::memcpy(compressed_buffer.data() + 4, "
            "uncompressed_buffer.data(), uncompressed_buffer.size());\n"
        )
        output += "    } else {\n"
        output += "        compressed_buffer.resize(4 + compressed_size);\n"
        output += "    }\n\n"
        output += "    return compressed_buffer;\n"
    else:
        output += "    return buffer;\n"

    output += "}\n\n"
    return output


# Deserialization Code Generation


def generate_deserialize_impl(
    msg_name: str,
    fields: list,
    endianness: str,
    structs: dict,
    compressed: bool = False,
) -> str:
    """Generate the deserialize method implementation."""
    output = (
        f"{msg_name} {msg_name}::deserialize(const std::vector<uint8_t>& data) {{\n"
    )
    output += f"    {msg_name} msg = {{}};\n"

    if compressed:
        output += "    std::vector<uint8_t> decompressed_data;\n\n"
        output += "    uint32_t uncompressed_size = 0;\n"
        output += "    size_t temp_offset = 0;\n"
        temp_read = read_integer_bytes(
            "uncompressed_size", 4, "uint32_t", endianness
        ).replace("offset", "temp_offset")
        output += indent(temp_read, 1)
        output += "\n"

        output += "    decompressed_data.resize(uncompressed_size);\n"
        output += "    int decompressed_size = LZ4_decompress_safe(\n"
        output += "        reinterpret_cast<const char*>(data.data() + 4),\n"
        output += "        reinterpret_cast<char*>(decompressed_data.data()),\n"
        output += "        static_cast<int>(data.size() - 4),\n"
        output += "        static_cast<int>(uncompressed_size)\n"
        output += "    );\n\n"

        output += "    if (decompressed_size < 0) {\n"
        output += "        decompressed_data.assign(data.begin() + 4, data.end());\n"
        output += "    }\n\n"

        output += "    const std::vector<uint8_t>& actual_data = decompressed_data;\n"
    else:
        output += "    const std::vector<uint8_t>& actual_data = data;\n"

    output += "    size_t offset = 1;\n\n"

    for field in fields:
        field_name = field["name"]
        field_type = field["type"]

        output += f"    // Read {field_name}\n"

        if field_type == "fixed_array":
            element_type = field["element_type"]
            max_size = field["max_size"]

            count_field = find_count_field(field_name, fields)
            if count_field is None:
                print(f"Error: Cannot find count field for fixed_array '{field_name}'")
                sys.exit(1)

            output += f"    for (uint32_t i = 0; i < msg.{count_field} && i < {max_size}; ++i) {{\n"

            if element_type in structs:
                struct_def = structs[element_type]
                for struct_field in struct_def["fields"]:
                    sf_name = struct_field["name"]
                    sf_type = struct_field["type"]
                    if sf_type in TYPE_INFO:
                        output += indent(
                            gen_deser_field(
                                f"msg.{field_name}[i].{sf_name}", sf_type, endianness
                            ),
                            2,
                        )
                    elif sf_type == "string":
                        max_len = struct_field["max_length"]
                        output += (
                            f"        std::memcpy(msg.{field_name}[i].{sf_name}, "
                            f"actual_data.data() + offset, {max_len});\n"
                        )
                        output += f"        offset += {max_len};\n"
            else:
                if element_type in TYPE_INFO:
                    output += indent(
                        gen_deser_field(
                            f"msg.{field_name}[i]", element_type, endianness
                        ),
                        2,
                    )

            output += "    }\n"

        elif field_type == "dynamic_array":
            element_type = field["element_type"]

            output += "    {\n"
            output += "        uint32_t size;\n"
            temp_read = read_integer_bytes("size", 4, "uint32_t", endianness)
            output += indent(temp_read, 2)
            output += f"        msg.{field_name}.resize(size);\n"
            output += "    }\n"

            output += f"    for (auto& elem : msg.{field_name}) {{\n"

            if element_type in structs:
                struct_def = structs[element_type]
                for struct_field in struct_def["fields"]:
                    sf_name = struct_field["name"]
                    sf_type = struct_field["type"]

                    if sf_type in TYPE_INFO:
                        output += indent(
                            gen_deser_field(f"elem.{sf_name}", sf_type, endianness),
                            2,
                        )
                    elif sf_type == "string":
                        max_len = struct_field["max_length"]
                        output += (
                            f"        std::memcpy(elem.{sf_name}, "
                            f"actual_data.data() + offset, {max_len});\n"
                        )
                        output += f"        offset += {max_len};\n"
            else:
                if element_type in TYPE_INFO:
                    output += indent(
                        gen_deser_field("elem", element_type, endianness), 2
                    )
                elif element_type == "string":
                    output += "    {\n"
                    output += "        uint32_t str_len;\n"
                    temp_read = read_integer_bytes("str_len", 4, "uint32_t", endianness)
                    output += indent(temp_read, 3)
                    output += "            elem.resize(str_len);\n"
                    output += "            for (uint32_t j = 0; j < str_len; ++j) {\n"
                    output += "                elem[j] = actual_data[offset];\n"
                    output += "                offset += 1;\n"
                    output += "            }\n"
                    output += "        }\n"

            output += "    }\n"

        elif field_type == "string":
            max_len = field["max_length"]
            output += (
                f"    std::memcpy(msg.{field_name}, "
                f"actual_data.data() + offset, {max_len});\n"
            )
            output += f"    offset += {max_len};\n"

        elif field_type in TYPE_INFO:
            output += indent(
                gen_deser_field(f"msg.{field_name}", field_type, endianness)
            )

        output += "\n"

    output += "    return msg;\n"
    output += "}\n\n"
    return output


def generate_source(protocol: dict, endianness: str, namespace: str = "ptc") -> str:
    """Generate the complete .cpp source file."""
    output = '#include "generated_messages.hpp"\n\n'
    output += f"namespace {namespace} {{\n\n"

    structs = protocol.get("structs", {})

    for msg_name, msg_data in protocol["messages"].items():
        compressed = msg_data.get("compressed", False)
        output += generate_serialize_impl(
            msg_name, msg_data["fields"], endianness, structs, compressed
        )
        output += generate_deserialize_impl(
            msg_name, msg_data["fields"], endianness, structs, compressed
        )

    output += f"}}  // namespace {namespace}\n"
    return output


def write_file(filepath: str, content: str) -> None:
    """Write content to a file."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def parse_args() -> tuple[str, str]:
    """Parse command-line arguments. Returns (json_path, namespace)."""
    args = sys.argv[1:]
    namespace = "ptc"
    json_path = None

    i = 0
    while i < len(args):
        if args[i] == "-n":
            if i + 1 >= len(args):
                print("Error: -n requires a namespace name")
                sys.exit(1)
            namespace = args[i + 1]
            i += 2
        else:
            if json_path is not None:
                print("Error: unexpected argument '" + args[i] + "'")
                sys.exit(1)
            json_path = args[i]
            i += 1

    if json_path is None:
        print("Usage: ./generate_protocol.py [-n <namespace>] path_to.json")
        sys.exit(1)

    return json_path, namespace


def main() -> None:
    """Main entry point."""
    json_path, namespace = parse_args()

    protocol = load_protocol(json_path)
    validate_protocol(protocol)
    endianness = get_endianness(protocol)

    header = generate_header(protocol, namespace)
    write_file("generated_messages.hpp", header)

    source = generate_source(protocol, endianness, namespace)
    write_file("generated_messages.cpp", source)


if __name__ == "__main__":
    main()
