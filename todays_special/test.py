import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv, dotenv_values
import numpy as np

# 1) Resolve the .env path reliably (cwd or next to this file)
dotenv_path = find_dotenv(filename=".env", usecwd=True)
if not dotenv_path:
    dotenv_path = str((Path(__file__).parent / ".env").resolve())

# 2) Load and OVERRIDE existing env vars with values from .env
load_dotenv(dotenv_path, override=True)

# 3) Debug prints to confirm what’s happening
print("Loaded .env from:", dotenv_path)
print("File values:", {k: ("***" if "KEY" in k or "TOKEN" in k else v)
                      for k, v in dotenv_values(dotenv_path).items()})
print("Effective env:", {
    "ITEMSNAP_MODEL": os.getenv("ITEMSNAP_MODEL"),
    "OPENAI_API_KEY": (os.getenv("OPENAI_API_KEY") or "")[:8] + "…"
})


print(...)
print(type(...))

arr = np.zeros((3, 4, 5))
print(arr[..., 0])  # take everything, just fix the last index