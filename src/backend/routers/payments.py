from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from models.database import (
    confirm_payment,
    create_payment_transaction,
    get_order,
    get_payment_transaction,
)
from models.schemas import (
    MockPayConfirmRequest,
    MockPayCreateRequest,
    PaymentConfirmResponse,
    PaymentSessionResponse,
    PaymentStatus,
)

router = APIRouter(tags=["payments"])


def _assert_order_owner(order: dict | None, request: Request) -> dict:
    if order is None or order["identity_id"] != request.state.user_id:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/api/pay/mock/create", response_model=PaymentSessionResponse)
async def create_mock_payment(payload: MockPayCreateRequest, request: Request):
    order = _assert_order_owner(await get_order(payload.order_id), request)
    if order["amount"] <= 0:
        raise HTTPException(status_code=409, detail="Free order does not require payment")
    if order["payment_status"] == "paid":
        raise HTTPException(status_code=409, detail="Order already paid")

    payment = await create_payment_transaction(
        payload.order_id,
        provider="mock",
        status="pending",
        checkout_url=f"/pay/result?order_id={payload.order_id}",
    )
    return PaymentSessionResponse(
        payment_id=payment["payment_id"],
        order_id=payload.order_id,
        provider="mock",
        status=payment["status"],
        amount=payment["amount"],
        currency=payment["currency"],
        checkout_url=payment["checkout_url"],
    )


@router.post("/api/pay/mock/confirm", response_model=PaymentConfirmResponse)
async def confirm_mock_payment(payload: MockPayConfirmRequest, request: Request):
    payment = await get_payment_transaction(payload.payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    order = _assert_order_owner(await get_order(payment["order_id"]), request)
    if order["amount"] <= 0:
        raise HTTPException(status_code=409, detail="Free order does not require payment")

    confirmed = await confirm_payment(
        payload.payment_id,
        succeed=payload.succeed,
        notify_payload={"provider": "mock", "success": payload.succeed},
    )
    order_after = await get_order(payment["order_id"])
    return PaymentConfirmResponse(
        payment_id=confirmed["payment_id"],
        order_id=confirmed["order_id"],
        payment_status=PaymentStatus(order_after["payment_status"]),
        paid_at=order_after.get("paid_at"),
    )
