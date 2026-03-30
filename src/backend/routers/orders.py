from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from config import settings
from models.database import (
    create_generation_batch,
    create_order,
    get_order,
    get_sku,
    increment_order_rerun_usage,
    list_deliverables,
    list_generation_batches,
    list_orders_for_identity,
    list_skus,
)
from models.schemas import (
    BatchListResponse,
    DeliverableInfo,
    DeliverableListResponse,
    GenerateRequest,
    GenerationBatchInfo,
    OrderCreateRequest,
    OrderInfo,
    OrderListResponse,
    PaymentStatus,
    SkuInfo,
    StartOrderRequest,
    StartOrderResponse,
)
from routers.generate import PACKAGES, generate_order_batch

router = APIRouter(tags=["orders"])


def _assert_order_owner(order: dict | None, request: Request) -> dict:
    if order is None or order["identity_id"] != request.state.user_id:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


async def _serialize_order(order: dict) -> OrderInfo:
    batches = await list_generation_batches(order["order_id"])
    deliverables = await list_deliverables(order["order_id"])
    sku = await get_sku(order["sku_id"])
    package = PACKAGES.get(order["package_id"])
    rerun_quota = int(order["entitlement_snapshot"].get("rerun_quota", 0))
    latest_batch = GenerationBatchInfo(**batches[0]) if batches else None
    return OrderInfo(
        order_id=order["order_id"],
        identity_id=order["identity_id"],
        sku_id=order["sku_id"],
        package_id=order["package_id"],
        amount=order["amount"],
        currency=order["currency"],
        payment_status=PaymentStatus(order["payment_status"]),
        fulfillment_status=order["fulfillment_status"],
        service_status=order["service_status"],
        entitlement_snapshot=order["entitlement_snapshot"],
        rerun_used_count=order["rerun_used_count"],
        created_at=order["created_at"],
        paid_at=order.get("paid_at"),
        expired_at=order.get("expired_at"),
        closed_at=order.get("closed_at"),
        latest_batch=latest_batch,
        deliverable_count=len(deliverables),
        remaining_reruns=max(rerun_quota - order["rerun_used_count"], 0),
        package_name=package.name if package else order["package_id"],
        sku_name=sku["name"] if sku else order["sku_id"],
    )


@router.get("/api/skus", response_model=list[SkuInfo])
async def get_sku_catalog():
    rows = await list_skus()
    return [SkuInfo(**row) for row in rows]


@router.post("/api/orders", response_model=OrderInfo)
async def create_order_endpoint(payload: OrderCreateRequest, request: Request):
    if payload.package_id not in PACKAGES:
        raise HTTPException(status_code=400, detail="Unknown package_id")
    order = await create_order(request.state.user_id, payload.package_id, payload.sku_id)
    return await _serialize_order(order)


@router.get("/api/orders", response_model=OrderListResponse)
async def list_orders(request: Request):
    orders = await list_orders_for_identity(request.state.user_id)
    items = [await _serialize_order(order) for order in orders]
    return OrderListResponse(items=items)


@router.get("/api/orders/{order_id}", response_model=OrderInfo)
async def get_order_endpoint(order_id: str, request: Request):
    order = _assert_order_owner(await get_order(order_id), request)
    return await _serialize_order(order)


@router.get("/api/orders/{order_id}/batches", response_model=BatchListResponse)
async def get_order_batches(order_id: str, request: Request):
    order = _assert_order_owner(await get_order(order_id), request)
    items = [GenerationBatchInfo(**row) for row in await list_generation_batches(order["order_id"])]
    return BatchListResponse(items=items)


@router.get("/api/orders/{order_id}/deliverables", response_model=DeliverableListResponse)
async def get_order_deliverables(order_id: str, request: Request):
    order = _assert_order_owner(await get_order(order_id), request)
    items = [DeliverableInfo(**row) for row in await list_deliverables(order["order_id"])]
    return DeliverableListResponse(items=items)


def _ensure_can_start(order: dict) -> None:
    if order["payment_status"] not in {"paid", "free_granted"}:
        raise HTTPException(status_code=409, detail="Order has not been paid")


@router.post("/api/orders/{order_id}/start", response_model=StartOrderResponse)
async def start_order(
    order_id: str,
    payload: StartOrderRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    order = _assert_order_owner(await get_order(order_id), request)
    _ensure_can_start(order)

    batches = await list_generation_batches(order_id)
    if any(batch["status"] in {"pending", "processing"} for batch in batches):
        batch = batches[0]
        return StartOrderResponse(
            order_id=order_id,
            batch_id=batch["batch_id"],
            fulfillment_status="processing",
        )

    requested_photos = int(order["entitlement_snapshot"].get("promised_photos", settings.photos_per_package))
    batch = await create_generation_batch(
        order_id,
        batch_type="initial",
        initiated_by="user",
        requested_photos=requested_photos,
    )
    background_tasks.add_task(
        generate_order_batch,
        order_id,
        batch["batch_id"],
        GenerateRequest(
            user_id=request.state.user_id,
            package_id=order["package_id"],
            makeup_style=payload.makeup_style,
            gender=payload.gender,
            groom_style=payload.groom_style,
            bride_style=payload.bride_style,
        ),
        requested_photos=requested_photos,
    )
    return StartOrderResponse(
        order_id=order_id,
        batch_id=batch["batch_id"],
        fulfillment_status="processing",
    )


@router.post("/api/orders/{order_id}/reruns", response_model=StartOrderResponse)
async def rerun_order(
    order_id: str,
    payload: StartOrderRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    order = _assert_order_owner(await get_order(order_id), request)
    _ensure_can_start(order)
    rerun_quota = int(order["entitlement_snapshot"].get("rerun_quota", 0))
    if order["rerun_used_count"] >= rerun_quota:
        raise HTTPException(status_code=409, detail="No rerun quota remaining")

    batches = await list_generation_batches(order_id)
    if any(batch["status"] in {"pending", "processing"} for batch in batches):
        raise HTTPException(status_code=409, detail="Order already has a running batch")

    await increment_order_rerun_usage(order_id)
    requested_photos = int(order["entitlement_snapshot"].get("promised_photos", settings.photos_per_package))
    batch = await create_generation_batch(
        order_id,
        batch_type="rerun",
        initiated_by="user",
        requested_photos=requested_photos,
    )
    background_tasks.add_task(
        generate_order_batch,
        order_id,
        batch["batch_id"],
        GenerateRequest(
            user_id=request.state.user_id,
            package_id=order["package_id"],
            makeup_style=payload.makeup_style,
            gender=payload.gender,
            groom_style=payload.groom_style,
            bride_style=payload.bride_style,
        ),
        requested_photos=requested_photos,
    )
    return StartOrderResponse(
        order_id=order_id,
        batch_id=batch["batch_id"],
        fulfillment_status="processing",
    )
