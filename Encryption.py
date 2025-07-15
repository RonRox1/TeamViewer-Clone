#Encryption.py
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asy_pad
from cryptography.hazmat.primitives import serialization, hashes, padding as sy_pad
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import os


def generate_rsa_keys():
    """
    Generate an RSA private-public key pair.

    :return: Tuple containing (private_key, public_key).
    :rtype: (rsa.RSAPrivateKey, rsa.RSAPublicKey)
    """
    # Generate private RSA key with public exponent 65537 and 2048-bit key size
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    # Derive the corresponding public key from private key
    public_key = private_key.public_key()
    return private_key, public_key


def generate_aes_key():
    """
    Generate a random 256-bit AES key.

    :return: AES key bytes.
    :rtype: bytes
    """
    # os.urandom generates cryptographically secure random bytes
    return os.urandom(32)  # 32 bytes = 256 bits


def rsa_encrypt(public_key, text):
    """
    Encrypt text using RSA public key with OAEP padding.

    :param public_key: RSA public key for encryption.
    :type public_key: rsa.RSAPublicKey
    :param text: Plaintext to encrypt (str or bytes).
    :type text: str or bytes
    :return: Encrypted ciphertext bytes.
    :rtype: bytes
    """
    # Convert text to bytes if necessary
    if type(text) is not bytes:
        text = text.encode()

    # Encrypt using OAEP padding with SHA-256 as hash function
    ciphertext = public_key.encrypt(
        text,
        asy_pad.OAEP(
            mgf=asy_pad.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return ciphertext


def rsa_decrypt(private_key, ciphertext):
    """
    Decrypt ciphertext using RSA private key with OAEP padding.

    :param private_key: RSA private key for decryption.
    :type private_key: rsa.RSAPrivateKey
    :param ciphertext: Encrypted bytes to decrypt.
    :type ciphertext: bytes
    :return: Decrypted plaintext bytes.
    :rtype: bytes
    """
    # Decrypt ciphertext using OAEP padding with SHA-256 as hash function
    decrypted_message = private_key.decrypt(
        ciphertext,
        asy_pad.OAEP(
            mgf=asy_pad.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return decrypted_message


def serialize_public_key(public_key):
    """
    Serialize RSA public key to PEM format bytes.

    :param public_key: RSA public key to serialize.
    :type public_key: rsa.RSAPublicKey
    :return: PEM-encoded public key bytes.
    :rtype: bytes
    """
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return pem


def deserialize_public_key(pem):
    """
    Deserialize PEM bytes to RSA public key.

    :param pem: PEM-encoded public key bytes.
    :type pem: bytes
    :return: RSA public key object.
    :rtype: rsa.RSAPublicKey
    """
    return serialization.load_pem_public_key(pem)


def encrypt_aes(key, text):
    """
    Encrypt text using AES-CBC with PKCS7 padding.

    :param key: AES key bytes (256-bit).
    :type key: bytes
    :param text: Plaintext to encrypt (str or bytes).
    :type text: str or bytes
    :return: Tuple (iv, ciphertext) where iv is the initialization vector.
    :rtype: (bytes, bytes)
    """
    # Convert text to bytes if necessary
    if type(text) is not bytes:
        text = text.encode()

    # Generate a random 16-byte IV for AES CBC mode
    iv = os.urandom(16)

    # Pad the plaintext to be multiple of block size (128 bits for AES)
    padder = sy_pad.PKCS7(128).padder()
    padded_data = padder.update(text) + padder.finalize()

    # Create AES cipher object in CBC mode
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()

    # Encrypt the padded plaintext
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    return iv, ciphertext


def decrypt_aes(key, iv, ciphertext):
    """
    Decrypt AES-CBC encrypted ciphertext with PKCS7 padding removal.

    :param key: AES key bytes (256-bit).
    :type key: bytes
    :param iv: Initialization vector used during encryption.
    :type iv: bytes
    :param ciphertext: Encrypted ciphertext bytes.
    :type ciphertext: bytes
    :return: Decrypted plaintext bytes.
    :rtype: bytes
    """
    # Create AES cipher object in CBC mode with provided IV
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()

    # Decrypt ciphertext to padded plaintext
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # Remove PKCS7 padding from plaintext
    unpadder = sy_pad.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
    return plaintext
