import aiohttp
import aiofiles
from typing import AsyncGenerator, Optional, Dict, Any, List
import json
import asyncio
import base64
import os
import time
import logging
from pathlib import Path
from dataclasses import dataclass
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend
from abc import ABC, abstractmethod


# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Exceptions
class NeuronumError(Exception):
    """Base exception for Neuronum errors"""
    pass


class AuthenticationError(NeuronumError):
    """Raised when authentication fails"""
    pass


class EncryptionError(NeuronumError):
    """Raised when encryption/decryption fails"""
    pass


class CellNotFoundError(NeuronumError):
    """Raised when a cell cannot be found"""
    pass


class NetworkError(NeuronumError):
    """Raised when network operations fail"""
    pass


# Configuration
@dataclass
class ClientConfig:
    """Client configuration settings"""
    network: str = "neuronum.net"
    cache_expiry: int = 3600
    credentials_path: Path = Path.home() / ".neuronum"
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    max_retry_delay: float = 60.0
    websocket_ping_interval: int = 20
    websocket_ping_timeout: int = 10


class CryptoManager:
    """Handles all cryptographic operations"""
    
    def __init__(self, private_key: Optional[ec.EllipticCurvePrivateKey] = None):
        self._private_key = private_key
        self._public_key = private_key.public_key() if private_key else None
    
    def sign_message(self, message: bytes) -> str:
        """Sign a message with the private key"""
        if not self._private_key:
            raise EncryptionError("Private key not available for signing")
        
        try:
            signature = self._private_key.sign(message, ec.ECDSA(hashes.SHA256()))
            return base64.b64encode(signature).decode()
        except Exception as e:
            logger.error("Failed to sign message", exc_info=True)
            raise EncryptionError(f"Message signing failed: {e}")
    
    def get_public_key_pem(self) -> str:
        """Get public key in PEM format"""
        if not self._public_key:
            raise EncryptionError("Public key not available")
        
        pem_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem_bytes.decode('utf-8')
    
    def load_public_key_from_pem(self, pem_string: str) -> ec.EllipticCurvePublicKey:
        """Load a public key from PEM format"""
        try:
            return serialization.load_pem_public_key(
                pem_string.encode(), 
                backend=default_backend()
            )
        except Exception as e:
            logger.error("Failed to load public key from PEM", exc_info=True)
            raise EncryptionError(f"Failed to load public key: {e}")
    
    @staticmethod
    def safe_b64decode(data: str) -> bytes:
        """Safely decode base64 with proper padding"""
        padding = 4 - (len(data) % 4)
        if padding != 4:
            data += '=' * padding
        return base64.urlsafe_b64decode(data)
    
    def encrypt_with_ecdh_aesgcm(
        self, 
        public_key: ec.EllipticCurvePublicKey, 
        plaintext_dict: Dict[str, Any]
    ) -> Dict[str, str]:
        """Encrypt data using ECDH + AES-GCM"""
        try:
            ephemeral_private = ec.generate_private_key(ec.SECP256R1())
            shared_secret = ephemeral_private.exchange(ec.ECDH(), public_key)
            derived_key = HKDF(
                algorithm=hashes.SHA256(), 
                length=32, 
                salt=None, 
                info=b'handshake data'
            ).derive(shared_secret)
            
            aesgcm = AESGCM(derived_key)
            nonce = os.urandom(12)
            plaintext_bytes = json.dumps(plaintext_dict).encode()
            ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)
            
            ephemeral_public_bytes = ephemeral_private.public_key().public_bytes(
                serialization.Encoding.X962, 
                serialization.PublicFormat.UncompressedPoint
            )
            
            return {
                'ciphertext': base64.urlsafe_b64encode(ciphertext).rstrip(b'=').decode(),
                'nonce': base64.urlsafe_b64encode(nonce).rstrip(b'=').decode(),
                'ephemeralPublicKey': base64.urlsafe_b64encode(ephemeral_public_bytes).rstrip(b'=').decode()
            }
        except Exception as e:
            logger.error("Encryption failed", exc_info=True)
            raise EncryptionError(f"Encryption failed: {e}")
    
    def decrypt_with_ecdh_aesgcm(
        self, 
        ephemeral_public_key_bytes: bytes, 
        nonce: bytes, 
        ciphertext: bytes
    ) -> Dict[str, Any]:
        """Decrypt data using ECDH + AES-GCM"""
        if not self._private_key:
            raise EncryptionError("Private key not available for decryption")
        
        try:
            ephemeral_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256R1(), ephemeral_public_key_bytes
            )
            shared_secret = self._private_key.exchange(ec.ECDH(), ephemeral_public_key)
            derived_key = HKDF(
                algorithm=hashes.SHA256(), 
                length=32, 
                salt=None, 
                info=b'handshake data'
            ).derive(shared_secret)
            
            aesgcm = AESGCM(derived_key)
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
            return json.loads(plaintext_bytes.decode())
        except Exception as e:
            logger.error("Decryption failed", exc_info=True)
            raise EncryptionError(f"Decryption failed: {e}")


class CacheManager:
    """Manages cell cache with async file operations"""
    
    def __init__(self, config: ClientConfig):
        self.config = config
        self.cache_file = config.credentials_path / "cells.json"
        self._lock = asyncio.Lock()
        self._memory_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_time: Optional[float] = None
    
    async def get_cells(self) -> List[Dict[str, Any]]:
        """Get cached cells if valid, otherwise fetch new"""
        async with self._lock:
            # Check memory cache first
            if self._is_memory_cache_valid():
                logger.debug("Using in-memory cache")
                return self._memory_cache
            
            # Check file cache
            if await self._is_file_cache_valid():
                logger.debug("Using file cache")
                cells = await self._load_from_file()
                self._update_memory_cache(cells)
                return cells
            
            return None
    
    async def update_cells(self, cells: List[Dict[str, Any]]) -> None:
        """Update cache with new cell data"""
        async with self._lock:
            self._update_memory_cache(cells)
            await self._save_to_file(cells)
    
    def _is_memory_cache_valid(self) -> bool:
        """Check if memory cache is still valid"""
        if not self._memory_cache or not self._cache_time:
            return False
        return (time.time() - self._cache_time) < self.config.cache_expiry
    
    async def _is_file_cache_valid(self) -> bool:
        """Check if file cache is still valid"""
        if not self.cache_file.exists():
            return False
        
        try:
            file_mtime = os.path.getmtime(self.cache_file)
            return (time.time() - file_mtime) < self.config.cache_expiry
        except OSError:
            return False
    
    async def _load_from_file(self) -> List[Dict[str, Any]]:
        """Load cells from cache file"""
        try:
            async with aiofiles.open(self.cache_file, 'r') as f:
                content = await f.read()
                return json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load cache file: {e}")
            return []
    
    async def _save_to_file(self, cells: List[Dict[str, Any]]) -> None:
        """Save cells to cache file"""
        try:
            self.config.credentials_path.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(self.cache_file, 'w') as f:
                await f.write(json.dumps(cells, indent=4))
            logger.debug("Cache file updated")
        except Exception as e:
            logger.error(f"Failed to save cache file: {e}")
    
    def _update_memory_cache(self, cells: List[Dict[str, Any]]) -> None:
        """Update in-memory cache"""
        self._memory_cache = cells
        self._cache_time = time.time()


class NetworkClient:
    """Handles all network operations with retry logic"""

    def __init__(self, config: ClientConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    def __del__(self):
        """Cleanup: warn if session wasn't properly closed"""
        if self._session and not self._session.closed:
            logger.warning(
                "NetworkClient session was not properly closed. "
                "Use 'async with NetworkClient(...)' or call close() explicitly."
            )
    
    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )
        return self
    
    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()
            self._session = None

    async def close(self):
        """Explicitly close the session"""
        if self._session:
            await self._session.close()
            self._session = None

    async def post_request(
        self,
        url: str,
        payload: Dict[str, Any],
        retry_count: int = 0
    ) -> Optional[Dict[str, Any]]:
        """Make POST request with retry logic"""
        # Create session if needed, but ensure it's tracked for cleanup
        session_created_here = False
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            )
            session_created_here = True
        
        try:
            async with self._session.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP error {e.status} for URL: {url}")
            if retry_count < self.config.max_retries and e.status >= 500:
                return await self._retry_request(url, payload, retry_count)
            raise NetworkError(f"HTTP {e.status} error")
        except aiohttp.ClientError as e:
            logger.error(f"Client error for URL {url}: {e}")
            if retry_count < self.config.max_retries:
                return await self._retry_request(url, payload, retry_count)
            raise NetworkError(f"Client error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error for URL {url}: {e}")
            raise NetworkError(f"Unexpected error: {e}")
    
    async def _retry_request(
        self, 
        url: str, 
        payload: Dict[str, Any], 
        retry_count: int
    ) -> Optional[Dict[str, Any]]:
        """Retry request with exponential backoff"""
        delay = min(
            self.config.retry_delay * (2 ** retry_count),
            self.config.max_retry_delay
        )
        logger.info(f"Retrying request in {delay}s (attempt {retry_count + 1})")
        await asyncio.sleep(delay)
        return await self.post_request(url, payload, retry_count + 1)


class BaseClient(ABC):
    """Base client with common functionality"""

    def __init__(self, config: Optional[ClientConfig] = None):
        self.config = config or ClientConfig()
        self.env: Dict[str, str] = {}
        self._crypto: Optional[CryptoManager] = None
        self._cache_manager = CacheManager(self.config)
        self._network_client = NetworkClient(self.config)
        self.host = ""
        self.network = self.config.network

    @abstractmethod
    def _load_private_key(self) -> Optional[ec.EllipticCurvePrivateKey]:
        """Load private key (must be implemented by subclasses)"""
        pass
    
    def _init_crypto(self, private_key: Optional[ec.EllipticCurvePrivateKey]) -> None:
        """Initialize crypto manager with private key"""
        self._crypto = CryptoManager(private_key)
    
    def to_dict(self) -> Dict[str, str]:
        """Create authentication payload"""
        if not self._crypto:
            logger.warning("Crypto manager not initialized")
            timestamp = str(int(time.time()))
            return {
                "host": self.host,
                "signed_message": "",
                "message": f"host={self.host};timestamp={timestamp}"
            }
        
        timestamp = str(int(time.time()))
        message = f"host={self.host};timestamp={timestamp}"
        
        try:
            signed_message = self._crypto.sign_message(message.encode())
        except EncryptionError:
            logger.error("Failed to sign authentication message")
            signed_message = ""
        
        return {
            "host": self.host,
            "signed_message": signed_message,
            "message": message
        }
    
    async def _get_target_cell_public_key(self, cell_id: str) -> str:
        """Get public key for target cell"""
        cells = await self.list_cells(update=False)

        for cell in cells:
            if cell.get('cell_id') == cell_id:
                public_key = cell.get('public_key', {})
                if public_key:
                    return public_key

        logger.info(f"Cell {cell_id} not in cache, refreshing")
        cells = await self.list_cells(update=True)
        
        for cell in cells:
            if cell.get('cell_id') == cell_id:
                public_key = cell.get('public_key', {})
                if public_key:
                    return public_key
        
        raise CellNotFoundError(f"Cell not found: {cell_id}")


    async def list_cells(self, update: bool = False) -> List[Dict[str, Any]]:
        """List all available cells with optional cache refresh"""
        if not update:
            cached_cells = await self._cache_manager.get_cells()
            if cached_cells is not None:
                return cached_cells

        full_url = f"https://{self.network}/api/list_cells"
        payload = {"cell": self.to_dict()}
        
        try:
            data = await self._network_client.post_request(full_url, payload)
            cells = data.get("Cells", []) if data else []
            await self._cache_manager.update_cells(cells)
            return cells
        except NetworkError as e:
            logger.error(f"Failed to fetch cells: {e}")
            return []
        

    async def _fetch_session_metadata(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Fetch session metadata from list_sessions."""
        sessions = await self.list_sessions()
        for s in sessions:
            if s.get("session_id") == session_id:
                return s
        return None


    async def list_sessions(self) -> List[Dict[str, Any]]:
        """List all secure cell sessions for this cell."""
        
        full_url = f"https://{self.network}/api/list_sessions"
        payload = {"cell": self.to_dict()}

        try:
            data = await self._network_client.post_request(full_url, payload)
            sessions = data.get("Sessions", []) if data else []
            return sessions
        except NetworkError as e:
            logger.error(f"Failed to fetch sessions: {e}")
            return []

    async def create_secure_agent_session(self, receiver_cell_id: str = None, receiver_email: str = None) -> Optional[Dict[str, Any]]:
        """Create a secure B2B session using either a cell_id or an email."""

        if not receiver_cell_id and not receiver_email:
            raise ValueError("You must provide either receiver_cell_id or receiver_email")

        if receiver_cell_id and receiver_email:
            raise ValueError("Provide only one: receiver_cell_id OR receiver_email")

        full_url = f"https://{self.network}/api/create_secure_agent_session"

        payload = {
            "cell": self.to_dict(),
            "receiver_cell_id": receiver_cell_id,
            "receiver_email": receiver_email
        }

        try:
            data = await self._network_client.post_request(full_url, payload)
            return data
        except NetworkError as e:
            logger.error(f"Failed to create secure cell session: {e}")
            return None

    
    async def get_session_messages(self, session_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch and decrypt all messages for a session."""
        
        if not isinstance(self, Cell):
            raise ValueError("sync_session_messages must be called from an Cell instance")

        if not getattr(self, 'host', None):
            raise ValueError("host is required for sync_session_messages")

        if not self._crypto:
            raise EncryptionError("Crypto manager not initialized")

        full_url = f"https://{self.network}/api/get_session_messages/{session_id}"
        payload = {"cell": self.to_dict()}

        try:
            # 1) Fetch encrypted messages
            data = await self._network_client.post_request(full_url, payload)
            messages = data.get("Messages", []) if data else []

            # 2) Iterate and decrypt only messages intended for this cell
            for msg in messages:
                ciphertext = msg.get("ciphertext")
                if not ciphertext:
                    continue

                try:
                    # Extract fields
                    ephemeral_public_key_bytes = CryptoManager.safe_b64decode(
                        ciphertext["ephemeralPublicKey"]
                    )
                    nonce = CryptoManager.safe_b64decode(ciphertext["nonce"])
                    ct = CryptoManager.safe_b64decode(ciphertext["ciphertext"])

                    # Attempt decryption
                    decrypted = self._crypto.decrypt_with_ecdh_aesgcm(
                        ephemeral_public_key_bytes,
                        nonce,
                        ct
                    )

                    # Build final message object
                    yield {
                        "tx_id": msg["tx_id"],
                        "time": msg["time"],
                        "sender": msg["sender"],
                        "data": decrypted
                    }

                except EncryptionError:
                    # Message was not encrypted for this cell → skip
                    continue

        except NetworkError as e:
            logger.error(f"Failed to sync session messages: {e}")
            return


    async def send_session_message(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Send an encrypted message to a secure cell session."""
        
        if not isinstance(self, Cell):
            raise ValueError("send_session_message must be called from an Cell instance")

        if not getattr(self, 'host', None):
            raise ValueError("host is required for send_session_message")

        if not self._crypto:
            raise EncryptionError("Crypto manager not initialized")

        # 1) Fetch session details from server
        #    (to know who the other participant is)
        session = await self._fetch_session_metadata(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return False

        requester = session["requester_cell_id"]
        receiver = session["receiver_cell_id"]

        # 2) Determine the other participant
        if self.host == requester:
            other_cell_id = receiver
        elif self.host == receiver:
            other_cell_id = requester
        else:
            raise ValueError("This cell is not part of the session")

        # 3) Load public keys
        sender_public_key_pem = self._crypto.get_public_key_pem()

        # Web-based sessions: receiver has no cell — their public key is stored in
        # session metadata after their first message. Cell IDs always end in "::cell".
        if other_cell_id.endswith("::cell"):
            receiver_public_key_pem = await self._get_target_cell_public_key(other_cell_id)
        else:
            receiver_public_key_pem = session.get("receiver_public_key")
            if not receiver_public_key_pem:
                logger.error(f"No receiver public key in session metadata yet for session {session_id}")
                return False

        sender_public_key = self._crypto.load_public_key_from_pem(sender_public_key_pem)
        receiver_public_key = self._crypto.load_public_key_from_pem(receiver_public_key_pem)

        # 4) Encrypt twice (sender + receiver)
        cipher_for_sender = self._crypto.encrypt_with_ecdh_aesgcm(
            sender_public_key,
            data
        )

        cipher_for_receiver = self._crypto.encrypt_with_ecdh_aesgcm(
            receiver_public_key,
            data
        )

        # 5) Build payload
        payload = {
            "cell": self.to_dict(),
            "data": {
                "cipher_for_sender": cipher_for_sender,
                "cipher_for_receiver": cipher_for_receiver
            }
        }

        # 6) Send to server
        full_url = f"https://{self.network}/api/send_session_message/{session_id}"

        try:
            response = await self._network_client.post_request(full_url, payload)
            if response and response.get("success"):
                logger.info(f"Message sent to session {session_id}")
                return True
            else:
                logger.error(f"Failed to send message: {response}")
                return False

        except NetworkError as e:
            logger.error(f"Network error sending session message: {e}")
            return False


class Cell(BaseClient):
    """Cell client implementation"""

    def __init__(self, config: Optional[ClientConfig] = None, network: str = "testnet.neuronum.net"):
        if config is None:
            config = ClientConfig(network=network)
        super().__init__(config)
        self.env = self._load_env()
        private_key = self._load_private_key()
        self._init_crypto(private_key)

        self.host = self.env.get("HOST", "")
        if not self.host:
            logger.warning("HOST not set in environment")
    
    def _load_private_key(self) -> Optional[ec.EllipticCurvePrivateKey]:
        """Load private key from credentials folder"""
        credentials_path = self.config.credentials_path
        credentials_path.mkdir(parents=True, exist_ok=True)
        
        key_path = credentials_path / "private_key.pem"
        
        try:
            with open(key_path, "rb") as f:
                private_key = serialization.load_pem_private_key(
                    f.read(), 
                    password=None, 
                    backend=default_backend()
                )
            
            stat = os.stat(key_path)
            if stat.st_mode & 0o177:
                logger.warning(
                    f"Private key file has insecure permissions: {oct(stat.st_mode)}. "
                    f"Automatically fixing permissions to 0600 for security."
                )
                try:
                    os.chmod(key_path, 0o600)
                    logger.info(f"Successfully set permissions to 0600 on {key_path}")
                except Exception as chmod_error:
                    logger.error(
                        f"Failed to fix permissions automatically: {chmod_error}. "
                        f"Please manually run: chmod 600 {key_path}"
                    )
                    raise PermissionError(
                        f"Cannot fix insecure permissions on private key. "
                        f"Please run: chmod 600 {key_path}"
                    )

            logger.info("Private key loaded successfully")
            return private_key
        except FileNotFoundError:
            logger.error(f"Private key not found at {key_path}")
            return None
        except Exception as e:
            logger.error(f"Error loading private key: {e}")
            return None
    
    def _load_env(self) -> Dict[str, str]:
        """Load environment variables from .env file"""
        env_path = self.config.credentials_path / ".env"
        env_data = {}
        
        try:
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_data[key.strip()] = value.strip()
            logger.info("Environment loaded successfully")
            return env_data
        except FileNotFoundError:
            logger.error(f"Environment file not found at {env_path}")
            return {}
        except Exception as e:
            logger.error(f"Error loading environment: {e}")
            return {}
        
    async def __aenter__(self):
        await self._network_client.__aenter__()
        return self
    
    async def __aexit__(self, *args):
        await self._network_client.__aexit__(*args)