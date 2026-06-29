"""
Neuronum CLI - Command-line interface for Neuronum Cell management.
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
import base64
import time
import hashlib
from bip_utils import Bip39MnemonicGenerator, Bip39SeedGenerator
from bip_utils import Bip39MnemonicValidator, Bip39Languages

# Configuration
NEURONUM_PATH = Path.home() / ".neuronum"
ENV_FILE = NEURONUM_PATH / ".env"
PUBLIC_KEY_FILE = NEURONUM_PATH / "public_key.pem"
PRIVATE_KEY_FILE = NEURONUM_PATH / "private_key.pem"
DEFAULT_NETWORK = "testnet.neuronum.net"
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

def save_credentials(host: str, operator: str, pem_public: bytes, pem_private: bytes, cell_type: str, network: str = None):
    """Save cell credentials to .neuronum directory with secure file permissions."""
    import os
    if network is None:
        network = DEFAULT_NETWORK
    try:
        NEURONUM_PATH.mkdir(parents=True, exist_ok=True)

        # Save environment configuration with sensitive data
        env_content = f"HOST={host}\nOPERATOR={operator}\nTYPE={cell_type}\nNETWORK={network}\n"
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
    """Load cell credentials from .neuronum directory and return as dictionary."""
    credentials = {}
    try:
        # Load .env data (Host and Mnemonic)
        if not ENV_FILE.exists():
            click.echo("Error: No credentials found. Please create or connect a cell first.")
            return None

        with open(ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, value = line.split("=", 1)
                    # Clean up quotes from mnemonic
                    credentials[key] = value.strip().strip('"')

        credentials['host'] = credentials.get("HOST")
        credentials['type'] = credentials.get("TYPE")
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
    """Neuronum CLI App for Cell management."""
    pass

# Cell Management Commands

@click.command()
def create_cell():
    """Creates a new Business Cell via email verification."""

    # 1. Select network
    network = questionary.text("Network URL:", default=DEFAULT_NETWORK).ask()
    if not network:
        click.echo("Canceled.")
        return
    network = network.strip()
    api_base_url = f"https://{network}/api"

    # 2. Collect business info
    business_name = questionary.text("Company / business name:").ask()
    if not business_name:
        click.echo("Canceled.")
        return

    business_email = questionary.text("Business email:").ask()
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
    click.echo("\nBy creating a Cell you agree to the Neuronum Terms of Service.")
    click.echo("Read them at: https://neuronum.net/legals")
    accepted = questionary.confirm("Do you accept the Terms of Service?").ask()
    if not accepted:
        click.echo("You must accept the Terms of Service to create a Cell.")
        return

    # 4. Enter verification code
    verification_code = questionary.text("Enter the verification code:").ask()
    if not verification_code:
        click.echo("Canceled.")
        return

    # 5. Generate mnemonic + keys, then verify email
    click.echo("Verifying...")
    mnemonic_obj = Bip39MnemonicGenerator().FromWordsNumber(12)
    mnemonic = str(mnemonic_obj)
    private_key, _, pem_private, pem_public = derive_keys_from_mnemonic(mnemonic)

    if not private_key:
        return

    business_domain = business_email.split('@')[1]

    try:
        response = requests.post(
            f"{api_base_url}/verify_email",
            json={
                "public_key": pem_public.decode("utf-8"),
                "business_email": business_email,
                "business_domain": business_domain,
                "verification_code": verification_code,
                "company_name": business_name
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

    # 6. Save credentials and connect
    if save_credentials(host, business_name, pem_public, pem_private, "business", network):
        click.echo(f"\nBusiness Cell created and connected successfully!")
        click.echo(f"Host: {host}")
        click.echo(f"\nYour 12-word mnemonic (SAVE THIS SECURELY):")
        click.echo(f"   {mnemonic}")
        click.echo(f"\nNote:This mnemonic is the ONLY way to recover your Cell.")
        click.echo(f"   Write it down and store it in a safe place!\n")
    else:
        click.echo("Warning:Cell created on server but failed to connect locally.")
        click.echo(f"Your mnemonic: {mnemonic}")

@click.command()
def connect_cell():
    """Connects to an existing Cell using a 12-word mnemonic."""

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
    click.echo("Attempting to connect to cell...")
    url = f"{api_base_url}/connect_cell"
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
        cell_type = response.json().get("cell_type")
    except requests.exceptions.RequestException as e:
        click.echo(f"Error:Error connecting to cell: {e}")
        return

    # 5. Save Credentials
    if host and cell_type:
        if save_credentials(host, operator, pem_public, pem_private, cell_type, network):
            click.echo(f"Successfully connected to Cell '{host}'.")
        # Error saving credentials already echoed in helper
    else:
        click.echo("Error:Failed to retrieve host from server. Connection failed.")


@click.command()
def view_cell():
    """Displays the connection status and host name of the current cell."""

    credentials = load_credentials()

    if credentials:
        click.echo("\n")
        click.echo(f"Status:Connected")
        click.echo(f"Cell ID:   {credentials['host']}")
        click.echo(f"Operator:   {credentials['operator']}")
        click.echo(f"Path:   {NEURONUM_PATH}")
        click.echo("----------------------------")


@click.command()
def verify_cell():
    """Verify domain ownership and submit business details in one step."""

    credentials = load_credentials()
    if not credentials:
        return

    host = credentials['host']
    private_key = credentials['private_key']
    api_base_url = credentials['api_base_url']

    domain = host.replace("::cell", "").strip()

    # --- Pre-check: fetch current DNS + legal status ---
    def make_cell_payload():
        ts = str(int(time.time()))
        msg = f"host={host};timestamp={ts}"
        sig = sign_message(private_key, msg.encode())
        return {"host": host, "signed_message": sig, "message": msg}

    click.echo("\nChecking current verification status...")
    try:
        dns_resp = requests.post(f"{api_base_url}/check_dns_status", json={"cell": make_cell_payload()}, timeout=10)
        legal_resp = requests.post(f"{api_base_url}/check_legal_status", json={"cell": make_cell_payload()}, timeout=10)
        dns_verified = dns_resp.status_code == 200 and dns_resp.json().get("status") == "True"
        legal_verified = legal_resp.status_code == 200 and legal_resp.json().get("status") == "True"
    except requests.exceptions.RequestException:
        dns_verified = False
        legal_verified = False

    if dns_verified and legal_verified:
        click.echo(f"Cell {host} ({credentials['operator']}) is already fully verified (DNS + Legal Entity).")
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

    tax_number = questionary.text("Tax / VAT number (leave blank if none):").ask()
    tax_number = tax_number.strip() if tax_number else "no_tax"

    # --- Step 3: Sign and submit everything in one call ---
    timestamp = str(int(time.time()))
    message = f"host={host};timestamp={timestamp}"
    signature_b64 = sign_message(private_key, message.encode())
    if not signature_b64:
        return

    click.echo("\nSubmitting verification...")
    try:
        response = requests.post(
            f"{api_base_url}/verify_cell",
            json={
                "host": host,
                "signed_message": signature_b64,
                "message": message,
                "challenge_value": challenge_value,
                "domain": domain,
                "business_address": business_address,
                "registartion_country": registration_country,
                "tax_number": tax_number,
            },
            timeout=15
        )
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        click.echo(f"Error: {e}")
        return

    if str(result.get("success", "")).lower() == "true":
        click.echo(f"\nCell verified successfully for {domain}.")
        click.echo("You will be notified once the review is complete.")
    else:
        click.echo(f"\nVerification failed.")
        click.echo(f"Server response: {result.get('detail') or result}")


@click.command()
def delete_cell():
    """Deletes the locally stored credentials and requests cell deletion from the server."""

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
    click.echo(f"Requesting deletion of cell '{host}'...")
    url = f"{credentials['api_base_url']}/delete_cell"
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

            click.echo(f"Neuronum Cell '{host}' has been deleted and local credentials removed.")
        except Exception as e:
            click.echo(f"Warning:Warning: Successfully deleted cell on server, but failed to clean up all local files: {e}")
    else:
        click.echo(f"Error:Neuronum Cell '{host}' deletion failed on server.")


@click.command()
def disconnect_cell():
    """Removes local credentials without deleting the cell on the server."""

    # Check if any files exist to avoid unnecessary actions
    if not ENV_FILE.exists() and not PRIVATE_KEY_FILE.exists() and not PUBLIC_KEY_FILE.exists():
        click.echo("Info:No local Neuronum credentials found to disconnect.")
        return

    # 1. Confirmation
    confirm = click.confirm("Are you sure you want to disconnect? This will remove all local key files and the mnemonic, but your cell will remain active on the server.", default=False)
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
            click.echo("You can reconnect later using your 12-word mnemonic (via `connect-cell`).")
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

cli.add_command(create_cell)
cli.add_command(connect_cell)
cli.add_command(view_cell)
cli.add_command(verify_cell)
cli.add_command(delete_cell)
cli.add_command(disconnect_cell)
cli.add_command(start_mcp)

if __name__ == "__main__":
    cli()
