from aiogram import Router
from .start import router as start_router
from .subscription import router as subscription_router
from .payments import router as payments_router
from .referral import router as referral_router
from .admin import router as admin_router

main_router = Router()
main_router.include_routers(
    start_router,
    subscription_router,
    payments_router,
    referral_router,
    admin_router,
)

__all__ = ["main_router"]
