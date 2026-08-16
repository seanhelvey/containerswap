import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import email, events, ratelimit, storage
from app.auth import require_user, verify_csrf
from app.db import get_db
from app.geo import fuzz, parse_latlng
from app.images import ImageRejected, process_upload
from app.models import Listing, Message, Report, User
from app.templating import CATEGORIES, render

logger = logging.getLogger("containerswap")

router = APIRouter()

PAGE_SIZE = 24


@router.get("/")
def home(request: Request, q: str = "", category: str = "", db: Session = Depends(get_db)):
    query = (
        select(Listing)
        .options(selectinload(Listing.owner))
        .where(Listing.status == "active")
        .order_by(Listing.created_at.desc())
    )
    term = q.strip()
    if term:
        like = f"%{term}%"
        query = query.where(Listing.title.ilike(like) | Listing.body.ilike(like))
    if category in CATEGORIES:
        query = query.where(Listing.category == category)

    listings = db.execute(query.limit(PAGE_SIZE)).scalars().all()
    return render(
        request,
        "index.html",
        {"listings": listings, "q": term, "active_category": category},
    )


@router.get("/map")
def map_view(request: Request):
    return render(request, "map.html")


@router.get("/api/listings.geojson")
def listings_geojson(db: Session = Depends(get_db)):
    """Map pins. Coordinates here are already fuzzed — see app.geo."""
    rows = (
        db.execute(
            select(Listing)
            .where(Listing.status == "active", Listing.lat.is_not(None))
            .order_by(Listing.created_at.desc())
            .limit(500)
        )
        .scalars()
        .all()
    )

    return JSONResponse(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [row.lng, row.lat]},
                    "properties": {
                        "id": row.id,
                        "title": row.title,
                        "price": row.price,
                        "quantity": row.quantity,
                        "category": row.category,
                        "url": f"/listings/{row.id}",
                        "image": storage.url_for(row.image_path),
                    },
                }
                for row in rows
            ],
        },
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.get("/listings/new")
def new_listing_form(request: Request, user: User = Depends(require_user)):
    return render(request, "new_listing.html")


@router.post(
    "/listings",
    dependencies=[Depends(verify_csrf), Depends(ratelimit.limiter("listing"))],
)
async def create_listing(
    request: Request,
    title: str = Form(""),
    body: str = Form(""),
    quantity: str = Form(""),
    price: str = Form(""),
    category: str = Form("other"),
    lat: str = Form(""),
    lng: str = Form(""),
    image: UploadFile | None = File(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not user.email_verified:
        return render(request, "new_listing.html", status_code=403)

    title = title.strip()
    if not title:
        return _new_listing_error(request, "listing.error.title_required", locals())

    image_path = None
    if image is not None and image.filename:
        raw = await image.read()
        try:
            # Off the event loop: this decodes and re-encodes a bitmap and then
            # pushes it to the object store, so it blocks for long enough to stall
            # every other request on this worker.
            image_path = await run_in_threadpool(process_upload, raw)
        except ImageRejected as exc:
            return _new_listing_error(request, f"listing.error.image.{exc.args[0]}", locals())
        except storage.StorageError:
            # Our fault, not theirs, so it is logged rather than explained away — but
            # they still get the form back with their text intact instead of a 500.
            logger.exception("listing image upload failed")
            return _new_listing_error(request, "listing.error.image.storage_failed", locals())

    coords = parse_latlng(lat, lng)
    stored_lat, stored_lng = fuzz(*coords) if coords else (None, None)

    listing = Listing(
        title=title[:120],
        body=body.strip()[:4000],
        quantity=quantity.strip()[:60],
        price=price.strip()[:60],
        category=category if category in CATEGORIES else "other",
        image_path=image_path,
        lat=stored_lat,
        lng=stored_lng,
        owner_id=user.id,
    )
    db.add(listing)
    db.commit()

    events.log_event(db, events.LISTING_CREATED, listing_id=listing.id, user_id=user.id)
    return RedirectResponse(f"/listings/{listing.id}", status_code=303)


@router.get("/listings/{listing_id}")
def listing_detail(request: Request, listing_id: int, db: Session = Depends(get_db)):
    listing = _get_listing(db, listing_id)
    viewer = getattr(request.state, "user", None)
    events.log_event(
        db,
        events.LISTING_VIEWED,
        listing_id=listing.id,
        user_id=viewer.id if viewer else None,
    )

    return render(
        request,
        "listing_detail.html",
        {
            "listing": listing,
            "is_owner": bool(viewer and viewer.id == listing.owner_id),
        },
    )


@router.post(
    "/listings/{listing_id}/contact",
    dependencies=[Depends(verify_csrf), Depends(ratelimit.limiter("contact"))],
)
def send_contact(
    request: Request,
    listing_id: int,
    background: BackgroundTasks,
    body: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """The only path between a sender and an owner. No address of any kind changes
    hands — the message lands in the owner's /inbox and nowhere else."""
    if not user.email_verified:
        return RedirectResponse(f"/listings/{listing_id}", status_code=303)

    listing = _get_listing(db, listing_id)
    text = body.strip()
    if not text:
        return RedirectResponse(f"/listings/{listing_id}?error=empty_message", status_code=303)
    if listing.owner_id == user.id:
        return RedirectResponse(f"/listings/{listing_id}", status_code=303)

    db.add(
        Message(
            listing_id=listing.id,
            sender_id=user.id,
            recipient_id=listing.owner_id,
            body=text[:2000],
        )
    )
    db.commit()
    events.log_event(db, events.CONTACT_SENT, listing_id=listing.id, user_id=user.id)

    # After the commit and off the request: an inbox message that was saved must not
    # be reported as failed because a mail provider was slow. The owner's address is
    # read here and passed straight to the mailer — it never reaches the template,
    # the sender, or the log.
    background.add_task(
        email.notify_new_message,
        listing.owner.email,
        user.display_name,
        listing.title,
    )

    return RedirectResponse(f"/listings/{listing_id}?sent=1", status_code=303)


@router.post(
    "/listings/{listing_id}/report",
    dependencies=[Depends(verify_csrf), Depends(ratelimit.limiter("report"))],
)
def report_listing(
    listing_id: int,
    background: BackgroundTasks,
    reason: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    listing = _get_listing(db, listing_id)
    text = reason.strip()[:500]
    db.add(Report(listing_id=listing_id, reporter_id=user.id, reason=text))
    db.commit()

    # "We will take a look" is what the page promises. Without this the row is the
    # end of the road and the promise is false.
    background.add_task(email.notify_new_report, listing_id, listing.title, text)

    return RedirectResponse(f"/listings/{listing_id}?reported=1", status_code=303)


@router.post("/listings/{listing_id}/complete", dependencies=[Depends(verify_csrf)])
def mark_completed(
    listing_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    listing = _get_listing(db, listing_id)
    if listing.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your listing.")
    if listing.status != "completed":
        listing.status = "completed"
        db.commit()
        events.log_event(db, events.LISTING_COMPLETED, listing_id=listing.id, user_id=user.id)
    return RedirectResponse(f"/listings/{listing_id}", status_code=303)


@router.get("/inbox")
def inbox(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    messages = (
        db.execute(
            select(Message)
            .options(selectinload(Message.listing), selectinload(Message.sender))
            .where(Message.recipient_id == user.id)
            .order_by(Message.created_at.desc())
            .limit(200)
        )
        .scalars()
        .all()
    )

    mine = (
        db.execute(
            select(Listing).where(Listing.owner_id == user.id).order_by(Listing.created_at.desc())
        )
        .scalars()
        .all()
    )

    return render(request, "inbox.html", {"messages": messages, "my_listings": mine})


def _get_listing(db: Session, listing_id: int) -> Listing:
    listing = db.execute(
        select(Listing).options(selectinload(Listing.owner)).where(Listing.id == listing_id)
    ).scalar_one_or_none()
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found.")
    return listing


def _new_listing_error(request: Request, error_key: str, form: dict):
    keep = {k: form.get(k, "") for k in ("title", "body", "quantity", "price", "category")}
    return render(request, "new_listing.html", {"error_key": error_key, **keep}, status_code=400)
