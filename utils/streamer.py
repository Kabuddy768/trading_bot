import asyncio
import json
import websockets
from typing import Callable, List
from utils.logger import logger

class BinanceStreamer:
    """
    Subscribes to Binance WebSockets for a list of symbols and
    fires a callback whenever a new ticker (price update) arrives.
    """
    def __init__(self, symbols: List[str], on_tick: Callable[[str, float], None]):
        self.symbols = [s.replace('/', '').lower() for s in symbols]
        self.on_tick = on_tick
        self.ws_url = "wss://stream.binance.com:9443/ws"
        self._running = False

    async def start(self):
        self._running = True
        
        # Create subscription payload
        # "miniTicker" is faster and lighter than full "ticker"
        streams = [f"{symbol}@miniTicker" for symbol in self.symbols]
        payload = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": 1
        }

        while self._running:
            try:
                # connect
                async with websockets.connect(self.ws_url) as ws:
                    logger.info(f"WebSocket connected. Subscribing to: {self.symbols}")
                    await ws.send(json.dumps(payload))
                    
                    while self._running:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        
                        # Handle actual ticker events
                        if 'e' in data and data['e'] == '24hrMiniTicker':
                            sym_raw = data['s']  # e.g., 'BTCUSDT'
                            
                            # Format back to 'BTC/USDT' for our internal logic
                            # (Assuming all pairs end in USDT for simplicity based on watchlist)
                            if sym_raw.endswith("USDT"):
                                sym_formatted = sym_raw[:-4] + "/USDT"
                            else:
                                sym_formatted = sym_raw # Fallback
                                
                            last_price = float(data['c']) # close is the last price
                            
                            # Fire callback
                            if asyncio.iscoroutinefunction(self.on_tick):
                                await self.on_tick(sym_formatted, last_price)
                            else:
                                self.on_tick(sym_formatted, last_price)
                                
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket disconnected. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await asyncio.sleep(5)

    def stop(self):
        self._running = False
        logger.info("WebSocket stopping...")
