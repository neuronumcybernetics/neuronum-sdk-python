"""
Neuronum CLI - Command-line interface for Neuronum Cell, App, and Server management.
"""

import click
import questionary
from pathlib import Path
import requests
import asyncio
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
import json
import subprocess
import shutil
import os
import sys
import signal

# Configuration
NEURONUM_PATH = Path.home() / ".neuronum"
ENV_FILE = NEURONUM_PATH / ".env"
PUBLIC_KEY_FILE = NEURONUM_PATH / "public_key.pem"
PRIVATE_KEY_FILE = NEURONUM_PATH / "private_key.pem"
API_BASE_URL = "https://neuronum.net/api"

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

def save_credentials(host: str, mnemonic: str, pem_public: bytes, pem_private: bytes, cell_type: str):
    """Save cell credentials to .neuronum directory with secure file permissions."""
    import os
    try:
        NEURONUM_PATH.mkdir(parents=True, exist_ok=True)

        # Save environment configuration with sensitive data
        env_content = f"HOST={host}\nMNEMONIC=\"{mnemonic}\"\nTYPE={cell_type}\n"
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
        credentials['mnemonic'] = credentials.get("MNEMONIC")
        credentials['type'] = credentials.get("TYPE")
        
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

    # 1. Collect business info
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
            f"{API_BASE_URL}/send_verification_email",
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
            f"{API_BASE_URL}/verify_email",
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
    if save_credentials(host, mnemonic, pem_public, pem_private, "business"):
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

    # 1. Get and Validate Mnemonic
    mnemonic = questionary.text("Enter your 12-word BIP-39 mnemonic (space separated):").ask()

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
    url = f"{API_BASE_URL}/connect_cell"
    connect_data = {
        "public_key": public_key_pem_str,
        "signed_message": signature_b64,
        "message": message
    }

    try:
        response = requests.post(url, json=connect_data, timeout=10)
        response.raise_for_status()
        host = response.json().get("host")
        cell_type = response.json().get("cell_type")
    except requests.exceptions.RequestException as e:
        click.echo(f"Error:Error connecting to cell: {e}")
        return

    # 5. Save Credentials
    if host and cell_type:
        if save_credentials(host, mnemonic, pem_public, pem_private, cell_type):
            click.echo(f"Successfully connected to Cell '{host}'.")
        # Error saving credentials already echoed in helper
    else:
        click.echo("Error:Failed to retrieve host from server. Connection failed.")


@click.command()
def view_cell():
    """Displays the connection status and host name of the current cell."""
    
    credentials = load_credentials()
    
    if credentials:
        click.echo("\n--- Neuronum Cell Status ---")
        click.echo(f"Status:Connected")
        click.echo(f"Host:   {credentials['host']}")
        click.echo(f"Path:   {NEURONUM_PATH}")
        click.echo(f"Key Type: {credentials['private_key'].curve.name} (SECP256R1)")
        click.echo("----------------------------")


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
    url = f"{API_BASE_URL}/delete_cell"
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


# App Management Commands

@click.command()
def init_agent():
    credentials = load_credentials()
    if not credentials:
        return

    host = credentials['host']
    private_key = credentials['private_key']
    cell_type = credentials['type']

    if cell_type == "business":
        agent_type = questionary.select(
            "Select agent type:",
            choices=["Task Agent", "Personal Agent"]
        ).ask()
        if not agent_type:
            click.echo("Canceled.")
            return
        use_business = agent_type == "Task Agent"
    else:
        use_business = False

    if use_business:
        timestamp = str(int(time.time()))
        message = f"host={host};timestamp={timestamp}"
        signature_b64 = sign_message(private_key, message.encode())

        if not signature_b64:
            return

        try:
            response = requests.post(
                f"{API_BASE_URL}/init_agent",
                json={"host": host, "signed_message": signature_b64, "message": message},
                timeout=10
            )
            response.raise_for_status()
            agent_id = response.json().get("agent_id", False)
        except requests.exceptions.RequestException as e:
            click.echo(f"Error:Error communicating with the server: {e}")
            return

        agent_folder = "agent_" + agent_id
        project_path = Path(agent_folder)

        click.echo("Downloading boilerplate...")
        clone_result = subprocess.run(
            ["git", "clone", "https://github.com/neuronumcybernetics/agent-boilerplate.git", agent_folder],
            capture_output=True, text=True
        )
        if clone_result.returncode != 0:
            click.echo(f"Error:Failed to clone boilerplate: {clone_result.stderr.strip()}")
            return

        shutil.rmtree(project_path / ".git", ignore_errors=True)

        business_src = project_path / "task_agent"
        for f in business_src.iterdir():
            shutil.move(str(f), str(project_path / f.name))
        shutil.rmtree(str(business_src), ignore_errors=True)
        shutil.rmtree(str(project_path / "personal_agent"), ignore_errors=True)

        config_path = project_path / "agent.config"
        config_data = json.dumps({
            "agent_meta": {
                "agent_id": agent_id,
                "version": "1.0.0",
                "name": "Task Agent",
                "description": "An agent that helps you get tasks done by answering questions and delegating to specialized agents",
                "audience": "private",
                "logo": "https://neuronum.net/static/logo_new.png"
            },
            "skills": [
            {
                "handle": "get_answer",
                "description": "Submit a task or question and get an answer, with optional delegation to a specialized agent.",
                "examples": [
                    "Summarize the key points from this document.",
                    "Draft a follow-up email for a client meeting."
                ],
                "stream": False,
                "input_schema": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The user request"
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional background information"
                        }
                    },
                    "required": ["query"]
                }
            }
            ],
            "legals": {
                "terms": "https://url_to_your/legals",
                "privacy_policy": "https://url_to_your/legals"
            }
        }, indent=2)
        config_path.write_text(config_data + "\n")
        click.echo(f"Agent '{agent_id}' initialized!")

    else:
        agent_folder = "personal_agent"
        project_path = Path(agent_folder)

        click.echo("Downloading boilerplate...")
        clone_result = subprocess.run(
            ["git", "clone", "https://github.com/neuronumcybernetics/agent-boilerplate.git", agent_folder],
            capture_output=True, text=True
        )
        if clone_result.returncode != 0:
            click.echo(f"Error:Failed to clone boilerplate: {clone_result.stderr.strip()}")
            return

        shutil.rmtree(project_path / ".git", ignore_errors=True)

        personal_src = project_path / "personal_agent"
        for f in personal_src.iterdir():
            shutil.move(str(f), str(project_path / f.name))
        shutil.rmtree(str(personal_src), ignore_errors=True)
        shutil.rmtree(str(project_path / "task_agent"), ignore_errors=True)

        click.echo("Personal agent initialized!")


@click.command()
def update_agent():
    try:
        with open("agent.config", "r") as f:
            config_data = json.load(f)

        audience = config_data.get("agent_meta", {}).get("audience", "")
        agent_id = config_data.get("agent_meta", {}).get("agent_id", "")

    except FileNotFoundError as e:
        click.echo(f"Error: File not found - {e.filename}")
        return
    except click.ClickException as e:
        click.echo(e.format_message())
        return
    except Exception as e:
        click.echo(f"Error reading files: {e}")
        return

    asyncio.run(async_update_agent(config_data, agent_id, audience))


async def async_update_agent(config_data, agent_id: str, audience: str):
    """Update agent configuration on the Neuronum network."""
    credentials = load_credentials()
    if not credentials:
        return

    host = credentials['host']
    private_key = credentials['private_key']

    # Prepare signed message for API authentication
    timestamp = str(int(time.time()))
    message = f"host={host};timestamp={timestamp}"
    signature_b64 = sign_message(private_key, message.encode())

    if not signature_b64:
        return

    url = f"{API_BASE_URL}/update_agent"
    payload = {
        "host": host,
        "signed_message": signature_b64,
        "message": message,
        "agent_id": agent_id,
        "config": config_data,
        "audience": audience
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        response_data = response.json()
        
        if response_data.get("success"):
            agent_id = response_data.get("agent_id")
            message = response_data.get("message", "Agent updated!")
            click.echo(f"Agent '{agent_id}' updated successfully!")
        else:
            error_message = response_data.get("message", "Unknown error")
            click.echo(f"Error:Failed to update app: {error_message}")
            
    except requests.exceptions.RequestException as e:
        click.echo(f"Error:Error communicating with the server: {e}")
        return

                   

@click.command()
def delete_agent():
    try:
        with open("agent.config", "r") as f:
            config_data = json.load(f)

        agent_id = config_data.get("agent_meta", {}).get("agent_id", "")

    except FileNotFoundError as e:
        click.echo(f"Error: File not found - {e.filename}")
        return
    except click.ClickException as e:
        click.echo(e.format_message())
        return
    except Exception as e:
        click.echo(f"Error reading files: {e}")
        return

    # 1. Load Credentials
    credentials = load_credentials()
    if not credentials:
        # Error already echoed in helper
        return

    host = credentials['host']
    private_key = credentials['private_key']

    # Confirm deletion
    confirm = click.confirm(f"Are you sure you want to permanently delete your Neuronum Agent '{agent_id}'?", default=False)
    if not confirm:
        click.echo("Deletion canceled.")
        return

    # Prepare signed message for API authentication
    timestamp = str(int(time.time()))
    message = f"host={host};timestamp={timestamp}"
    signature_b64 = sign_message(private_key, message.encode())

    if not signature_b64:
        return

    # Send deletion request to API
    click.echo(f"Requesting deletion of Agent '{agent_id}'...")
    url = f"{API_BASE_URL}/delete_agent"
    payload = {
        "host": host,
        "signed_message": signature_b64,
        "message": message,
        "agent_id": agent_id
    }

    try:
        response = requests.delete(url, json=payload, timeout=10)
        response.raise_for_status()
        status = response.json().get("status", False)
        if status:
            click.echo(f"Agent '{agent_id}' has been deleted!")
    except requests.exceptions.RequestException as e:
        click.echo(f"Error:Error communicating with the server during deletion: {e}")
        return

# Server Management Commands

@click.command()
@click.option("-d", "--detach", is_flag=True, default=False, help="Run agent in background (daemon mode)")
def start_agent(detach):
    """Starts the agent in the current directory. Use -d to run in the background."""
    agent_path = Path("agent.py")
    if not agent_path.exists():
        click.echo("Error: agent.py not found. Run this command from inside your agent folder.")
        return

    if detach:
        pid_file = Path(".agent_pid")

        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)
                click.echo("Server is already running!")
                click.echo("View logs: tail -f agent.log")
                click.echo("To restart, first run: neuronum stop-agent")
                return
            except (OSError, ValueError, ProcessLookupError):
                pid_file.unlink(missing_ok=True)

        if Path("model.py").exists():
            click.echo("Checking model...")
            try:
                subprocess.run([sys.executable, "model.py"], check=True)
            except subprocess.CalledProcessError as e:
                click.echo(f"Error downloading model: {e}")
                return

        click.echo("Starting server in background...")
        try:
            process = subprocess.Popen(
                [sys.executable, "agent.py"],
                stdout=open("agent.log", "a"),
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
            pid_file.write_text(str(process.pid))
            click.echo(f"Server started (PID: {process.pid})")
            click.echo("View logs: tail -f agent.log")
            click.echo("Stop server: neuronum stop-agent")
        except Exception as e:
            click.echo(f"Error starting server: {e}")
    else:
        if Path("model.py").exists():
            click.echo("Checking model...")
            try:
                subprocess.run([sys.executable, "model.py"], check=True)
            except subprocess.CalledProcessError as e:
                click.echo(f"Error downloading model: {e}")
                return

        try:
            subprocess.run([sys.executable, "agent.py"])
        except KeyboardInterrupt:
            pass
        except Exception as e:
            click.echo(f"Error starting agent: {e}")


@click.command()
def stop_agent():
    """Stops the agent server in the current directory"""
    pid_file = Path(".agent_pid")

    if not pid_file.exists():
        click.echo("No running server found in this directory.")
        return

    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        click.echo(f"Server stopped (PID: {pid})")
    except ProcessLookupError:
        click.echo("Server process was not running.")
    except Exception as e:
        click.echo(f"Error stopping server: {e}")
    finally:
        pid_file.unlink(missing_ok=True)

# CLI Command Registration

cli.add_command(create_cell)
cli.add_command(connect_cell)
cli.add_command(view_cell)
cli.add_command(delete_cell)
cli.add_command(disconnect_cell)
cli.add_command(init_agent)
cli.add_command(update_agent)
cli.add_command(delete_agent)
cli.add_command(start_agent)
cli.add_command(stop_agent)

if __name__ == "__main__":
    cli()