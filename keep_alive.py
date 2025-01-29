from flask import Flask
from threading import Thread
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    try:
        logger.info("Starting keep-alive server on port 8080")
        app.run(host='0.0.0.0', port=8080)
    except Exception as e:
        logger.error(f"Error starting keep-alive server: {e}")
        raise

def keep_alive():
    try:
        logger.info("Initializing keep-alive thread")
        t = Thread(target=run)
        t.daemon = True  # Make thread daemon so it exits when main thread exits
        t.start()
        logger.info("Keep-alive thread started successfully")
    except Exception as e:
        logger.error(f"Error in keep_alive: {e}")
        raise
