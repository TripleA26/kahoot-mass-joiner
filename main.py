import aiohttp
import asyncio
import json
import random
import ssl
import time
from base64 import b64decode
import logging

PREFIX = "Triple"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

class GameNotFoundError(Exception):
    pass

def random_words(n=2):
    words = ["Yo", "Yes", "Awesome", "GG", "YAY"]
    return "_".join(random.sample(words, n))

def make_nickname():
    return f"{PREFIX}_{random_words(2)}"

def _do_xor(session_token: str, solution: str) -> str:
    decoded_token = b64decode(session_token).decode('utf-8', 'strict')
    sol_chars = [ord(s) for s in solution]
    sess_chars = [ord(s) for s in decoded_token]
    return "".join([chr(sess_chars[i] ^ sol_chars[i % len(sol_chars)]) for i in range(len(sess_chars))])

def decode(offset: int, message):
    decoded_message = ''
    
    for position, char in enumerate(message):
        decoded_char = chr((((ord(char) * position) + offset) % 77) + 48)
        decoded_message += decoded_char
    
    return decoded_message

def solve_challenge(session_token: str, text: str) -> str:
    text = text.replace('\t', '', -1).encode('ascii', 'ignore').decode('utf-8')
    offset: int = int(eval(text.split("offset = ")[1].split(";")[0]))
    input = text.split("this, '")[1].split("'")[0]
    solution = decode(offset, input)
    return _do_xor(session_token, solution)

def load_proxies(filename="proxies.txt"):
    try:
        with open(filename, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
        logger.info(f"Loaded {len(proxies)} proxies from {filename}")
        return proxies
    except FileNotFoundError:
        logger.warning(f"Proxy file {filename} not found, running without proxies")
        return []
    except Exception as e:
        logger.error(f"Error loading proxies: {e}")
        return []

def format_proxy(proxy):
    if not proxy:
        return None
    return f"http://{proxy}"

class KahootBot:
    def __init__(self, proxy=None):
        self.http_client = None
        self.game_pin = None
        self.ws = None
        self.client_id = None
        self.proxy = format_proxy(proxy) if proxy else None

    async def join_game(self, game_pin: int, username: str):
        logger.info(f"Joining game {game_pin} as {username}")
        self.http_client = aiohttp.ClientSession()
        
        try:
            # Get session token and challenge
            ts = str(int(time.time() * 1000))
            async with self.http_client.get(
                f"https://kahoot.it/reserve/session/{game_pin}/?{ts}",
                ssl=ssl_context,
                proxy=self.proxy
            ) as r:
                if r.status != 200:
                    raise GameNotFoundError(f"Game with pin {game_pin} not found (status: {r.status})")
                
                data = await r.json()
                session_token = r.headers.get('x-kahoot-session-token', '')
                
                if not session_token:
                    raise Exception("No session token found in headers")
                
                logger.debug(f"Session token: {session_token}")
                
                # Solve challenge
                session_id = solve_challenge(session_token, data["challenge"])
                logger.debug(f"Session ID: {session_id}")

                self.game_pin = game_pin
                success = await self._establish_connection(session_id, username)
                return success

        except Exception as e:
            logger.error(f"Error joining game: {e}")
            await self.close()
            return False

    async def _establish_connection(self, session_id: str, username: str):
        try:
            ws_url = f"wss://kahoot.it/cometd/{self.game_pin}/{session_id}"
            logger.debug(f"Connecting to WebSocket: {ws_url}")
            
            self.ws = await self.http_client.ws_connect(
                ws_url, 
                ssl=ssl_context,
                proxy=self.proxy
            )
            
            # Step 1: Handshake
            handshake_msg = [{
                "id": "1",
                "version": "1.0", 
                "minimumVersion": "1.0",
                "channel": "/meta/handshake",
                "supportedConnectionTypes": ["websocket"],
                "advice": {"timeout": 60000, "interval": 0},
                "ext": {"ack": True}
            }]
            await self.ws.send_str(json.dumps(handshake_msg))
            logger.debug("Sent handshake")
            
            # Wait for handshake response
            response = await self.ws.receive()
            if response.type != aiohttp.WSMsgType.TEXT:
                logger.error(f"Invalid handshake response type: {response.type}")
                return False
                
            handshake_data = json.loads(response.data)
            logger.debug(f"Handshake response: {handshake_data}")
            
            if not handshake_data or not handshake_data[0].get("successful"):
                logger.error("Handshake failed")
                return False
                
            self.client_id = handshake_data[0].get("clientId")
            logger.debug(f"Client ID: {self.client_id}")
            
            # Step 2: First connect
            connect_msg = [{
                "id": "2",
                "channel": "/meta/connect",
                "connectionType": "websocket",
                "clientId": self.client_id
            }]
            await self.ws.send_str(json.dumps(connect_msg))
            logger.debug("Sent first connect")
            
            # Wait for first connect response
            response = await self.ws.receive()
            if response.type != aiohttp.WSMsgType.TEXT:
                logger.error(f"Invalid connect response type: {response.type}")
                return False
                
            connect_data = json.loads(response.data)
            logger.debug(f"First connect response: {connect_data}")
            
            if not connect_data or not connect_data[0].get("successful"):
                logger.error("First connect failed")
                return False

            # Send login message
            login_msg = [{
                "id": "3",
                "channel": "/service/controller", 
                "data": {
                    "type": "login",
                    "gameid": str(self.game_pin),
                    "host": "kahoot.it", 
                    "name": username,
                    "content": "{}"
                },
                "clientId": self.client_id
            }]
            await self.ws.send_str(json.dumps(login_msg))
            logger.debug(f"Sent login message for {username}")
            
            # Wait for login response
            response = await self.ws.receive()
            if response.type != aiohttp.WSMsgType.TEXT:
                logger.error(f"Invalid login response type: {response.type}")
                return False
                
            login_data = json.loads(response.data)
            logger.debug(f"Login response: {login_data}")
            
            if not login_data or not login_data[0].get("successful"):
                logger.error("Login failed")
                return False

            # Send join message (this is what actually joins the game)
            join_msg = [{
                "id": "4",
                "channel": "/service/controller", 
                "data": {
                    "type": "message",
                    "gameid": str(self.game_pin),
                    "host": "kahoot.it",
                    "id": 16,
                    "content": '{"usingNamerator":false}'
                },
                "clientId": self.client_id
            }]
            await self.ws.send_str(json.dumps(join_msg))
            logger.debug(f"Sent join message for {username}")
            
            # Wait for join response
            response = await self.ws.receive()
            if response.type == aiohttp.WSMsgType.TEXT:
                join_data = json.loads(response.data)
                logger.debug(f"Join response: {join_data}")
                
                # Check if join was successful
                if (join_data and len(join_data) > 0 and 
                    join_data[0].get('channel') == '/service/controller' and
                    join_data[0].get('successful')):
                    logger.info(f"Successfully joined as {username}")
                    return True
            
            logger.warning(f"Join confirmation not clear for {username}")
            return False
            
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            return False

    async def close(self):
        if self.ws:
            await self.ws.close()
        if self.http_client:
            await self.http_client.close()

async def run_bot(pin, username, proxy=None):
    bot = KahootBot(proxy=proxy)
    try:
        success = await bot.join_game(pin, username)
        # Keep successful connections alive for a bit to ensure join is processed
        if success:
            await asyncio.sleep(1)
        return success
    except Exception as e:
        logger.error(f"Bot error: {e}")
        return False
    finally:
        await bot.close()

async def run_batch(pin, num_bots, proxies=None):
    tasks = []
    
    # Load proxies if not provided
    if proxies is None:
        proxies = load_proxies()
    
    for i in range(num_bots):
        username = make_nickname()
        
        proxy = proxies[i % len(proxies)] if proxies else None
        
        task = asyncio.create_task(run_bot(pin, username, proxy))
        tasks.append(task)
        
        # Add delay between bot connections to avoid rate limiting
        await asyncio.sleep(0.3)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    success_count = 0
    for result in results:
        if isinstance(result, bool) and result:
            success_count += 1
        elif isinstance(result, Exception):
            logger.error(f"Bot exception: {result}")
    
    return success_count, num_bots

if __name__ == "__main__":
    pin = int(input("Enter Kahoot PIN: "))
    num_bots = int(input("Enter number of bots: "))
    
    proxies = load_proxies()
    
    if proxies:
        print(f"Using {len(proxies)} proxies from proxies.txt")
    else:
        print("Running without proxies")
    
    print(f"Starting {num_bots} bots...")
    success_count, total_count = asyncio.run(run_batch(pin, num_bots, proxies))
    print(f"Successfully joined: {success_count}/{total_count}")
