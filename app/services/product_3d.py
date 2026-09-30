import json
import struct


class Invalid3DModel(ValueError):
    pass


_ALLOWED_MIME_TYPES = {
    ".glb": {"model/gltf-binary", "application/octet-stream"},
    ".gltf": {"model/gltf+json", "application/json", "text/plain", "application/octet-stream"},
}
_JSON_CHUNK_TYPE = 0x4E4F534A
_BINARY_CHUNK_TYPE = 0x004E4942


def validate_3d_model(contents, extension, mimetype, max_bytes):
    extension = extension.lower()
    if extension not in _ALLOWED_MIME_TYPES:
        raise Invalid3DModel("Only self-contained .glb or .gltf models are supported.")
    if mimetype.lower() not in _ALLOWED_MIME_TYPES[extension]:
        raise Invalid3DModel("The model content type does not match its file format.")
    if not contents or len(contents) > max_bytes:
        raise Invalid3DModel("The model is empty or exceeds the configured 50 MB limit.")

    binary_chunk = b""
    if extension == ".glb":
        if len(contents) < 20:
            raise Invalid3DModel("This GLB file is incomplete.")
        magic, version, declared_length = struct.unpack_from("<4sII", contents, 0)
        if magic != b"glTF" or version != 2 or declared_length != len(contents):
            raise Invalid3DModel("The file is not a valid glTF 2.0 binary model.")
        json_length, json_type = struct.unpack_from("<II", contents, 12)
        if json_type != _JSON_CHUNK_TYPE or json_length % 4 or 20 + json_length > len(contents):
            raise Invalid3DModel("The GLB JSON chunk is invalid.")
        json_data = contents[20:20 + json_length].rstrip(b"\x00 \t\r\n")
        chunk_offset = 20 + json_length
        if chunk_offset < len(contents):
            if chunk_offset + 8 > len(contents):
                raise Invalid3DModel("The GLB binary chunk is incomplete.")
            binary_length, binary_type = struct.unpack_from("<II", contents, chunk_offset)
            if binary_type != _BINARY_CHUNK_TYPE or chunk_offset + 8 + binary_length != len(contents):
                raise Invalid3DModel("The GLB binary chunk is invalid.")
            binary_chunk = contents[chunk_offset + 8:]
    else:
        json_data = contents

    try:
        document = json.loads(json_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Invalid3DModel("The model does not contain valid glTF JSON.") from error

    if not isinstance(document, dict) or document.get("asset", {}).get("version") != "2.0":
        raise Invalid3DModel("Only glTF 2.0 models are supported.")
    for resource_group in ("buffers", "images"):
        for resource in document.get(resource_group, []):
            uri = resource.get("uri")
            if uri and not uri.startswith("data:"):
                raise Invalid3DModel("Models must be self-contained; external file references are not allowed.")
    if binary_chunk and document.get("buffers"):
        buffer_length = document["buffers"][0].get("byteLength", 0)
        if buffer_length > len(binary_chunk):
            raise Invalid3DModel("The model references data outside its GLB binary chunk.")
    return document
