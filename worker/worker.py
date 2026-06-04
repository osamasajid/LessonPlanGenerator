import os
import sys
from dotenv import load_dotenv

# Ensure the project root is in the Python search path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.telemetry import setup_telemetry, instrument_celery
from worker.celery_app import celery_app

# Initialize OpenTelemetry and instrument Celery prior to runner initialization
setup_telemetry()
instrument_celery()

if __name__ == "__main__":
    print("Starting Celery worker...")
    
    # Configure arguments for Celery command-line execution
    # First argument must be the command 'worker'
    argv = ["worker", "--loglevel=info"]
    
    # On Windows, use the 'solo' pool to prevent multiprocessing fork errors.
    # On Linux/Docker, run with default prefork pool for high-performance concurrency.
    if sys.platform.startswith("win"):
        print("Windows detected: Using solo pool (-P solo)")
        argv.extend(["-P", "solo"])
    else:
        print("Unix/Docker detected: Using default concurrent pool")
        
    celery_app.start(argv=argv)
