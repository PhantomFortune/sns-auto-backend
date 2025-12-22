"""
Run script for the backend server

Usage (from backend directory):
    ./venv/Scripts/python.exe run.py
    
Or with uvicorn directly:
    ./venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""
import os
import sys

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

