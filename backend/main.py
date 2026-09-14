import os
import sys

# Ensure backend root is on Python module search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
