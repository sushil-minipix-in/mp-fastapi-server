from fastapi import APIRouter

from .admins import router as admins_router
from .analytics import router as analytics_router
from .artists import router as artists_router
from .discounts import router as discounts_router
from .drm import router as drm_router
from .events import router as events_router
from .exports import router as exports_router
from .genres import router as genres_router
from .languages import router as languages_router
from .media_houses import router as media_houses_router
from .movies import router as movies_router
from .oauth2 import router as oauth2_router
from .auth import router as login_auth_router
from .orders import router as orders_router
from .justpay import router as justpay_router
from .pp_orders import router as phonepe_router
from .partners import router as partners_router
from .paytm_orders import router as paytm_orders_router
from .paytm_tickets import router as paytm_tickets_router
from .plans import router as plans_router
from .playlists import router as playlists_router
from .short_playlists import router as short_playlists_router
from .promos import router as promos_router
from .resellers import router as resellers_router
from .search import router as search_router
from .shorts_search import router as short_search_router
from .series import router as series_router
from .webseries import router as webseries_router
from .episodes import router as episodes_router
from .sitemap import router as sitemap_router
from .songs import router as songs_router
from .tickets import router as tickets_router
from .justpay_tickets import router as justpay_tickets_router
from .transcoding import router as transcoding_router
from .tv import router as tv_router
from .uploads import router as uploads_router
from .users import router as users_router
from .paytm_subscriptions import router as paytm_subs_router
from .subscriptions import router as subscriptions_router
from .webhooks import router as webhooks_router
from .transcode_callback import router as transcode_router


router = APIRouter()

router.include_router(users_router, prefix="/users", tags=["users"])
router.include_router(admins_router, prefix="/admins", tags=["admins"])
router.include_router(oauth2_router, prefix="/oauth2", tags=["oauth2"])
router.include_router(login_auth_router, prefix="/login", tags=["OTP Login"])
router.include_router(artists_router, prefix="/artists", tags=["artists"])
router.include_router(movies_router, prefix="/movies", tags=["movies"])
router.include_router(series_router, prefix="/series", tags=["series"])
router.include_router(songs_router, prefix="/songs", tags=["songs"])
router.include_router(webseries_router, prefix="/webseries", tags=["webseries"])
router.include_router(episodes_router, prefix="/episodes", tags=["episodes"])
router.include_router(plans_router, prefix="/plans", tags=["plans"])
router.include_router(uploads_router, prefix="/uploads", tags=["uploads"])
router.include_router(orders_router, prefix="/orders", tags=["orders"])
router.include_router(justpay_router, prefix="/justpay", tags=["justpay"])
router.include_router(phonepe_router, prefix="/pp_orders", tags=["phonepe"])
router.include_router(search_router, prefix="/search", tags=["search"])
router.include_router(short_search_router, prefix="/short_search", tags=["short_search"])
router.include_router(genres_router, prefix="/genres", tags=["genres"])
router.include_router(drm_router, prefix="/drm", tags=["drm"])
router.include_router(promos_router, prefix="/promos", tags=["promos"])
router.include_router(exports_router, prefix="/exports", tags=["exports"])
router.include_router(tv_router, prefix="/tv", tags=["tv"])
router.include_router(tickets_router, prefix="/tickets", tags=["tickets"])
router.include_router(justpay_tickets_router, prefix="/justpay-ticket", tags=["justpay tickets"])
router.include_router(events_router, prefix="/events", tags=["events"])
router.include_router(partners_router, prefix="/partners", tags=["partners"])

router.include_router(
    media_houses_router,
    prefix="/mediaHouses",
    tags=["media houses"]
)
router.include_router(
    discounts_router,
    prefix="/discounts",
    tags=["discounts"]
)
router.include_router(
    playlists_router,
    prefix="/playlists",
    tags=["playlists"]
)
router.include_router(
    short_playlists_router,
    prefix="/short_playlists",
    tags=["short playlists"]
)
router.include_router(
    languages_router,
    prefix="/languages",
    tags=["languages"]
)
router.include_router(
    analytics_router,
    prefix="/analytics",
    tags=["analytics"]
)
router.include_router(
    transcoding_router,
    prefix="/transcode_callback",
    tags=["transcode callback"]
)
router.include_router(
    resellers_router,
    prefix="/resellers",
    tags=["resellers"]
)
router.include_router(
    paytm_orders_router,
    prefix="/paytm_orders",
    tags=["paytm_orders"]
)

router.include_router(
    paytm_tickets_router,
    prefix="/paytm_tickets",
    tags=["paytm_tickets"]
)

router.include_router(
    sitemap_router,
    prefix="/sitemap",
    tags=["sitemap"]
)

router.include_router(
    subscriptions_router,
    prefix="/subscriptions",
    tags=["subscriptions"])

router.include_router(
    paytm_subs_router,
    prefix="/paytm_subscriptions",
    tags=["paytm subscriptions"]
)

router.include_router(
    webhooks_router,
    prefix="/webhooks",
    tags=["Webhooks"]
)

router.include_router(
    transcode_router,
    prefix="/transcode",
    tags=["Transcode Callback"]
)