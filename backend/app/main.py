from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .diagnosis import build_diagnosis, validate_stock_code
from .errors import DiagnosisError
from .fuyao import FuyaoClient
from .schemas import Diagnosis
from .research import ResearchRequest, ResearchReport, make_plan, factual_report, attach_prices
from .llm import add_interpretation
from .prices import PriceAnalysis, build_prices, price_window
from .stocks import STOCKS, Stock

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
app = FastAPI(title="StockLens Backend", version="0.1.0")


def get_fuyao_client():
    return FuyaoClient()


@app.exception_handler(DiagnosisError)
async def diagnosis_error_handler(request: Request, exc: DiagnosisError):
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/stocks", response_model=list[Stock])
def stocks():
    return STOCKS


@app.get("/api/diagnosis", response_model=Diagnosis)
def diagnosis(stock_code: str, client: FuyaoClient = Depends(get_fuyao_client)):
    validate_stock_code(stock_code)
    return build_diagnosis(stock_code, client.annual_income_statements(stock_code))


@app.post("/api/plan")
def plan(request: ResearchRequest):
    validate_stock_code(request.stock_code)
    return make_plan(request.question, request.stock_code)


@app.post("/api/research", response_model=ResearchReport)
def research(request: ResearchRequest, client: FuyaoClient = Depends(get_fuyao_client)):
    validate_stock_code(request.stock_code)
    wants_prices = any(d.id == "price" for d in make_plan(request.question, request.stock_code).dimensions)
    try:
        report = build_diagnosis(request.stock_code, client.annual_income_statements(request.stock_code))
    except DiagnosisError as exc:
        if not wants_prices:
            raise
        report = Diagnosis(stock_code=request.stock_code, status="unavailable", current_year=None, previous_year=None,
            issues=[exc.code], metrics=[], evidence=[], sources=[])
    result = factual_report(request, report)
    if any(d.id == "price" for d in result.plan.dimensions):
        start, end = price_window()
        try:
            prices = build_prices(request.stock_code, client.historical_prices(request.stock_code, start, end), start, end)
        except DiagnosisError as exc:
            prices = PriceAnalysis(requested_start=str(start), requested_end=str(end), error_code=exc.code, issues=[exc.code])
        attach_prices(result, prices)
    return add_interpretation(result)


# Development uses the Vite proxy. Production serves the compiled UI on the same origin.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (frontend_dist / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def index():
    if (frontend_dist / "index.html").is_file():
        return FileResponse(frontend_dist / "index.html")
    return JSONResponse({"message": "Build the frontend with npm run build in frontend/, or use the Vite development server.", "docs": "/docs"})
