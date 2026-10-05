"""Phone key pairs.

When a phone is registered, the app creates an EC P-256 key pair inside the Android Keystore
(the private key never leaves the phone's secure hardware) and sends us the public key.
Every attendance request is signed with the private key; we verify it here. A stolen login
token is therefore useless on another phone or in a script.
"""

import base64
import binascii

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

SUPPORTED_ALGORITHM = "EC_P256"


class InvalidPublicKey(ValueError):
    pass


def load_public_key(b64_der: str) -> ec.EllipticCurvePublicKey:
    """Accepts the base64 DER 'SubjectPublicKeyInfo' that Android's PublicKey.getEncoded() returns."""
    try:
        key = serialization.load_der_public_key(base64.b64decode(b64_der, validate=True))
    except (ValueError, binascii.Error) as exc:
        raise InvalidPublicKey("not a valid public key") from exc
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
        raise InvalidPublicKey("key must be EC P-256")
    return key


def verify_signature(b64_der_public_key: str, payload: str, b64_signature: str) -> bool:
    """ECDSA with SHA-256 (Android: Signature.getInstance("SHA256withECDSA"))."""
    try:
        key = load_public_key(b64_der_public_key)
        signature = base64.b64decode(b64_signature, validate=True)
        key.verify(signature, payload.encode(), ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidPublicKey, InvalidSignature, ValueError, binascii.Error):
        return False
