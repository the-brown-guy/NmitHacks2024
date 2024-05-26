import json
import asyncio
from web3 import Web3
import websockets
import pygame
from gtts import gTTS
from io import BytesIO
from collections import deque

# Initialize pygame mixer for text-to-speech
pygame.mixer.init()

# Network details
networks = {
    'sepolia': {
        'websocket': 'wss://sepolia.infura.io/ws/v3/<key>',
        'address': '', #add address
        'currency': 'Ether'
    },
    'amoy': {
        'websocket': 'wss://polygon-amoy.infura.io/ws/v3/<key>',
        'address': '', #add address
        'currency': 'Matic'
    }
}

# Initialize web3 instances
web3_instances = {
    'sepolia': Web3(Web3.WebsocketProvider(networks['sepolia']['websocket'])),
    'amoy': Web3(Web3.WebsocketProvider(networks['amoy']['websocket']))
}

def play_audio_notification(amount, currency):
    """Function to convert text to speech and play the notification"""
    rounded_amount = round(amount, 4)
    text = f'Payment received: {rounded_amount} {currency}'
    tts = gTTS(text, lang='en', slow=False)
    audio_stream = BytesIO()
    tts.write_to_fp(audio_stream)
    audio_stream.seek(0)
    pygame.mixer.music.load(audio_stream, "mp3")
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        continue

async def fetch_transaction(web3, tx_hash, retries=15, delay=20):
    """Fetch transaction details with retries"""
    for attempt in range(retries):
        try:
            tx = web3.eth.get_transaction(tx_hash)
            if tx:
                return tx
            else:
                print(f"Transaction with hash '{tx_hash}' not found in attempt {attempt + 1}. Retrying...")
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}. Retrying...")
        await asyncio.sleep(delay)
    raise Exception(f"Transaction with hash: '{tx_hash}' not found after {retries} attempts")

async def handle_transaction(network_name, tx_hash):
    """Fetch transaction details and notify"""
    web3 = web3_instances[network_name]
    try:
        tx = await fetch_transaction(web3, tx_hash)
        to_address = tx['to']
        value = web3.from_wei(tx['value'], 'ether')
        currency = networks[network_name]['currency']

        if to_address and to_address.lower() == networks[network_name]['address'].lower():
            print(f"Received {value} {currency} on {network_name}")
            play_audio_notification(value, currency)
    except Exception as e:
        print(f"Error handling transaction {tx_hash}: {e}. Retrying...")

async def listen_for_transactions(network_name, transaction_queue):
    """Listen for new transactions on the specified network"""
    websocket_url = networks[network_name]['websocket']
    while True:
        try:
            async with websockets.connect(websocket_url) as websocket:
                subscription_params = {
                    "jsonrpc": "2.0",
                    "method": "eth_subscribe",
                    "params": ["newPendingTransactions"],
                    "id": 1
                }
                await websocket.send(json.dumps(subscription_params))

                while True:
                    response = await websocket.recv()
                    response = json.loads(response)
                    if 'params' in response:
                        tx_hash = response['params']['result']
                        transaction_queue.append((network_name, tx_hash))
        except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK, websockets.InvalidStatusCode) as e:
            print(f"Error in {network_name} listener: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Unexpected error in {network_name} listener: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

async def process_transactions(transaction_queue):
    """Process transactions from the queue"""
    while True:
        if transaction_queue:
            network_name, tx_hash = transaction_queue.popleft()
            asyncio.create_task(handle_transaction(network_name, tx_hash))
        await asyncio.sleep(1)

async def main():
    transaction_queue = deque()
    listeners = [
        listen_for_transactions('sepolia', transaction_queue),
        listen_for_transactions('amoy', transaction_queue)
    ]
    processors = process_transactions(transaction_queue)
    await asyncio.gather(*listeners, processors)

if __name__ == "__main__":
    asyncio.run(main())
