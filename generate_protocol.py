#!/usr/bin/env python3
import json
import sys
from pathlib import Path

TYPE_MAP = {
    "uint8": "uint8_t",
    "uint16": "uint16_t",
    "uint32": "uint32_t",
    "uint64": "uint64_t",
    "int8": "int8_t",
    "int16": "int16_t",
    "int32": "int32_t",
    "int64": "int64_t",
    "float": "float",
    "double": "double",
}


def load_protocol(json_path: str) -> dict:
    """Open the file and validate if the json is well written"""
    try:
        file = open(json_path)
        content = file.read()
        return json.loads(content)
    except ValueError as e:
        print("invalid file: %s" % e)
        sys.exit(1)


def is_valid_msg(msg: dict, list_id: list, structs: dict) -> bool:
    """Check if a packet definition is valid"""
    if "id" not in msg or not isinstance(msg["id"], int):
        return False

    if msg["id"] in list_id:
        return False

    if "fields" not in msg or not isinstance(msg["fields"], list):
        return False

    if "compressed" in msg and not isinstance(msg["compressed"], bool):
        return False

    for field in msg["fields"]:
        if "name" not in field or not isinstance(field["name"], str):
            return False

        if "type" not in field or not isinstance(field["type"], str):
            return False

        field_type = field["type"]

        if field_type in TYPE_MAP:
            continue

        if field_type == "string":
            if (
                "max_length" not in field
                or not isinstance(field["max_length"], int)
                or field["max_length"] <= 0
            ):
                return False
            continue

        if field_type == "fixed_array":
            if "element_type" not in field or "max_size" not in field:
                print(
                    f"Error: fixed_array field '{field['name']}' missing 'element_type' or 'max_size'"
                )
                return False

            element_type = field["element_type"]

            if (
                element_type not in TYPE_MAP
                and element_type not in structs
                and element_type != "string"
            ):
                print(
                    f"Error: Unknown element_type '{element_type}' in fixed_array '{field['name']}'"
                )
                return False

            if not isinstance(field["max_size"], int) or field["max_size"] <= 0:
                print(f"Error: Invalid max_size for fixed_array '{field['name']}'")
                return False

            continue

        if field_type == "dynamic_array":
            if "element_type" not in field:
                print(
                    f"Error: dynamic_array field '{field['name']}' missing 'element_type'"
                )
                return False

            element_type = field["element_type"]

            if (
                element_type not in TYPE_MAP
                and element_type not in structs
                and element_type != "string"
            ):
                print(
                    f"Error: Unknown element_type '{element_type}' in dynamic_array '{field['name']}'"
                )
                return False

            continue

        print(f"Error: Unknown type '{field_type}' for field '{field['name']}'")
        return False

    return True


def validate_protocol(protocol: dict):
    """Check if the whole protocol is valid"""
    if not validate_structs(protocol):
        sys.exit(1)

    messages = protocol["messages"]
    if messages is None:
        print("Error: File doesn't contain 'messages' field")
        sys.exit(1)

    list_id = []
    structs = protocol.get("structs", {})

    for msg_name, msg_data in messages.items():
        if not is_valid_msg(msg_data, list_id, structs):
            print(f"Error: {msg_name} invalid")
            sys.exit(1)
        list_id.append(msg_data["id"])


def validate_structs(protocol: dict) -> bool:
    """Check if all structs are well defined"""
    if "structs" not in protocol:
        return True

    structs = protocol["structs"]

    for struct_name, struct_data in structs.items():
        if "fields" not in struct_data:
            print(f"Error: Struct '{struct_name}' missing 'fields'")
            return False

        for field in struct_data["fields"]:
            if "name" not in field or "type" not in field:
                print(f"Error: Invalid field in struct '{struct_name}'")
                return False

            field_type = field["type"]

            if field_type == "fixed_array":
                if "element_type" not in field:
                    print(
                        f"Error: fixed_array missing 'element_type' in struct '{struct_name}'"
                    )
                    return False
                if (
                    "max_size" not in field
                    or not isinstance(field["max_size"], int)
                    or field["max_size"] <= 0
                ):
                    print(
                        f"Error: fixed_array missing or invalid 'max_size' in struct '{struct_name}'"
                    )
                    return False
                element_type = field["element_type"]
                if (
                    element_type not in TYPE_MAP
                    and element_type != "string"
                    and element_type not in structs
                ):
                    print(
                        f"Error: Unknown element_type '{element_type}' for fixed_array in struct '{struct_name}'"
                    )
                    return False
            elif field_type not in TYPE_MAP and field_type != "string":
                print(f"Error: Unknown type '{field_type}' in struct '{struct_name}'")
                return False

            if field_type == "string":
                if (
                    "max_length" not in field
                    or not isinstance(field["max_length"], int)
                    or field["max_length"] <= 0
                ):
                    print(
                        f"Error: Invalid max_length for string in struct '{struct_name}'"
                    )
                    return False

    return True


def get_endianness(protocol: dict) -> str:
    """Extract and validate endianness from protocol"""
    if "endianness" not in protocol:
        print("Warning: 'endianness' not specified, defaulting to 'big'")
        return "big"

    endianness = protocol["endianness"].lower()
    if endianness not in ["big", "little"]:
        print(f"Error: Invalid endianness '{endianness}'. Must be 'big' or 'little'")
        sys.exit(1)

    return endianness


def generate_struct_definition(
    struct_name: str, struct_data: dict, structs: dict = {}
) -> str:
    """Generate a data structure, not a structure of a packet"""
    output = ""

    output += f"struct {struct_name} {{\n"

    for field in struct_data["fields"]:
        field_name = field["name"]
        field_type = field["type"]

        if field_type == "string":
            output += f"    char {field_name}[{field['max_length']}];\n"
        elif field_type == "fixed_array":
            element_type = field["element_type"]
            max_size = field["max_size"]

            if element_type in TYPE_MAP:
                cpp_type = TYPE_MAP[element_type]
            elif element_type in structs:
                cpp_type = element_type
            else:
                cpp_type = "uint8_t"  # Fallback

            output += f"    {cpp_type} {field_name}[{max_size}];\n"
        else:
            output += f"    {TYPE_MAP[field_type]} {field_name};\n"

    output += "};\n\n"

    return output


def generate_struct_declaration(msg_name: str, msg_data: dict, structs: dict) -> str:
    """Generate a struct from a packet definition"""
    output = ""

    output += f"struct {msg_name} {{\n"
    output += f"    static constexpr uint32_t ID = {msg_data['id']};\n\n"

    for field in msg_data["fields"]:
        field_name = field["name"]
        field_type = field["type"]

        if field_type == "string":
            output += f"    char {field_name}[{field['max_length']}];\n"

        elif field_type == "fixed_array":
            element_type = field["element_type"]
            max_size = field["max_size"]

            if element_type in TYPE_MAP:
                cpp_type = TYPE_MAP[element_type]
            elif element_type in structs:
                cpp_type = element_type
            elif element_type == "string":
                if "element_max_length" in field:
                    output += f"    char {field_name}[{max_size}][{field['element_max_length']}];\n"
                    continue
                else:
                    print("Error: fixed_array of strings needs 'element_max_length'")
                    sys.exit(1)
            else:
                cpp_type = "uint8_t"  # Fallback

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
                cpp_type = "uint8_t"  # Fallback

            output += f"    std::vector<{cpp_type}> {field_name};\n"

        else:
            output += f"    {TYPE_MAP[field_type]} {field_name};\n"

    output += "\n"
    output += "    std::vector<uint8_t> serialize() const;\n"
    output += f"    static {msg_name} deserialize(const std::vector<uint8_t>& data);\n"
    output += "};\n\n"

    return output


def generate_header(protocol: dict) -> str:
    """Generate a file with all structs definition"""
    output = ""
    output += "#pragma once\n"
    output += "#include <cstdint>\n"
    output += "#include <vector>\n"
    output += "#include <cstring>\n\n"
    output += "#include <string>\n"

    needs_lz4 = False
    for msg_name, msg_data in protocol["messages"].items():
        if msg_data.get("compressed", False):
            needs_lz4 = True
            break

    if needs_lz4:
        output += "#include <lz4.h>\n"

    output += "\n"
    output += "namespace net {\n\n"

    if "structs" in protocol:
        output += "// ===== Structs =====\n\n"
        for struct_name, struct_data in protocol["structs"].items():
            output += generate_struct_definition(
                struct_name, struct_data, protocol["structs"]
            )

    output += "// ===== Messages =====\n\n"
    structs = protocol.get("structs", {})
    for msg_name, msg_data in protocol["messages"].items():
        output += generate_struct_declaration(msg_name, msg_data, structs)

    output += "}  // namespace net\n"

    return output


def write_uint_bytes(field_name: str, num_bytes: int, endianness: str) -> str:
    """Generate code to write unsigned integer in specified endianness"""
    output = ""

    if endianness == "big":
        for i in range(num_bytes - 1, -1, -1):
            output += f"    buffer.push_back(({field_name} >> {i * 8}) & 0xFF);\n"
    else:
        for i in range(num_bytes):
            output += f"    buffer.push_back(({field_name} >> {i * 8}) & 0xFF);\n"

    return output


def read_uint_bytes(
    field_name: str, num_bytes: int, type_name: str, endianness: str
) -> str:
    """Generate code to read unsigned integer in specified endianness"""
    output = ""
    if endianness == "big":
        output += f"    msg.{field_name} = "
        for i in range(num_bytes):
            if i > 0:
                output += " |\n        "
            shift = (num_bytes - 1 - i) * 8
            output += f"(static_cast<{type_name}>(data[offset + {i}]) << {shift})"
        output += ";\n"
    else:
        output += f"    msg.{field_name} = "
        for i in range(num_bytes):
            if i > 0:
                output += " |\n        "
            shift = i * 8
            output += f"(static_cast<{type_name}>(data[offset + {i}]) << {shift})"
        output += ";\n"

    output += f"    offset += {num_bytes};\n"
    return output


def generate_serialize_impl(
    msg_name: str,
    fields: list,
    endianness: str,
    structs: dict,
    compressed: bool = False,
) -> str:
    """Generate the serialize method of a struct"""
    output = ""
    output += f"std::vector<uint8_t> {msg_name}::serialize() const {{\n"

    if compressed:
        output += "    std::vector<uint8_t> uncompressed_buffer;\n"
        output += "    std::vector<uint8_t>& buffer = uncompressed_buffer;\n\n"
    else:
        output += "    std::vector<uint8_t> buffer;\n\n"

    output += "    // Write message ID\n"
    output += write_uint_bytes("ID", 1, endianness)
    output += "\n"

    for field in fields:
        field_name = field["name"]
        field_type = field["type"]

        output += f"    // Write {field_name}\n"

        if field_type == "fixed_array":
            element_type = field["element_type"]
            max_size = field["max_size"]

            count_field = None

            possible_names = [
                field_name.rstrip("s") + "_count",
                field_name[:-3] + "y_count" if field_name.endswith("ies") else None,
                field_name + "_count",
            ]

            for possible_name in possible_names:
                if possible_name is None:
                    continue
                for f in fields:
                    if f["name"] == possible_name:
                        count_field = possible_name
                        break
                if count_field:
                    break

            if count_field is None:
                for f in fields:
                    if f["name"].endswith("_count") or f["name"].endswith("count"):
                        if (
                            f["name"].replace("_count", "") in field_name
                            or field_name in f["name"]
                        ):
                            count_field = f["name"]
                            break

            if count_field is None:
                print(f"Error: Cannot find count field for fixed_array '{field_name}'")
                print(
                    f"Expected one of: {[n for n in possible_names if n is not None]}"
                )
                sys.exit(1)

            output += f"    for (uint32_t i = 0; i < {count_field} && i < {max_size}; ++i) {{\n"

            if element_type in structs:
                struct_data = structs[element_type]
                for struct_field in struct_data["fields"]:
                    sf_name = struct_field["name"]
                    sf_type = struct_field["type"]

                    if sf_type in ["uint8", "int8"]:
                        output += (
                            f"        buffer.push_back({field_name}[i].{sf_name});\n"
                        )

                    elif sf_type in ["uint16", "int16"]:
                        temp = write_uint_bytes(
                            f"{field_name}[i].{sf_name}", 2, endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ")

                    elif sf_type in ["uint32", "int32"]:
                        temp = write_uint_bytes(
                            f"{field_name}[i].{sf_name}", 4, endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ")

                    elif sf_type in ["uint64", "int64"]:
                        temp = write_uint_bytes(
                            f"{field_name}[i].{sf_name}", 8, endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ")

                    elif sf_type == "float":
                        output += "        {\n"
                        output += "            uint32_t temp;\n"
                        output += f"            std::memcpy(&temp, &{field_name}[i].{sf_name}, sizeof(float));\n"
                        temp_write = write_uint_bytes("temp", 4, endianness)
                        output += "        " + temp_write.replace("\n", "\n        ")
                        output += "        }\n"

                    elif sf_type == "double":
                        output += "        {\n"
                        output += "            uint64_t temp;\n"
                        output += f"            std::memcpy(&temp, &{field_name}[i].{sf_name}, sizeof(double));\n"
                        temp_write = write_uint_bytes("temp", 8, endianness)
                        output += "        " + temp_write.replace("\n", "\n        ")
                        output += "        }\n"

                    elif sf_type == "string":
                        max_len = struct_field["max_length"]
                        output += (
                            f"        for (uint32_t j = 0; j < {max_len}; ++j) {{\n"
                        )
                        output += f"            buffer.push_back({field_name}[i].{sf_name}[j]);\n"
                        output += "        }\n"

            elif element_type in TYPE_MAP:
                if element_type in ["uint8", "int8"]:
                    output += f"        buffer.push_back({field_name}[i]);\n"

                elif element_type in ["uint16", "int16"]:
                    temp = write_uint_bytes(f"{field_name}[i]", 2, endianness)
                    output += "    " + temp.replace("\n", "\n    ")

                elif element_type in ["uint32", "int32"]:
                    temp = write_uint_bytes(f"{field_name}[i]", 4, endianness)
                    output += "    " + temp.replace("\n", "\n    ")

                elif element_type in ["uint64", "int64"]:
                    temp = write_uint_bytes(f"{field_name}[i]", 8, endianness)
                    output += "    " + temp.replace("\n", "\n    ")

                elif element_type == "float":
                    output += "        {\n"
                    output += "            uint32_t temp;\n"
                    output += f"            std::memcpy(&temp, &{field_name}[i], sizeof(float));\n"
                    temp_write = write_uint_bytes("temp", 4, endianness)
                    output += "        " + temp_write.replace("\n", "\n        ")
                    output += "        }\n"

                elif element_type == "double":
                    output += "        {\n"
                    output += "            uint64_t temp;\n"
                    output += f"            std::memcpy(&temp, &{field_name}[i], sizeof(double));\n"
                    temp_write = write_uint_bytes("temp", 8, endianness)
                    output += "        " + temp_write.replace("\n", "\n        ")
                    output += "        }\n"

            output += "    }\n"

        elif field_type == "dynamic_array":
            element_type = field["element_type"]

            output += "    {\n"
            output += (
                f"        uint32_t size = static_cast<uint32_t>({field_name}.size());\n"
            )
            temp_size = write_uint_bytes("size", 4, endianness)
            output += "    " + temp_size.replace("\n", "\n    ")
            output += "    }\n"

            output += f"    for (const auto& elem : {field_name}) {{\n"

            if element_type in structs:
                struct_data = structs[element_type]
                for struct_field in struct_data["fields"]:
                    sf_name = struct_field["name"]
                    sf_type = struct_field["type"]

                    if sf_type in ["uint8", "int8"]:
                        output += f"        buffer.push_back(elem.{sf_name});\n"

                    elif sf_type in ["uint16", "int16"]:
                        temp = write_uint_bytes(f"elem.{sf_name}", 2, endianness)
                        output += "    " + temp.replace("\n", "\n    ")

                    elif sf_type in ["uint32", "int32"]:
                        temp = write_uint_bytes(f"elem.{sf_name}", 4, endianness)
                        output += "    " + temp.replace("\n", "\n    ")

                    elif sf_type in ["uint64", "int64"]:
                        temp = write_uint_bytes(f"elem.{sf_name}", 8, endianness)
                        output += "    " + temp.replace("\n", "\n    ")

                    elif sf_type == "float":
                        output += "        {\n"
                        output += "            uint32_t temp;\n"
                        output += f"            std::memcpy(&temp, &elem.{sf_name}, sizeof(float));\n"
                        temp_write = write_uint_bytes("temp", 4, endianness)
                        output += "        " + temp_write.replace("\n", "\n        ")
                        output += "        }\n"

                    elif sf_type == "double":
                        output += "        {\n"
                        output += "            uint64_t temp;\n"
                        output += f"            std::memcpy(&temp, &elem.{sf_name}, sizeof(double));\n"
                        temp_write = write_uint_bytes("temp", 8, endianness)
                        output += "        " + temp_write.replace("\n", "\n        ")
                        output += "        }\n"

                    elif sf_type == "string":
                        max_len = struct_field["max_length"]
                        output += (
                            f"        for (uint32_t j = 0; j < {max_len}; ++j) {{\n"
                        )
                        output += f"            buffer.push_back(elem.{sf_name}[j]);\n"
                        output += "        }\n"

            elif element_type in TYPE_MAP:
                if element_type in ["uint8", "int8"]:
                    output += "        buffer.push_back(elem);\n"

                elif element_type in ["uint16", "int16"]:
                    temp = write_uint_bytes("elem", 2, endianness)
                    output += "    " + temp.replace("\n", "\n    ")

                elif element_type in ["uint32", "int32"]:
                    temp = write_uint_bytes("elem", 4, endianness)
                    output += "    " + temp.replace("\n", "\n    ")

                elif element_type in ["uint64", "int64"]:
                    temp = write_uint_bytes("elem", 8, endianness)
                    output += "    " + temp.replace("\n", "\n    ")

                elif element_type == "float":
                    output += "        {\n"
                    output += "            uint32_t temp;\n"
                    output += "            std::memcpy(&temp, &elem, sizeof(float));\n"
                    temp_write = write_uint_bytes("temp", 4, endianness)
                    output += "        " + temp_write.replace("\n", "\n        ")
                    output += "        }\n"

                elif element_type == "double":
                    output += "        {\n"
                    output += "            uint64_t temp;\n"
                    output += "            std::memcpy(&temp, &elem, sizeof(double));\n"
                    temp_write = write_uint_bytes("temp", 8, endianness)
                    output += "        " + temp_write.replace("\n", "\n        ")
                    output += "        }\n"

            elif element_type == "string":
                output += "        {\n"
                output += "            uint32_t str_len = static_cast<uint32_t>(elem.size());\n"
                temp_len = write_uint_bytes("str_len", 4, endianness)
                output += "        " + temp_len.replace("\n", "\n        ")
                output += "            for (char c : elem) {\n"
                output += "                buffer.push_back(c);\n"
                output += "            }\n"
                output += "        }\n"

            output += "    }\n"

        elif field_type == "string":
            max_len = field["max_length"]
            output += f"    for (uint32_t i = 0; i < {max_len}; ++i) {{\n"
            output += f"        buffer.push_back({field_name}[i]);\n"
            output += "    }\n"

        elif field_type in ["uint8", "int8"]:
            output += f"    buffer.push_back({field_name});\n"

        elif field_type in ["uint16", "int16"]:
            output += write_uint_bytes(field_name, 2, endianness)

        elif field_type in ["uint32", "int32"]:
            output += write_uint_bytes(field_name, 4, endianness)

        elif field_type in ["uint64", "int64"]:
            output += write_uint_bytes(field_name, 8, endianness)

        elif field_type == "float":
            output += "    {\n"
            output += "        uint32_t temp;\n"
            output += f"        std::memcpy(&temp, &{field_name}, sizeof(float));\n"
            output += write_uint_bytes("temp", 4, endianness).replace(
                "    ", "        "
            )
            output += "    }\n"

        elif field_type == "double":
            output += "    {\n"
            output += "        uint64_t temp;\n"
            output += f"        std::memcpy(&temp, &{field_name}, sizeof(double));\n"
            output += write_uint_bytes("temp", 8, endianness).replace(
                "    ", "        "
            )
            output += "    }\n"

        output += "\n"

    if compressed:
        output += "    // Compress the buffer using LZ4\n"
        output += "    std::vector<uint8_t> compressed_buffer;\n"
        output += "    int max_compressed_size = LZ4_compressBound(static_cast<int>(uncompressed_buffer.size()));\n"
        output += "    compressed_buffer.resize(max_compressed_size + 4); // +4 for uncompressed size\n\n"

        output += "    // Write uncompressed size at the beginning\n"
        output += "    uint32_t uncompressed_size = static_cast<uint32_t>(uncompressed_buffer.size());\n"
        temp_size = write_uint_bytes("uncompressed_size", 4, endianness)
        output += "    std::vector<uint8_t> size_bytes;\n"
        output += temp_size.replace("buffer.push_back", "size_bytes.push_back")
        output += "    std::memcpy(compressed_buffer.data(), size_bytes.data(), 4);\n\n"

        output += "    // Compress the data\n"
        output += "    int compressed_size = LZ4_compress_default(\n"
        output += "        reinterpret_cast<const char*>(uncompressed_buffer.data()),\n"
        output += "        reinterpret_cast<char*>(compressed_buffer.data() + 4),\n"
        output += "        static_cast<int>(uncompressed_buffer.size()),\n"
        output += "        max_compressed_size\n"
        output += "    );\n\n"

        output += "    if (compressed_size <= 0) {\n"
        output += (
            "        // Compression failed, return uncompressed data with size prefix\n"
        )
        output += "        compressed_buffer.resize(4 + uncompressed_buffer.size());\n"
        output += "        std::memcpy(compressed_buffer.data() + 4, uncompressed_buffer.data(), uncompressed_buffer.size());\n"
        output += "    } else {\n"
        output += "        compressed_buffer.resize(4 + compressed_size);\n"
        output += "    }\n\n"

        output += "    return compressed_buffer;\n"
    else:
        output += "    return buffer;\n"

    output += "}\n\n"
    return output


def generate_deserialize_impl(
    msg_name: str,
    fields: list,
    endianness: str,
    structs: dict,
    compressed: bool = False,
) -> str:
    """Generate the deserialize method of a struct"""
    output = ""

    output += (
        f"{msg_name} {msg_name}::deserialize(const std::vector<uint8_t>& data) {{\n"
    )
    output += f"    {msg_name} msg;\n"

    if compressed:
        output += "    std::vector<uint8_t> decompressed_data;\n\n"
        output += "    // Read uncompressed size\n"
        output += "    uint32_t uncompressed_size = 0;\n"
        output += "    size_t temp_offset = 0;\n"
        temp_read = (
            read_uint_bytes("uncompressed_size", 4, "uint32_t", endianness)
            .replace("msg.", "")
            .replace("offset", "temp_offset")
        )
        output += "    " + temp_read.replace("\n", "\n    ")
        output += "\n"

        output += "    // Decompress the data\n"
        output += "    decompressed_data.resize(uncompressed_size);\n"
        output += "    int decompressed_size = LZ4_decompress_safe(\n"
        output += "        reinterpret_cast<const char*>(data.data() + 4),\n"
        output += "        reinterpret_cast<char*>(decompressed_data.data()),\n"
        output += "        static_cast<int>(data.size() - 4),\n"
        output += "        static_cast<int>(uncompressed_size)\n"
        output += "    );\n\n"

        output += "    if (decompressed_size < 0) {\n"
        output += "        // Decompression failed, assume data is uncompressed\n"
        output += "        decompressed_data.assign(data.begin() + 4, data.end());\n"
        output += "    }\n\n"

        output += "    const std::vector<uint8_t>& actual_data = decompressed_data;\n"
        output += "    size_t offset = 0;\n\n"

        output += "    // Skip message ID\n"
        output += "    offset += 1;\n\n"
    else:
        output += "    const std::vector<uint8_t>& actual_data = data;\n"
        output += "    size_t offset = 0;\n\n"

        output += "    // Skip message ID\n"
        output += "    offset += 1;\n\n"

    for field in fields:
        field_name = field["name"]
        field_type = field["type"]

        output += f"    // Read {field_name}\n"

        data_var = "actual_data" if compressed else "data"

        if field_type == "fixed_array":
            element_type = field["element_type"]
            max_size = field["max_size"]

            count_field = None

            possible_names = [
                field_name.rstrip("s") + "_count",
                field_name[:-3] + "y_count" if field_name.endswith("ies") else None,
                field_name + "_count",
            ]

            for possible_name in possible_names:
                if possible_name is None:
                    continue
                for f in fields:
                    if f["name"] == possible_name:
                        count_field = possible_name
                        break
                if count_field:
                    break

            if count_field is None:
                for f in fields:
                    if f["name"].endswith("_count") or f["name"].endswith("count"):
                        if (
                            f["name"].replace("_count", "") in field_name
                            or field_name in f["name"]
                        ):
                            count_field = f["name"]
                            break

            if count_field is None:
                print(f"Error: Cannot find count field for fixed_array '{field_name}'")
                sys.exit(1)

            output += f"    for (uint32_t i = 0; i < msg.{count_field} && i < {max_size}; ++i) {{\n"

            if element_type in structs:
                struct_data = structs[element_type]
                for struct_field in struct_data["fields"]:
                    sf_name = struct_field["name"]
                    sf_type = struct_field["type"]

                    if sf_type in ["uint8", "int8"]:
                        output += f"        msg.{field_name}[i].{sf_name} = {data_var}[offset];\n"
                        output += "        offset += 1;\n"

                    elif sf_type == "uint16":
                        temp = read_uint_bytes(
                            f"{field_name}[i].{sf_name}", 2, "uint16_t", endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ")

                    elif sf_type == "int16":
                        temp = read_uint_bytes(
                            f"{field_name}[i].{sf_name}", 2, "int16_t", endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ")

                    elif sf_type == "uint32":
                        temp = read_uint_bytes(
                            f"{field_name}[i].{sf_name}", 4, "uint32_t", endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ")

                    elif sf_type == "int32":
                        temp = read_uint_bytes(
                            f"{field_name}[i].{sf_name}", 4, "int32_t", endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ")

                    elif sf_type == "uint64":
                        temp = read_uint_bytes(
                            f"{field_name}[i].{sf_name}", 8, "uint64_t", endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ")

                    elif sf_type == "int64":
                        temp = read_uint_bytes(
                            f"{field_name}[i].{sf_name}", 8, "int64_t", endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ")

                    elif sf_type == "float":
                        output += "        {\n"
                        output += "            uint32_t temp;\n"
                        temp_read = read_uint_bytes(
                            "temp", 4, "uint32_t", endianness
                        ).replace("msg.", "")
                        output += "        " + temp_read.replace("\n", "\n        ")
                        output += f"            std::memcpy(&msg.{field_name}[i].{sf_name}, &temp, sizeof(float));\n"
                        output += "        }\n"

                    elif sf_type == "double":
                        output += "        {\n"
                        output += "            uint64_t temp;\n"
                        temp_read = read_uint_bytes(
                            "temp", 8, "uint64_t", endianness
                        ).replace("msg.", "")
                        output += "        " + temp_read.replace("\n", "\n        ")
                        output += f"            std::memcpy(&msg.{field_name}[i].{sf_name}, &temp, sizeof(double));\n"
                        output += "        }\n"

                    elif sf_type == "string":
                        max_len = struct_field["max_length"]
                        output += f"        std::memcpy(msg.{field_name}[i].{sf_name}, {data_var}.data() + offset, {max_len});\n"
                        output += f"        offset += {max_len};\n"

            elif element_type in TYPE_MAP:
                if element_type in ["uint8", "int8"]:
                    output += f"        msg.{field_name}[i] = {data_var}[offset];\n"
                    output += "        offset += 1;\n"

                elif element_type == "uint16":
                    temp = read_uint_bytes(
                        f"{field_name}[i]", 2, "uint16_t", endianness
                    )
                    output += "    " + temp.replace("\n", "\n    ")

                elif element_type == "int16":
                    temp = read_uint_bytes(f"{field_name}[i]", 2, "int16_t", endianness)
                    output += "    " + temp.replace("\n", "\n    ")

                elif element_type == "uint32":
                    temp = read_uint_bytes(
                        f"{field_name}[i]", 4, "uint32_t", endianness
                    )
                    output += "    " + temp.replace("\n", "\n    ")

                elif element_type == "int32":
                    temp = read_uint_bytes(f"{field_name}[i]", 4, "int32_t", endianness)
                    output += "    " + temp.replace("\n", "\n    ")

                elif element_type == "uint64":
                    temp = read_uint_bytes(
                        f"{field_name}[i]", 8, "uint64_t", endianness
                    )
                    output += "    " + temp.replace("\n", "\n    ")

                elif element_type == "int64":
                    temp = read_uint_bytes(f"{field_name}[i]", 8, "int64_t", endianness)
                    output += "    " + temp.replace("\n", "\n    ")

                elif element_type == "float":
                    output += "        {\n"
                    output += "            uint32_t temp;\n"
                    temp_read = read_uint_bytes(
                        "temp", 4, "uint32_t", endianness
                    ).replace("msg.", "")
                    output += "        " + temp_read.replace("\n", "\n        ")
                    output += f"            std::memcpy(&msg.{field_name}[i], &temp, sizeof(float));\n"
                    output += "        }\n"

                elif element_type == "double":
                    output += "        {\n"
                    output += "            uint64_t temp;\n"
                    temp_read = read_uint_bytes(
                        "temp", 8, "uint64_t", endianness
                    ).replace("msg.", "")
                    output += "        " + temp_read.replace("\n", "\n        ")
                    output += f"            std::memcpy(&msg.{field_name}[i], &temp, sizeof(double));\n"
                    output += "        }\n"

            output += "    }\n"

        elif field_type == "dynamic_array":
            element_type = field["element_type"]

            output += "    {\n"
            output += "        uint32_t size;\n"
            temp_read = read_uint_bytes("size", 4, "uint32_t", endianness).replace(
                "msg.", ""
            )
            output += "    " + temp_read.replace("\n", "\n    ")
            output += f"        msg.{field_name}.resize(size);\n"
            output += "    }\n"

            output += f"    for (auto& elem : msg.{field_name}) {{\n"

            if element_type in structs:
                struct_data = structs[element_type]
                for struct_field in struct_data["fields"]:
                    sf_name = struct_field["name"]
                    sf_type = struct_field["type"]

                    if sf_type in ["uint8", "int8"]:
                        output += f"        elem.{sf_name} = {data_var}[offset];\n"
                        output += "        offset += 1;\n"

                    elif sf_type == "uint16":
                        temp = read_uint_bytes(
                            f"elem.{sf_name}", 2, "uint16_t", endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ").replace(
                            "msg.", ""
                        )

                    elif sf_type == "int16":
                        temp = read_uint_bytes(
                            f"elem.{sf_name}", 2, "int16_t", endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ").replace(
                            "msg.", ""
                        )

                    elif sf_type == "uint32":
                        temp = read_uint_bytes(
                            f"elem.{sf_name}", 4, "uint32_t", endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ").replace(
                            "msg.", ""
                        )

                    elif sf_type == "int32":
                        temp = read_uint_bytes(
                            f"elem.{sf_name}", 4, "int32_t", endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ").replace(
                            "msg.", ""
                        )

                    elif sf_type == "uint64":
                        temp = read_uint_bytes(
                            f"elem.{sf_name}", 8, "uint64_t", endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ").replace(
                            "msg.", ""
                        )

                    elif sf_type == "int64":
                        temp = read_uint_bytes(
                            f"elem.{sf_name}", 8, "int64_t", endianness
                        )
                        output += "    " + temp.replace("\n", "\n    ").replace(
                            "msg.", ""
                        )

                    elif sf_type == "float":
                        output += "        {\n"
                        output += "            uint32_t temp;\n"
                        temp_read = read_uint_bytes(
                            "temp", 4, "uint32_t", endianness
                        ).replace("msg.", "")
                        output += "        " + temp_read.replace("\n", "\n        ")
                        output += f"            std::memcpy(&elem.{sf_name}, &temp, sizeof(float));\n"
                        output += "        }\n"

                    elif sf_type == "double":
                        output += "        {\n"
                        output += "            uint64_t temp;\n"
                        temp_read = read_uint_bytes(
                            "temp", 8, "uint64_t", endianness
                        ).replace("msg.", "")
                        output += "        " + temp_read.replace("\n", "\n        ")
                        output += f"            std::memcpy(&elem.{sf_name}, &temp, sizeof(double));\n"
                        output += "        }\n"

                    elif sf_type == "string":
                        max_len = struct_field["max_length"]
                        output += f"        std::memcpy(elem.{sf_name}, {data_var}.data() + offset, {max_len});\n"
                        output += f"        offset += {max_len};\n"

            elif element_type in TYPE_MAP:
                if element_type in ["uint8", "int8"]:
                    output += f"        elem = {data_var}[offset];\n"
                    output += "        offset += 1;\n"

                elif element_type == "uint16":
                    temp = read_uint_bytes("elem", 2, "uint16_t", endianness)
                    output += "    " + temp.replace("\n", "\n    ").replace("msg.", "")

                elif element_type == "int16":
                    temp = read_uint_bytes("elem", 2, "int16_t", endianness)
                    output += "    " + temp.replace("\n", "\n    ").replace("msg.", "")

                elif element_type == "uint32":
                    temp = read_uint_bytes("elem", 4, "uint32_t", endianness)
                    output += "    " + temp.replace("\n", "\n    ").replace("msg.", "")

                elif element_type == "int32":
                    temp = read_uint_bytes("elem", 4, "int32_t", endianness)
                    output += "    " + temp.replace("\n", "\n    ").replace("msg.", "")

                elif element_type == "uint64":
                    temp = read_uint_bytes("elem", 8, "uint64_t", endianness)
                    output += "    " + temp.replace("\n", "\n    ").replace("msg.", "")

                elif element_type == "int64":
                    temp = read_uint_bytes("elem", 8, "int64_t", endianness)
                    output += "    " + temp.replace("\n", "\n    ").replace("msg.", "")

                elif element_type == "float":
                    output += "        {\n"
                    output += "            uint32_t temp;\n"
                    temp_read = read_uint_bytes(
                        "temp", 4, "uint32_t", endianness
                    ).replace("msg.", "")
                    output += "        " + temp_read.replace("\n", "\n        ")
                    output += "            std::memcpy(&elem, &temp, sizeof(float));\n"
                    output += "        }\n"

                elif element_type == "double":
                    output += "        {\n"
                    output += "            uint64_t temp;\n"
                    temp_read = read_uint_bytes(
                        "temp", 8, "uint64_t", endianness
                    ).replace("msg.", "")
                    output += "        " + temp_read.replace("\n", "\n        ")
                    output += "            std::memcpy(&elem, &temp, sizeof(double));\n"
                    output += "        }\n"

            elif element_type == "string":
                output += "        {\n"
                output += "            uint32_t str_len;\n"
                temp_read = read_uint_bytes(
                    "str_len", 4, "uint32_t", endianness
                ).replace("msg.", "")
                output += "        " + temp_read.replace("\n", "\n        ")
                output += "            elem.resize(str_len);\n"
                output += "            for (uint32_t j = 0; j < str_len; ++j) {\n"
                output += f"                elem[j] = {data_var}[offset];\n"
                output += "                offset += 1;\n"
                output += "            }\n"
                output += "        }\n"

            output += "    }\n"

        elif field_type == "string":
            max_len = field["max_length"]
            output += f"    std::memcpy(msg.{field_name}, {data_var}.data() + offset, {max_len});\n"
            output += f"    offset += {max_len};\n"

        elif field_type in ["uint8", "int8"]:
            output += f"    msg.{field_name} = {data_var}[offset];\n"
            output += "    offset += 1;\n"

        elif field_type == "uint16":
            output += read_uint_bytes(field_name, 2, "uint16_t", endianness)

        elif field_type == "int16":
            output += read_uint_bytes(field_name, 2, "int16_t", endianness)

        elif field_type == "uint32":
            output += read_uint_bytes(field_name, 4, "uint32_t", endianness)

        elif field_type == "int32":
            output += read_uint_bytes(field_name, 4, "int32_t", endianness)

        elif field_type == "uint64":
            output += read_uint_bytes(field_name, 8, "uint64_t", endianness)

        elif field_type == "int64":
            output += read_uint_bytes(field_name, 8, "int64_t", endianness)

        elif field_type == "float":
            output += "    {\n"
            output += "        uint32_t temp;\n"
            temp_read = read_uint_bytes("temp", 4, "uint32_t", endianness).replace(
                "msg.", ""
            )
            output += "    " + temp_read.replace("\n", "\n    ")
            output += f"        std::memcpy(&msg.{field_name}, &temp, sizeof(float));\n"
            output += "    }\n"

        elif field_type == "double":
            output += "    {\n"
            output += "        uint64_t temp;\n"
            temp_read = read_uint_bytes("temp", 8, "uint64_t", endianness).replace(
                "msg.", ""
            )
            output += "    " + temp_read.replace("\n", "\n    ")
            output += (
                f"        std::memcpy(&msg.{field_name}, &temp, sizeof(double));\n"
            )
            output += "    }\n"

        output += "\n"

    output += "    return msg;\n"
    output += "}\n\n"

    return output


def generate_source(protocol: dict, endianness: str) -> str:
    """Generate the complete .cpp file containing all definitions of"""
    """ serialize and deserialize methods of protocol struct"""
    output = ""
    output += '#include "Network/generated_messages.hpp"\n\n'
    output += "namespace net {\n\n"

    structs = protocol.get("structs", {})

    for msg_name, msg_data in protocol["messages"].items():
        compressed = msg_data.get("compressed", False)
        output += generate_serialize_impl(
            msg_name, msg_data["fields"], endianness, structs, compressed
        )
        output += generate_deserialize_impl(
            msg_name, msg_data["fields"], endianness, structs, compressed
        )

    output += "}  // namespace net\n"
    return output


def write_file(filepath: str, content: str):
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        f.write(content)


def main():
    if len(sys.argv) != 2:
        print("Usage: ./generate_protocol.py path_to.json")
        sys.exit(1)

    protocol = load_protocol(sys.argv[1])
    validate_protocol(protocol)
    endianness = get_endianness(protocol)

    header = generate_header(protocol)
    write_file("include/Network/generated_messages.hpp", header)
    source = generate_source(protocol, endianness)
    write_file("src/generated_messages.cpp", source)


if __name__ == "__main__":
    main()
