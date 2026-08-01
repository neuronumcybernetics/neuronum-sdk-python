"""
Neuronum CLI - Command-line interface for Neuronum Agent management.
"""

import click
import questionary
from pathlib import Path
import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os
import re
import time
import hashlib
from bip_utils import Bip39MnemonicGenerator, Bip39SeedGenerator
from bip_utils import Bip39MnemonicValidator, Bip39Languages

# Configuration
NEURONUM_PATH = Path.home() / ".neuronum"
ENV_FILE = NEURONUM_PATH / ".env"
PUBLIC_KEY_FILE = NEURONUM_PATH / "public_key.pem"
PRIVATE_KEY_FILE = NEURONUM_PATH / "private_key.pem"
DEFAULT_NETWORK = "neuronum.net"
API_BASE_URL = f"https://{DEFAULT_NETWORK}/api"

# Utility Functions

def sign_message(private_key: EllipticCurvePrivateKey, message: bytes) -> str:
    """Sign message using ECDSA-SHA256 and return base64-encoded signature."""
    try:
        signature = private_key.sign(
            message,
            ec.ECDSA(hashes.SHA256())
        )
        return base64.b64encode(signature).decode()
    except Exception as e:
        click.echo(f"Error:Error signing message: {e}")
        return ""

def derive_keys_from_mnemonic(mnemonic: str):
    """Derive EC-SECP256R1 keys from BIP-39 mnemonic and return as PEM format."""
    try:
        # Generate seed from BIP-39 mnemonic
        seed = Bip39SeedGenerator(mnemonic).Generate()

        # Create deterministic key derivation input via SHA-256
        digest = hashlib.sha256(seed).digest()
        int_key = int.from_bytes(digest, "big")

        # Derive EC-SECP256R1 private and public keys
        private_key = ec.derive_private_key(int_key, ec.SECP256R1(), default_backend())
        public_key = private_key.public_key()

        # Serialize keys to PEM format for storage
        pem_private = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        pem_public = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        return private_key, public_key, pem_private, pem_public

    except Exception as e:
        click.echo(f"Error:Error generating keys from mnemonic: {e}")
        return None, None, None, None

def validate_business_password(password: str) -> str | None:
    """Returns an error message, or None if the password is valid."""
    if not password:
        return "Please enter a password."
    if len(password) < 10:
        return "Password must be at least 10 characters."
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter."
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter."
    if not re.search(r"[0-9]", password):
        return "Password must contain at least one number."
    if not re.search(r"[^a-zA-Z0-9]", password):
        return "Password must contain at least one special character."
    return None

def encrypt_mnemonic(mnemonic: str, password: str) -> dict:
    """Encrypts the mnemonic with PBKDF2-SHA256 (600k iterations, 16-byte random salt)
    -> AES-256-GCM (12-byte random IV). Returns base64-encoded salt/iv/ciphertext."""
    salt = os.urandom(16)
    iv = os.urandom(12)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    key = kdf.derive(password.encode("utf-8"))

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, mnemonic.encode("utf-8"), None)

    return {
        "salt": base64.b64encode(salt).decode(),
        "iv": base64.b64encode(iv).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }

def save_credentials(host: str, operator: str, pem_public: bytes, pem_private: bytes, network: str = None):
    """Save agent credentials to .neuronum directory with secure file permissions."""
    import os
    if network is None:
        network = DEFAULT_NETWORK
    try:
        NEURONUM_PATH.mkdir(parents=True, exist_ok=True)

        # Save environment configuration with sensitive data
        env_content = f"HOST={host}\nOPERATOR={operator}\nNETWORK={network}\n"
        ENV_FILE.write_text(env_content)
        os.chmod(ENV_FILE, 0o600)  # Owner read/write only

        # Save public key (world-readable)
        PUBLIC_KEY_FILE.write_bytes(pem_public)
        os.chmod(PUBLIC_KEY_FILE, 0o644)  # Owner read/write, others read

        # Save private key (owner-only access)
        PRIVATE_KEY_FILE.write_bytes(pem_private)
        os.chmod(PRIVATE_KEY_FILE, 0o600)  # Owner read/write only

        return True
    except Exception as e:
        click.echo(f"Error:Error saving credentials: {e}")
        return False

def load_credentials():
    """Load agent credentials from .neuronum directory and return as dictionary."""
    credentials = {}
    try:
        # Load .env data (Host and Mnemonic)
        if not ENV_FILE.exists():
            click.echo("Error: No credentials found. Please create or connect an agent first.")
            return None

        with open(ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, value = line.split("=", 1)
                    # Clean up quotes from mnemonic
                    credentials[key] = value.strip().strip('"')

        credentials['host'] = credentials.get("HOST")
        credentials['operator'] = credentials.get("OPERATOR")
        network = credentials.get("NETWORK", DEFAULT_NETWORK)
        credentials['network'] = network
        credentials['api_base_url'] = f"https://{network}/api"

        # Load Private Key
        with open(PRIVATE_KEY_FILE, "rb") as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,
                backend=default_backend()
            )
            credentials['private_key'] = private_key
            credentials['public_key'] = private_key.public_key()

        return credentials

    except FileNotFoundError:
        click.echo("Error: Credentials files are incomplete. Try deleting the '.neuronum' folder or reconnecting.")
        return None
    except Exception as e:
        click.echo(f"Error loading credentials: {e}")
        return None

# CLI Entry Point

@click.group()
def cli():
    """Neuronum CLI App for Agent management."""
    pass

# Agent Management Commands

@click.command()
def create_agent():
    """Creates a new Business Agent via email verification."""

    # 1. Select network
    network = questionary.text("Network URL:", default=DEFAULT_NETWORK).ask()
    if not network:
        click.echo("Canceled.")
        return
    network = network.strip()
    api_base_url = f"https://{network}/api"

    # 2. Collect business info
    business_name = questionary.text("Company Name:").ask()
    if not business_name:
        click.echo("Canceled.")
        return

    business_email = questionary.text("Business Email:").ask()
    if not business_email:
        click.echo("Canceled.")
        return

    # 2. Send verification email
    click.echo("Sending verification email...")
    try:
        response = requests.post(
            f"{api_base_url}/send_verification_email",
            json={"business_email": business_email, "business_name": business_name},
            timeout=10
        )
        if response.status_code == 400:
            detail = response.json().get("detail", "Invalid request.")
            click.echo(f"Error:{detail}")
            return
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.HTTPError as e:
        click.echo(f"Error:{e}")
        return
    except requests.exceptions.RequestException as e:
        click.echo(f"Error:Error communicating with server: {e}")
        return

    if str(result.get("success", "")).lower() != "true":
        click.echo(f"Error:{result.get('message', 'Failed to send verification email.')}")
        return

    click.echo(f"Verification code sent to {business_email}.")

    # 3. Accept Terms of Service
    click.echo("\nBy creating an Agent you agree to the Neuronum Terms of Service.")
    click.echo("Read them at: https://neuronum.net/legals")
    accepted = questionary.confirm("Do you accept the Terms of Service?").ask()
    if not accepted:
        click.echo("You must accept the Terms of Service to create an Agent.")
        return

    # 4. Enter verification code
    verification_code = questionary.text("Enter the verification code:").ask()
    if not verification_code:
        click.echo("Canceled.")
        return

    # 5. Set a password — used to encrypt the mnemonic before it is ever sent to the
    # server. The server only ever receives the ciphertext; it cannot decrypt it and
    # never sees the password or mnemonic.
    while True:
        password = questionary.password("Set a password (to encrypt your recovery phrase):").ask()
        if not password:
            click.echo("Canceled.")
            return
        pw_error = validate_business_password(password)
        if pw_error:
            click.echo(f"Error:{pw_error}")
            continue
        password_confirm = questionary.password("Confirm password:").ask()
        if password != password_confirm:
            click.echo("Error:Passwords do not match.")
            continue
        break

    # 6. Generate mnemonic + keys, encrypt the mnemonic, then verify email
    click.echo("Verifying...")
    mnemonic_obj = Bip39MnemonicGenerator().FromWordsNumber(12)
    mnemonic = str(mnemonic_obj)
    private_key, _, pem_private, pem_public = derive_keys_from_mnemonic(mnemonic)

    if not private_key:
        return

    business_domain = business_email.split('@')[1]
    encrypted_mnemonic = encrypt_mnemonic(mnemonic, password)

    try:
        response = requests.post(
            f"{api_base_url}/create_agent",
            json={
                "public_key": pem_public.decode("utf-8"),
                "business_email": business_email,
                "business_domain": business_domain,
                "verification_code": verification_code,
                "company_name": business_name,
                "encrypted_mnemonic": encrypted_mnemonic,
            },
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        click.echo(f"Error:Error communicating with server: {e}")
        return

    if str(result.get("success", "")).lower() != "true" or not result.get("host"):
        click.echo(f"Error:{result.get('message', 'Verification failed.')}")
        return

    host = result.get("host")

    # 7. Save credentials and connect
    if save_credentials(host, business_name, pem_public, pem_private, network):
        click.echo(f"\nBusiness Agent created and connected successfully!")
        click.echo(f"Host: {host}")
        click.echo(f"\nYour 12-word mnemonic (SAVE THIS SECURELY):")
        click.echo(f"   {mnemonic}")
        click.echo(f"\nNote:This mnemonic is the ONLY way to recover your Agent.")
        click.echo(f"   Write it down and store it in a safe place!\n")
    else:
        click.echo("Warning:Agent created on server but failed to connect locally.")
        click.echo(f"Your mnemonic: {mnemonic}")

@click.command()
def connect_agent():
    """Connects to an existing Agent using a 12-word mnemonic."""

    # 1. Select network
    network = questionary.text("Network URL:", default=DEFAULT_NETWORK).ask()
    if not network:
        click.echo("Connection canceled.")
        return
    network = network.strip()
    api_base_url = f"https://{network}/api"

    # 2. Get and Validate Mnemonic
    mnemonic = questionary.password("Enter your 12-word BIP-39 mnemonic (space separated):").ask()

    if not mnemonic:
        click.echo("Connection canceled.")
        return

    mnemonic = " ".join(mnemonic.strip().split())
    words = mnemonic.split()

    if len(words) != 12:
        click.echo("Error:Mnemonic must be exactly 12 words.")
        return

    if not Bip39MnemonicValidator(Bip39Languages.ENGLISH).IsValid(mnemonic):
      click.echo("Error:Invalid mnemonic. Please ensure all words are valid BIP-39 words.")
      return

    # 2. Derive Keys
    private_key, public_key, pem_private, pem_public = derive_keys_from_mnemonic(mnemonic)
    if not private_key:
        return

    # 3. Prepare Signed Message
    timestamp = str(int(time.time()))
    public_key_pem_str = pem_public.decode('utf-8')
    message = f"public_key={public_key_pem_str};timestamp={timestamp}"
    signature_b64 = sign_message(private_key, message.encode())

    if not signature_b64:
        return

    # 4. Call API to Connect
    click.echo("Attempting to connect to agent...")
    url = f"{api_base_url}/connect_agent"
    connect_data = {
        "public_key": public_key_pem_str,
        "signed_message": signature_b64,
        "message": message
    }

    try:
        response = requests.post(url, json=connect_data, timeout=10)
        response.raise_for_status()
        host = response.json().get("host")
        operator = response.json().get("operator")
    except requests.exceptions.RequestException as e:
        click.echo(f"Error:Error connecting to agent: {e}")
        return

    # 5. Save Credentials
    if host:
        if save_credentials(host, operator, pem_public, pem_private, network):
            click.echo(f"Successfully connected to Agent '{host}'.")
        # Error saving credentials already echoed in helper
    else:
        click.echo("Error:Failed to retrieve host from server. Connection failed.")


@click.command()
def view_agent():
    """Displays the connection status and host name of the current agent."""

    credentials = load_credentials()

    if credentials:
        click.echo("\n")
        click.echo(f"Status:Connected")
        click.echo(f"Agent ID:   {credentials['host']}")
        click.echo(f"Operator:   {credentials['operator']}")
        click.echo(f"Path:   {NEURONUM_PATH}")
        click.echo("----------------------------")


@click.command()
def verify_agent():
    """Verify domain ownership and submit business details in one step."""

    credentials = load_credentials()
    if not credentials:
        return

    host = credentials['host']
    private_key = credentials['private_key']
    api_base_url = credentials['api_base_url']

    domain = host.replace("::agent", "").strip()

    # --- Pre-check: fetch current DNS + legal status ---
    def make_agent_payload():
        ts = str(int(time.time()))
        msg = f"host={host};timestamp={ts}"
        sig = sign_message(private_key, msg.encode())
        return {"host": host, "signed_message": sig, "message": msg}

    click.echo("\nChecking current verification status...")
    try:
        dns_resp = requests.post(f"{api_base_url}/check_dns_status", json={"agent": make_agent_payload()}, timeout=10)
        legal_resp = requests.post(f"{api_base_url}/check_legal_status", json={"agent": make_agent_payload()}, timeout=10)
        dns_verified = dns_resp.status_code == 200 and dns_resp.json().get("status") == "True"
        legal_verified = legal_resp.status_code == 200 and legal_resp.json().get("status") == "True"
    except requests.exceptions.RequestException:
        dns_verified = False
        legal_verified = False

    if dns_verified and legal_verified:
        click.echo(f"Agent {host} ({credentials['operator']}) is already fully verified (DNS + Legal Entity).")
        return

    if dns_verified:
        click.echo("DNS: verified")
    else:
        click.echo("DNS: not verified")

    if legal_verified:
        click.echo("Legal: verified")
    else:
        click.echo("Legal: pending")

    # --- Step 1: Generate challenge and show DNS record ---
    challenge_value = base64.urlsafe_b64encode(
        hashlib.sha256(f"{host}{int(time.time())}".encode()).digest()
    ).decode().rstrip("=")

    click.echo(f"\nStep 1 — Add DNS TXT Record")
    click.echo(f"\n  Name:   _neuronum.{domain}")
    click.echo(f"  Type:   TXT")
    click.echo(f"  Value:  {challenge_value}")
    dns_confirmed = questionary.confirm("\nHave you added the DNS record?").ask()
    if not dns_confirmed:
        click.echo("Canceled.")
        return

    # --- Step 2: Collect business details ---
    click.echo(f"\nStep 2 — Business Details")

    business_address = questionary.text(f"Business address for {credentials['operator']}:").ask()
    if not business_address:
        click.echo("Canceled.")
        return

    registration_country = questionary.text("Registration country (e.g. DE, US):").ask()
    if not registration_country:
        click.echo("Canceled.")
        return
    
    commercial_register_number = questionary.text("Commercial register number (leave blank if none):").ask()
    commercial_register_number = commercial_register_number.strip() if commercial_register_number else "no_commercial_register_number"

    vat_number = questionary.text("VAT number (leave blank if none):").ask()
    vat_number = vat_number.strip() if vat_number else "no_vat_number"

    # --- Step 3: Sign and submit everything in one call ---
    timestamp = str(int(time.time()))
    message = f"host={host};timestamp={timestamp}"
    signature_b64 = sign_message(private_key, message.encode())
    if not signature_b64:
        return

    click.echo("\nSubmitting verification...")
    try:
        response = requests.post(
            f"{api_base_url}/verify_agent",
            json={
                "host": host,
                "signed_message": signature_b64,
                "message": message,
                "challenge_value": challenge_value,
                "domain": domain,
                "business_address": business_address,
                "registration_country": registration_country,
                "commercial_register_number": commercial_register_number,
                "vat_number": vat_number,
            },
            timeout=15
        )
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        click.echo(f"Error: {e}")
        return

    if str(result.get("success", "")).lower() == "true":
        click.echo(f"\nAgent verification successfully submitted.")
        click.echo("use `verify-agent` to check the verification status.")
    else:
        click.echo(f"\nVerification failed.")
        click.echo(f"Server response: {result.get('detail') or result}")


@click.command()
def delete_agent():
    """Deletes the locally stored credentials and requests agent deletion from the server."""

    # 1. Load Credentials
    credentials = load_credentials()
    if not credentials:
        # Error already echoed in helper
        return

    host = credentials['host']
    private_key = credentials['private_key']

    # 2. Confirmation
    confirm = click.confirm(f"Are you sure you want to permanently delete connection to '{host}'?", default=False)
    if not confirm:
        click.echo("Deletion canceled.")
        return

    # 3. Prepare Signed Message
    timestamp = str(int(time.time()))
    message = f"host={host};timestamp={timestamp}"
    signature_b64 = sign_message(private_key, message.encode())

    if not signature_b64:
        return

    # 4. Call API to Delete
    click.echo(f"Requesting deletion of agent '{host}'...")
    url = f"{credentials['api_base_url']}/delete_agent"
    payload = {
        "host": host,
        "signed_message": signature_b64,
        "message": message
    }

    try:
        response = requests.delete(url, json=payload, timeout=10)
        response.raise_for_status()
        status = response.json().get("status", False)
    except requests.exceptions.RequestException as e:
        click.echo(f"Error:Error communicating with the server during deletion: {e}")
        return

    # 5. Cleanup Local Files
    if status:
        try:
            ENV_FILE.unlink(missing_ok=True)
            PRIVATE_KEY_FILE.unlink(missing_ok=True)
            PUBLIC_KEY_FILE.unlink(missing_ok=True)

            click.echo(f"Neuronum Agent '{host}' has been deleted and local credentials removed.")
        except Exception as e:
            click.echo(f"Warning:Warning: Successfully deleted agent on server, but failed to clean up all local files: {e}")
    else:
        click.echo(f"Error:Neuronum Agent '{host}' deletion failed on server.")


@click.command()
def disconnect_agent():
    """Removes local credentials without deleting the agent on the server."""

    # Check if any files exist to avoid unnecessary actions
    if not ENV_FILE.exists() and not PRIVATE_KEY_FILE.exists() and not PUBLIC_KEY_FILE.exists():
        click.echo("Info:No local Neuronum credentials found to disconnect.")
        return

    # 1. Confirmation
    confirm = click.confirm("Are you sure you want to disconnect? This will remove all local key files and the mnemonic, but your agent will remain active on the server.", default=False)
    if not confirm:
        click.echo("Disconnection canceled.")
        return

    # 2. Cleanup Local Files
    click.echo(f"Removing local credentials from: {NEURONUM_PATH}")

    files_removed = 0

    try:
        if ENV_FILE.exists():
            ENV_FILE.unlink()
            files_removed += 1

        if PRIVATE_KEY_FILE.exists():
            PRIVATE_KEY_FILE.unlink()
            files_removed += 1

        if PUBLIC_KEY_FILE.exists():
            PUBLIC_KEY_FILE.unlink()
            files_removed += 1

        if files_removed > 0:
            click.echo(f"Successfully disconnected. Your credentials are now removed locally.")
            click.echo("You can reconnect later using your 12-word mnemonic (via `connect-agent`).")
        else:
            click.echo("Info:No credentials were found to remove.")

    except Exception as e:
        click.echo(f"Error:Error during local file cleanup: {e}")


@click.command()
@click.option("--network", default="neuronum.net", show_default=True, help="Neuronum network to connect to.")
def start_mcp(network):
    """Start the Neuronum MCP server (stdio transport)."""
    import os
    from neuronum.mcp import mcp
    os.environ.setdefault("NEURONUM_NETWORK", network)
    mcp.run()


# CLI Command Registration

cli.add_command(create_agent)
cli.add_command(connect_agent)
cli.add_command(view_agent)
cli.add_command(verify_agent)
cli.add_command(delete_agent)
cli.add_command(disconnect_agent)
cli.add_command(start_mcp)

if __name__ == "__main__":
    cli()
