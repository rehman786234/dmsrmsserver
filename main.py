import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import bcrypt
import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

from databasemanager import DatabaseManager

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("dms-api")

# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
JWT_ISSUER = os.getenv("JWT_ISSUER", "dms-api")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "dms-client")

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

# ============================================================
# CONFIG VALIDATION
# ============================================================

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not configured in .env")

if len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY must be at least 32 characters long")

if ALGORITHM != "HS256":
    raise RuntimeError("This application currently expects ALGORITHM=HS256")

# ============================================================
# APP
# ============================================================

app = FastAPI(title="DMS API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

db = DatabaseManager()

# ============================================================
# AUTH SCHEME
# ============================================================

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/bookingapp/login")

# ============================================================
# MODELS
# ============================================================


class DataRequest(BaseModel):
    last_sync_time: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ============================================================
# DB HELPERS
# ============================================================


@contextmanager
def db_cursor() -> Iterator[Any]:
    """Yield a cursor and always close cursor + connection."""
    conn, cursor = None, None
    try:
        conn, cursor = db.getConnection()
        if conn is None or cursor is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection failed",
            )
        yield cursor
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            logger.exception("Failed to close cursor")
        try:
            if conn:
                conn.close()
        except Exception:
            logger.exception("Failed to close connection")


def rows_to_dicts(cursor: Any, rows: list) -> list[dict]:
    """Convert tuple rows to dicts using cursor.description."""
    if not rows:
        return []
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def fetch_all(cursor: Any, query: str, params: tuple = ()) -> list[dict]:
    cursor.execute(query, params)
    return rows_to_dicts(cursor, cursor.fetchall())


# ============================================================
# JWT
# ============================================================


def create_access_token(user_id: int, user_name: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "name": user_name,
        "type": "access",
        "iat": now,
        "exp": expire,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )
    except JWTError:
        raise _unauthorized("Invalid or expired authentication token")

    if payload.get("type") != "access":
        raise _unauthorized("Invalid token type")

    if not payload.get("sub"):
        raise _unauthorized("Invalid authentication token")

    return payload


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    return verify_access_token(token)


# ============================================================
# PASSWORD
# ============================================================


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


# ============================================================
# BUSINESS LOGIC
# ============================================================


def login_user(email: str, password: str) -> dict:
    try:
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT slm_code, slm_name, slm_email, password
                FROM salesmen
                WHERE slm_email = %s
                LIMIT 1
                """,
                (email,),
            )
            user = cursor.fetchone()

            if user is None or not verify_password(password, user[3]):
                # Same response for both cases -> avoid user enumeration
                raise _unauthorized("Invalid email or password")

            user_id, user_name = user[0], user[1]

        access_token = create_access_token(user_id=user_id, user_name=user_name)

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Login error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


def check_data(last_sync_time: str | None) -> dict:
    try:
        with db_cursor() as cursor:
            is_first_sync = (
                last_sync_time is None
                or last_sync_time.strip().lower() == "null"
            )

            if is_first_sync:
                rows = fetch_all(cursor, "SELECT * FROM check_update")
                return {
                    "update_available": True,
                    "message": "Download Data now",
                    "data": rows,
                }

            rows = fetch_all(
                cursor,
                "SELECT * FROM check_update WHERE updated_at > %s",
                (last_sync_time,),
            )

            if not rows:
                return {
                    "update_available": False,
                    "message": "No new data available",
                }

            return {
                "update_available": True,
                "message": "New data available for download",
                "data": rows,
            }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Check data error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check for new data",
        )


def get_data(salesman_name: str) -> dict:
    try:
        with db_cursor() as cursor:
            customers = fetch_all(cursor, "SELECT * FROM customers")
            products = fetch_all(cursor, "SELECT * FROM products")
            categories = fetch_all(cursor, "SELECT * FROM categories")
            customer_types = fetch_all(cursor, "SELECT * FROM customer_types")
            areas = fetch_all(cursor, "SELECT * FROM areas")
            sub_areas = fetch_all(cursor, "SELECT * FROM sub_areas")

            orders = fetch_all(
                cursor,
                "SELECT * FROM sales_order WHERE salesman = %s",
                (salesman_name,),
            )
            order_prd = fetch_all(cursor, "SELECT * FROM order_prd")

            return {
                "customers": customers,
                "products": products,
                "categories": categories,
                "customer_types": customer_types,
                "areas": areas,
                "sub_areas": sub_areas,
                "orders": orders,
                "order_prd": order_prd,
            }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Get data error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download data",
        )


# ============================================================
# ROUTES
# ============================================================


@app.post("/api/v1/bookingapp/login")
def login(request: LoginRequest) -> dict:
    return login_user(request.email, request.password)


@app.post("/api/v1/dmsdata/check_new_data")
def check_new_data(
    request: DataRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    return check_data(request.last_sync_time)


@app.post("/api/v1/dmsdata/download/all")
def download_all_data(
    current_user: dict = Depends(get_current_user),
) -> dict:
    salesman_name = current_user.get("name")
    if not salesman_name:
        raise _unauthorized("Invalid user information in token")

    return get_data(salesman_name)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9990,
        reload=False,
    )