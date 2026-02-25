from fastapi import APIRouter
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.public import router as public_router
from app.api.v1.routes.bookings import router as bookings_router
from app.api.v1.routes.ops import router as ops_router
from app.api.v1.routes.payments import router as payments_router
from app.api.v1.routes.admin import router as admin_router
from app.api.v1.routes.pilot import router as pilot_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(public_router)
api_router.include_router(bookings_router)
api_router.include_router(ops_router)
api_router.include_router(payments_router)
api_router.include_router(admin_router)
api_router.include_router(pilot_router)
