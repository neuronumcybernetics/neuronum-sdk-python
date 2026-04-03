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
    """Neuronum CLI App for Community Cell management."""
    pass

# Cell Management Commands

@click.command()
def create_cell():
    """Creates a new Community Cell with a freshly generated 12-word mnemonic."""

    click.echo("Creating a new Community Cell...")
    click.echo("Warning:Save your mnemonic in a secure location! You'll need it to access your Cell.\n")

    # 1. Generate a new 12-word mnemonic
    mnemonic_obj = Bip39MnemonicGenerator().FromWordsNumber(12)
    mnemonic = str(mnemonic_obj)

    # 2. Derive keys from the mnemonic
    private_key, public_key, pem_private, pem_public = derive_keys_from_mnemonic(mnemonic)
    if not private_key:
        return

    # 3. Call API to create the cell
    click.echo("Registering new Cell on Neuronum network...")
    url = f"{API_BASE_URL}/create_community_cell"

    payload = {
        "public_key": pem_public.decode("utf-8")
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        response_data = response.json()

        if response_data.get("success") == "True" and response_data.get("host"):
            host = response_data.get("host")
            cell_type = "community"  # New cells are community type

            # 5. Save credentials locally
            if save_credentials(host, mnemonic, pem_public, pem_private, cell_type):
                click.echo(f"\nCommunity Cell created successfully!")
                click.echo(f"Host: {host}")
                click.echo(f"\nYour 12-word mnemonic (SAVE THIS SECURELY):")
                click.echo(f"   {mnemonic}")
                click.echo(f"\nNote:This mnemonic is the ONLY way to recover your Cell.")
                click.echo(f"   Write it down and store it in a safe place!\n")
            else:
                click.echo("Warning:Cell created on server but failed to save locally.")
                click.echo(f"Your mnemonic: {mnemonic}")
        else:
            error_msg = response_data.get("message", "Unknown error")
            click.echo(f"Error:Failed to create Cell: {error_msg}")

    except requests.exceptions.RequestException as e:
        click.echo(f"Error:Error communicating with server: {e}")
        return


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
            click.echo(f"Successfully connected to Community Cell '{host}'.")
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
def init_app():
    name = click.prompt("Enter a App Name").strip()
    descr = click.prompt("Enter a brief App description").strip()
    asyncio.run(async_init_app(descr, name))

async def async_init_app(descr, name):
    """Initialize a new app by registering it with the Neuronum network and creating local files."""
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

    url = f"{API_BASE_URL}/init_app"
    payload = {
        "host": host,
        "signed_message": signature_b64,
        "message": message,
        "name": name,
        "descr": descr
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        app_id = response.json().get("app_id", False)
    except requests.exceptions.RequestException as e:
        click.echo(f"Error:Error communicating with the server: {e}")
        return
    
    app_folder = name + "_" + app_id
    project_path = Path(app_folder)
    project_path.mkdir(exist_ok=True)
                                                                                                           
    app_path = project_path / "app.py"
    app_path.write_text('''\
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import asyncio
import json
import sys
from neuronum import Cell
from jinja2 import Environment, FileSystemLoader
import logging


# Logging Setup
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler("app.log", mode='a')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

env = Environment(loader=FileSystemLoader(os.path.dirname(os.path.abspath(__file__))))

# Load app config
with open("app.config", "r") as f:
    app_config = json.load(f)


# Grocery List Database
grocery_list = [
    {"id": 1, "item": "Milk", "qty": "1L"},
    {"id": 2, "item": "Eggs", "qty": "12"},
    {"id": 3, "item": "Bread", "qty": "1"},
    {"id": 4, "item": "Bananas", "qty": "6"},
    {"id": 5, "item": "Olive Oil", "qty": "500ml"},
]
next_id = 6

# Ratings
ratings = {"up": 0, "down": 0}

async def setup_cell_connection():
    """Establish connection as Neuronum Cell and return cell instance"""
    cell = Cell()

    if not cell.env.get("HOST"):
        logging.error("Error: No HOST found in Cell credentials. Please run 'neuronum create-cell' or 'neuronum connect-cell' first.")
        await cell.close()
        sys.exit(1)

    logging.info(f"Connected to Cell: {cell.env.get('HOST')}")
    return cell

# Message Handlers

async def send_cell_response(cell, transmitter_id: str, data: dict, public_key: str):
    """Send response back through cell"""
    await cell.tx_response(
        transmitter_id=transmitter_id,
        data=data,
        client_public_key_str=public_key
    )


# do not remove handle_get_index
async def handle_get_index(cell, transmitter: dict):
    """Handle getting the index/welcome page for operators"""
    data = transmitter.get("data", {})
    logging.info("Fetching index page")

    # Load and render template
    template = env.get_template("index.html")
    html_content = template.render()

    await send_cell_response(
        cell,
        transmitter.get("transmitter_id"),
        {"html": html_content},
        data.get("public_key", "")
    )

async def handle_get_page(cell, transmitter: dict):
    """Handle getting a page by name"""
    data = transmitter.get("data", {})
    page = data.get("page", "")
    logging.info(f"Fetching page: {page}")

    # Prevent path traversal — only allow .html files in the server directory
    if not page.endswith(".html") or "/" in page or "\\\\" in page or ".." in page:
        logging.warning(f"Rejected page request: {page}")
        await send_cell_response(
            cell,
            transmitter.get("transmitter_id"),
            {"json": "Invalid page name."},
            data.get("public_key", "")
        )
        return

    # Load and render template
    template = env.get_template(page)
    html_content = template.render()

    await send_cell_response(
        cell,
        transmitter.get("transmitter_id"),
        {"html": html_content},
        data.get("public_key", "")
    )

async def handle_get_groceries(cell, transmitter: dict):
    """Return the current grocery list"""
    data = transmitter.get("data", {})
    logging.info("Fetching grocery list")

    await send_cell_response(
        cell,
        transmitter.get("transmitter_id"),
        {"json": {"groceries": grocery_list}},
        data.get("public_key", "")
    )

async def handle_add_grocery(cell, transmitter: dict):
    """Add an item to the grocery list and return updated list"""
    global next_id
    data = transmitter.get("data", {})
    item = data.get("item", "")
    qty = data.get("qty", "1")

    if not item:
        logging.warning("Add grocery: no item provided")
        return

    grocery_list.append({"id": next_id, "item": item, "qty": qty})
    logging.info(f"Added grocery item: {item} (qty: {qty}, id: {next_id})")
    next_id += 1

    await send_cell_response(
        cell,
        transmitter.get("transmitter_id"),
        {"json": {"groceries": grocery_list}},
        data.get("public_key", "")
    )

async def handle_remove_grocery(cell, transmitter: dict):
    """Remove an item from the grocery list and return updated list"""
    global grocery_list
    data = transmitter.get("data", {})
    item_id = data.get("id")

    if item_id is None:
        logging.warning("Remove grocery: no id provided")
        return

    grocery_list = [g for g in grocery_list if g["id"] != item_id]
    logging.info(f"Removed grocery item with id: {item_id}")

    await send_cell_response(
        cell,
        transmitter.get("transmitter_id"),
        {"json": {"groceries": grocery_list}},
        data.get("public_key", "")
    )

async def handle_rate(cell, transmitter: dict):
    """Handle a rating (fire and forget via stream)"""
    data = transmitter.get("data", {})
    vote = data.get("vote", "")

    if vote in ("up", "down"):
        ratings[vote] += 1
        logging.info(f"Rating received: {vote} (total: up={ratings['up']}, down={ratings['down']})")


def is_authorized(operator: str, server_host: str) -> bool:
    """Check if operator is authorized based on app.config audience setting.

    Audience modes:
        - "private": only the host cell itself can access
        - "public": any cell can access
        - "cell_id, cell_id, ...": only the listed cells can access
    """
    audience = app_config.get("app_meta", {}).get("audience", "private")

    if audience == "public":
        return True

    if audience == "private":
        return operator == server_host

    # Audience is a comma-separated list of allowed cells
    allowed_cells = [c.strip() for c in audience.split(",")]
    return operator in allowed_cells


async def route_message(cell, transmitter: dict):
    """Route incoming messages to appropriate handlers with access control"""
    try:
        data = transmitter.get("data", {})
        message_type = data.get("type", None)
        operator = transmitter.get("operator", "")

        # Get the server's cell_id to determine authorized cells
        server_host = cell.host or cell.env.get("HOST", "")

        # Check if operator is authorized
        if not is_authorized(operator, server_host):
            logging.warning(f"Access denied: '{operator}' is not authorized (audience: {app_config.get('app_meta', {}).get('audience', 'private')})")
            await send_cell_response(
                cell,
                transmitter.get("transmitter_id"),
                {"json": "Access denied: This endpoint is not available."},
                data.get("public_key", "")
            )
            return

        handlers = {
            "get_index": lambda: handle_get_index(cell, transmitter),
            "get_page": lambda: handle_get_page(cell, transmitter),
            "get_groceries": lambda: handle_get_groceries(cell, transmitter),
            "add_grocery": lambda: handle_add_grocery(cell, transmitter),
            "remove_grocery": lambda: handle_remove_grocery(cell, transmitter),
            "rate": lambda: handle_rate(cell, transmitter),
        }

        handler = handlers.get(message_type)
        if handler:
            await handler()
        else:
            logging.warning(f"Unknown message type: {message_type}")
    except Exception as e:
        logging.error(f"Error routing message: {e}")
        import traceback
        logging.error(traceback.format_exc())

def _task_done_callback(task: asyncio.Task):
    """Log unhandled exceptions from fire-and-forget tasks"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logging.error(f"Unhandled exception in message task: {exc}", exc_info=exc)

async def process_cell_messages(cell):
    """Main message processing loop for cell — dispatches messages concurrently"""
    async for transmitter in cell.sync():

        task = asyncio.create_task(route_message(cell, transmitter))
        task.add_done_callback(_task_done_callback)

# Main Function

async def server_main():
    """Main server logic"""
    cell = None
    try:
        logging.info("Connecting to Neuronum network...")
        cell = await setup_cell_connection()
        logging.info(f"Connected as Cell: {cell.env.get('HOST') or cell.host}")

        await process_cell_messages(cell)
    finally:
        if cell is not None:
            try:
                await cell.close()
                logging.info("Cell connection closed successfully")
            except Exception as e:
                logging.error(f"Error closing cell connection: {e}")

async def main():
    """Main entry point"""
    await server_main()


if __name__ == "__main__":
    asyncio.run(main())
''')
    
    config_path = project_path / "app.config"
    config_data = json.dumps({
        "app_meta": {
            "app_id": app_id,
            "version": "1.0.0",
            "name": name,
            "description": descr,
            "audience": "private",
            "logo": "https://neuronum.net/static/logo_new.png"
        },
        "legals": {
            "terms": "https://neuronum.net/legals",
            "privacy_policy": "https://neuronum.net/legals"
        }
    }, indent=2)
    config_path.write_text(config_data + "\n")
    
    index_path = project_path / "index.html"
    index_path.write_text('''\
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Neuronum Server</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: #000;
            color: #fff;
        }
        .container {
            text-align: center;
            padding: 2rem;
            max-width: 600px;
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        .logo {
            max-width: 80px;
        }
        h1 {
            font-size: 2rem;
            margin-bottom: 1rem;
        }
        .tagline {
            font-size: 1.1rem;
            opacity: 0.85;
            line-height: 1.6;
            margin-bottom: 2rem;
        }
        .links {
            display: flex;
            justify-content: center;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .links a {
            color: #fff;
            text-decoration: none;
            padding: 0.6rem 1.2rem;
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 6px;
            transition: background 0.2s, border-color 0.2s;
        }
        .links a:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.5);
        }
        .app-btn {
            display: inline-block;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.25);
            border-radius: 8px;
            color: #fff;
            padding: 0.8rem 2rem;
            font-size: 1rem;
            cursor: pointer;
            font-family: inherit;
            transition: background 0.2s, border-color 0.2s;
            margin-bottom: 1rem;
        }
        .app-btn:hover {
            background: rgba(255, 255, 255, 0.18);
            border-color: rgba(255, 255, 255, 0.4);
        }
        .footer {
            font-size: 0.7rem;
            color: rgba(255, 255, 255, 0.25);
            padding: 1.5rem 2rem;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <img src="https://neuronum.net/static/logo_new.png" alt="Neuronum" class="logo">
        <h1>Neuronum Server</h1>
        <p class="tagline">Designed to build & deploy secure applications within minutes.<br> Self-hosted. Open source. E2E encrypted.</p>
        <div class="links">
            <a href="https://neuronum.net/docs" target="_blank">Docs</a>
            <a href="https://github.com/neuronumcybernetics/neuronum-server" target="_blank">GitHub</a>
        </div>
        <button class="app-btn" id="open-groceries">Open Demo (demo.html)</button>
    </div>

    <div class="footer">Neuronum Cybernetics UG - Steinerne Furt 72 86167 Augsburg - welcome@neuronum.net</div>

    <script>
        const api = window.parent.pywebview ? window.parent.pywebview.api : null;

        document.getElementById('open-groceries').addEventListener('click', async () => {
            if (!api) return;
            try {
                await api.console_activate_tx(
                    JSON.stringify({ type: 'get_page', page: 'demo.html' })
                );
            } catch (e) { console.error(e); }
        });
    </script>
</body>
</html>
''')
    
    demo_path = project_path / "demo.html"
    demo_path.write_text('''\
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Grocery List</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: #0a0a0a;
            color: #d0d0d0;
        }
        .page {
            width: 100%;
            max-width: 440px;
            padding: 2rem 1.5rem;
        }
        .top-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1.5rem;
        }
        .back-btn {
            background: none;
            border: 1px solid #2a2a2a;
            border-radius: 5px;
            color: #888;
            padding: 0.35rem 0.7rem;
            cursor: pointer;
            font-size: 0.78rem;
            font-family: inherit;
        }
        .back-btn:hover { border-color: #444; color: #bbb; }
        h1 {
            font-size: 1.2rem;
            font-weight: 600;
            margin: 0;
            color: #e0e0e0;
        }
        .method-tag {
            font-size: 0.55rem;
            padding: 0.15rem 0.4rem;
            border-radius: 3px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.4px;
        }
        .tag-tx { background: #1a1a1a; color: #999; border: 1px solid #2a2a2a; }
        .tag-stream { background: #1a1a1a; color: #999; border: 1px solid #2a2a2a; }

        /* Load button */
        .load-btn {
            width: 100%;
            background: #111;
            border: 1px solid #2a2a2a;
            border-radius: 6px;
            color: #aaa;
            padding: 0.55rem;
            cursor: pointer;
            font-size: 0.82rem;
            font-family: inherit;
            margin-bottom: 1rem;
        }
        .load-btn:hover { border-color: #444; color: #ccc; }

        /* Grocery list */
        .grocery-list {
            display: flex;
            flex-direction: column;
            gap: 0.3rem;
            margin-bottom: 1.2rem;
        }
        .grocery-item {
            display: flex;
            align-items: center;
            gap: 0.6rem;
            padding: 0.5rem 0.7rem;
            background: #111;
            border: 1px solid #1e1e1e;
            border-radius: 5px;
        }
        .grocery-name { flex: 1; font-size: 0.85rem; color: #ccc; }
        .grocery-qty {
            font-size: 0.78rem;
            color: #555;
            min-width: 36px;
            text-align: right;
        }
        .remove-btn {
            background: none;
            border: none;
            color: #555;
            cursor: pointer;
            font-size: 0.85rem;
            padding: 0.15rem 0.35rem;
            border-radius: 3px;
        }
        .remove-btn:hover { color: #c66; }
        .empty-msg {
            text-align: center;
            color: #444;
            font-size: 0.82rem;
            padding: 0.8rem;
        }

        /* Add form */
        .add-form {
            display: flex;
            gap: 0.4rem;
        }
        .add-form input {
            flex: 1;
            background: #111;
            border: 1px solid #2a2a2a;
            border-radius: 5px;
            padding: 0.45rem 0.6rem;
            color: #ccc;
            font-size: 0.82rem;
            font-family: inherit;
        }
        .add-form input::placeholder { color: #444; }
        .add-form input:focus { outline: none; border-color: #444; }
        .add-form .qty-input { max-width: 60px; }
        .add-btn {
            background: #111;
            border: 1px solid #2a2a2a;
            border-radius: 5px;
            color: #aaa;
            padding: 0.45rem 0.8rem;
            cursor: pointer;
            font-size: 0.82rem;
            font-family: inherit;
        }
        .add-btn:hover { border-color: #444; color: #ccc; }

        /* Rating */
        .rating {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.6rem;
            margin-top: 1.5rem;
            padding-top: 1.2rem;
            border-top: 1px solid #1a1a1a;
        }
        .rating-label {
            font-size: 0.75rem;
            color: #555;
        }
        .rate-btn {
            background: #111;
            border: 1px solid #2a2a2a;
            border-radius: 5px;
            color: #777;
            padding: 0.35rem 0.7rem;
            cursor: pointer;
            font-size: 0.9rem;
            font-family: inherit;
        }
        .rate-btn:hover { border-color: #444; color: #ccc; }
        .rate-btn.voted { border-color: #444; color: #ccc; }
    </style>
</head>
<body>
    <div class="page">
        <div class="top-bar">
            <button class="back-btn" id="back-btn">Back</button>
            <h1>Grocery List</h1>
        </div>

        <button class="load-btn" id="load-btn">
            Load Groceries <span class="method-tag tag-tx">activate_tx</span>
        </button>

        <div class="grocery-list" id="grocery-list">
            <div class="empty-msg">Press "Load Groceries" to fetch your list</div>
        </div>

        <div class="add-form">
            <input type="text" id="item-input" placeholder="Item name">
            <input type="text" id="qty-input" class="qty-input" placeholder="Qty">
            <button class="add-btn" id="add-btn">Add <span class="method-tag tag-tx">activate_tx</span></button>
        </div>

        <div class="rating">
            <span class="rating-label">Rate this app</span>
            <button class="rate-btn" id="rate-up"><i class="fa-regular fa-thumbs-up"></i></button>
            <button class="rate-btn" id="rate-down"><i class="fa-regular fa-thumbs-down"></i></button>
            <span class="method-tag tag-stream">stream</span>
        </div>
    </div>

    <script>
        const api = window.parent.pywebview ? window.parent.pywebview.api : null;
        const groceryList = document.getElementById('grocery-list');

        function renderGroceries(items) {
            if (!items || items.length === 0) {
                groceryList.innerHTML = '<div class="empty-msg">No items in your grocery list</div>';
                return;
            }
            groceryList.innerHTML = items.map(g => `
                <div class="grocery-item" data-id="${g.id}">
                    <span class="grocery-name">${g.item}</span>
                    <span class="grocery-qty">${g.qty}</span>
                    <button class="remove-btn" data-id="${g.id}">x</button>
                </div>
            `).join('');

            groceryList.querySelectorAll('.remove-btn').forEach(btn => {
                btn.addEventListener('click', () => removeGrocery(parseInt(btn.dataset.id)));
            });
        }

        document.getElementById('back-btn').addEventListener('click', async () => {
            if (!api) return;
            try {
                await api.console_activate_tx(
                    JSON.stringify({ type: 'get_index' })
                );
            } catch (e) { console.error(e); }
        });

        document.getElementById('load-btn').addEventListener('click', async () => {
            if (!api) return;
            try {
                const result = await api.console_activate_tx(
                    JSON.stringify({ type: 'get_groceries' })
                );
                handleTxResult(result);
            } catch (e) { console.error(e); }
        });

        function handleTxResult(result) {
            if (!result) return;
            const parsed = typeof result === 'string' ? JSON.parse(result) : result;
            const data = parsed.json || parsed;
            const groceries = data.groceries || data;
            if (Array.isArray(groceries)) {
                renderGroceries(groceries);
            }
        }

        document.getElementById('add-btn').addEventListener('click', async () => {
            const itemInput = document.getElementById('item-input');
            const qtyInput = document.getElementById('qty-input');
            const item = itemInput.value.trim();
            const qty = qtyInput.value.trim() || '1';
            if (!item) return;

            if (api) {
                try {
                    const result = await api.console_activate_tx(
                        JSON.stringify({ type: 'add_grocery', item: item, qty: qty })
                    );
                    handleTxResult(result);
                    itemInput.value = '';
                    qtyInput.value = '';
                } catch (e) { console.error(e); }
            }
        });

        document.getElementById('item-input').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') document.getElementById('add-btn').click();
        });

        async function removeGrocery(id) {
            if (!api) return;
            try {
                const result = await api.console_activate_tx(
                    JSON.stringify({ type: 'remove_grocery', id: id })
                );
                handleTxResult(result);
            } catch (e) { console.error(e); }
        }

        // Rating via stream (fire and forget)
        document.getElementById('rate-up').addEventListener('click', () => {
            if (!api) return;
            api.console_stream(JSON.stringify({ type: 'rate', vote: 'up' }));
            document.getElementById('rate-up').classList.add('voted');
            document.getElementById('rate-down').classList.remove('voted');
        });

        document.getElementById('rate-down').addEventListener('click', () => {
            if (!api) return;
            api.console_stream(JSON.stringify({ type: 'rate', vote: 'down' }));
            document.getElementById('rate-down').classList.add('voted');
            document.getElementById('rate-up').classList.remove('voted');
        });
    </script>
</body>
</html>
''')
    
    click.echo(f"Neuronum App '{app_id}' initialized!")


@click.command()
def update_app():
    try:
        with open("app.config", "r") as f:
            config_data = json.load(f)

        audience = config_data.get("app_meta", {}).get("audience", "")
        app_id = config_data.get("app_meta", {}).get("app_id", "")

    except FileNotFoundError as e:
        click.echo(f"Error: File not found - {e.filename}")
        return
    except click.ClickException as e:
        click.echo(e.format_message())
        return
    except Exception as e:
        click.echo(f"Error reading files: {e}")
        return

    asyncio.run(async_update_app(config_data, app_id, audience))


async def async_update_app(config_data, app_id: str, audience: str):
    """Update app configuration and script on the Neuronum network."""
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

    url = f"{API_BASE_URL}/update_app"
    payload = {
        "host": host,
        "signed_message": signature_b64,
        "message": message,
        "app_id": app_id,
        "config": config_data,
        "audience": audience
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        response_data = response.json()
        
        if response_data.get("success"):
            app_id = response_data.get("app_id")
            message = response_data.get("message", "App updated!")
            click.echo(f"App '{app_id}' updated successfully!")
        else:
            error_message = response_data.get("message", "Unknown error")
            click.echo(f"Error:Failed to update app: {error_message}")
            
    except requests.exceptions.RequestException as e:
        click.echo(f"Error:Error communicating with the server: {e}")
        return

                   

@click.command()
def delete_app():
    try:
        with open("app.config", "r") as f:
            config_data = json.load(f)

        app_id = config_data.get("app_meta", {}).get("app_id", "")

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
    confirm = click.confirm(f"Are you sure you want to permanently delete your Neuronum App '{app_id}'?", default=False)
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
    click.echo(f"Requesting deletion of app '{app_id}'...")
    url = f"{API_BASE_URL}/delete_app"
    payload = {
        "host": host,
        "signed_message": signature_b64,
        "message": message,
        "app_id": app_id
    }

    try:
        response = requests.delete(url, json=payload, timeout=10)
        response.raise_for_status()
        status = response.json().get("status", False)
        if status:
            click.echo(f"Neuronum App '{app_id}' has been deleted!")
    except requests.exceptions.RequestException as e:
        click.echo(f"Error:Error communicating with the server during deletion: {e}")
        return

# Server Management Commands

@click.command()
def start_server():
    """Starts the app server in the current directory"""
    app_path = Path("app.py")
    if not app_path.exists():
        click.echo("Error: app.py not found. Run this command from inside your app folder.")
        return

    pid_file = Path(".server_pid")

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            click.echo("Server is already running!")
            click.echo("View logs: tail -f app.log")
            click.echo("To restart, first run: neuronum stop-server")
            return
        except (OSError, ValueError, ProcessLookupError):
            pid_file.unlink(missing_ok=True)

    click.echo("Starting server...")
    try:
        process = subprocess.Popen(
            [sys.executable, "app.py"],
            stdout=open("app.log", "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        pid_file.write_text(str(process.pid))
        click.echo(f"Server started (PID: {process.pid})")
        click.echo("View logs: tail -f app.log")
        click.echo("Stop server: neuronum stop-server")
    except Exception as e:
        click.echo(f"Error starting server: {e}")


@click.command()
def stop_server():
    """Stops the app server in the current directory"""
    pid_file = Path(".server_pid")

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
cli.add_command(init_app)
cli.add_command(update_app)
cli.add_command(delete_app)
cli.add_command(start_server)
cli.add_command(stop_server)

if __name__ == "__main__":
    cli()