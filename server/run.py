"""Start the server on $PORT (used by Firedrill's per-drill launch)."""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("server.app:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8787")), log_level="warning")
