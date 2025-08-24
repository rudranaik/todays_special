# fast.py
from typing import Literal, List
from fastapi import FastAPI
from pydantic import BaseModel, Field, conlist

app1 = FastAPI(title="Mini Calc API", version="1.0")
app2 = FastAPI(title="Mini Calc API2", version="2.0")

# ---- Request/Response Schemas ----
class AddRequest(BaseModel):
    a: int = Field(..., description="First integer")
    b: int = Field(..., description="Second integer")

class BatchCalcRequest(BaseModel):
    numbers: conlist(float, min_length=2) = Field(..., description="At least two numbers")
    op: Literal["add", "multiply"] = Field("add", description="Operation to perform")

class Result(BaseModel):
    result: float

# ---- Endpoints ----

# Keep the original GET for quick testing
@app1.get("/add", response_model=Result, summary="Add two numbers via query params")
def add_get(a: int, b: int):
    return {"result": a + b}

# NEW: POST endpoint using JSON body
@app1.post("/add", response_model=Result, summary="Add two numbers via JSON")
def add_post(payload: AddRequest):
    return {"result": payload.a + payload.b}

# Bonus: Batch calculator to show validation + enums
@app1.post("/calc", response_model=Result, summary="Batch add/multiply numbers via JSON")
def calc(payload: BatchCalcRequest):
    if payload.op == "add":
        total = sum(payload.numbers)
        return {"result": total}
    # multiply
    prod = 1.0
    for x in payload.numbers:
        prod *= x
    return {"result": prod}


@app2.get("/add", response_model=Result, summary="Add two numbers via query params")
def add_get(a: int, b: int):
    return {"result": a + b}