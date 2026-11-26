"""Updater signature checks, including the bad-signature failure path.

Uses the real installer and `.sig` when a local release build exists. The
verification mirrors Tauri's minisign format: a 10-byte prefix before the
Ed25519 key/signature and a BLAKE2b-512 digest of the payload.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "src-tauri/target/release/bundle/nsis"
INSTALLER = BUNDLE / "AI Media Renamer_2.2.5_x64-setup.exe"
SIG_FILE = BUNDLE / "AI Media Renamer_2.2.5_x64-setup.exe.sig"

pytestmark = pytest.mark.skipif(
    not (INSTALLER.is_file() and SIG_FILE.is_file()),
    reason="no local release artifacts to verify",
)


def _public_key() -> Ed25519PublicKey:
    conf = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    encoded = base64.b64decode(conf["plugins"]["updater"]["pubkey"]).decode()
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(encoded.splitlines()[1])[10:42])


def _signature() -> bytes:
    encoded = base64.b64decode(SIG_FILE.read_text()).decode()
    return base64.b64decode(encoded.splitlines()[1])[10:74]


def _digest(data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=64).digest()


def test_real_installer_signature_is_valid():
    _public_key().verify(_signature(), _digest(INSTALLER.read_bytes()))


def test_tampered_installer_is_rejected():
    data = bytearray(INSTALLER.read_bytes())
    data[-1] ^= 0xFF
    with pytest.raises(InvalidSignature):
        _public_key().verify(_signature(), _digest(bytes(data)))


def test_tampered_signature_is_rejected():
    signature = bytearray(_signature())
    signature[0] ^= 0xFF
    with pytest.raises(InvalidSignature):
        _public_key().verify(bytes(signature), _digest(INSTALLER.read_bytes()))
