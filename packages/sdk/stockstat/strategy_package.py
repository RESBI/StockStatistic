from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def package_module(module_file, entrypoint, output, private_key=None):
    module_file = Path(module_file)
    output = Path(output)
    source = module_file.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    key = private_key or Ed25519PrivateKey.generate()
    manifest = {
        "entrypoint": entrypoint,
        "module": module_file.name,
        "sha256": digest,
        "kernel_compatibility": "3.1",
        "public_key": key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
    }
    signature = key.sign(json.dumps(manifest, sort_keys=True).encode("utf-8")).hex()
    manifest["signature"] = signature
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(module_file.name, source)
        archive.writestr("stockstat-strategy.json", json.dumps(manifest, sort_keys=True))
    return manifest


def verify_package(
    path, *, trusted_public_keys=None, scanner=None, max_unpacked_bytes=10 * 1024**2
):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if any(name.startswith(("/", "\\")) or ".." in Path(name).parts for name in names):
            raise ValueError("strategy archive contains an unsafe path")
        if sum(item.file_size for item in archive.infolist()) > max_unpacked_bytes:
            raise ValueError("strategy archive exceeds the unpacked size limit")
        manifest = json.loads(archive.read("stockstat-strategy.json"))
        source = archive.read(manifest["module"])
    if hashlib.sha256(source).hexdigest() != manifest["sha256"]:
        raise ValueError("strategy source digest mismatch")
    signature = bytes.fromhex(manifest.pop("signature"))
    trusted = {key.lower() for key in (trusted_public_keys or ())}
    if trusted and manifest["public_key"].lower() not in trusted:
        raise ValueError("strategy signing key is not trusted")
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(manifest["public_key"]))
    public_key.verify(signature, json.dumps(manifest, sort_keys=True).encode("utf-8"))
    if scanner:
        scanner(manifest, source)
    manifest["signature"] = signature.hex()
    return manifest
