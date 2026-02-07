# core/views.py
from __future__ import annotations

from datetime import datetime, timezone

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema

from .models import Negociacion, Reserva
from .serializers import (
    CreateIdSerializer,
    NegociacionAcceptSerializer,
    NegociacionCancelSerializer,
    NegociacionCreateSerializer,
    NegociacionDecisionResponseSerializer,
    NegociacionListItemSerializer,
    NegociacionReadSerializer,
    NegociacionRejectSerializer,
    OkSerializer,
    ReservaCancelSerializer,
    ReservaCreateSerializer,
    ReservaListItemSerializer,
    ReservaReadSerializer,
)


# =========================
# Reservas
# =========================

@extend_schema(tags=["Reservas"], request=ReservaCreateSerializer, responses={201: CreateIdSerializer})
class ReservaCreateView(APIView):
    """
    Crea una reserva.
    El orquestador envía el payload completo (monto + comisión).
    """

    def post(self, request):
        ser = ReservaCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            reserva = ser.save()
        except IntegrityError:
            # uq_reserva_alumno_clase
            return Response({"detail": "Ya existe una reserva para (alumno_id, clase_id)"}, status=409)

        return Response({"ok": True, "id": reserva.id}, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Reservas"], responses={200: ReservaReadSerializer})
class ReservaDetailView(APIView):
    """Obtiene detalle de una reserva por id."""

    def get(self, request, reserva_id: int):
        reserva = Reserva.objects.filter(id=reserva_id).first()
        if not reserva:
            return Response({"detail": "No encontrado"}, status=404)
        return Response(ReservaReadSerializer(reserva).data)


@extend_schema(
    tags=["Reservas"],
    parameters=[
        OpenApiParameter("alumno_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("clase_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("estado", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("from", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="timestamp_creado >= from"),
        OpenApiParameter("to", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="timestamp_creado <= to"),
        OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, description="Default 20"),
        OpenApiParameter("offset", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, description="Default 0"),
    ],
    responses={200: dict},
)
class ReservaListView(APIView):
    """
    Lista reservas por alumno_id o clase_id.

    Regla:
    - Debe venir alumno_id o clase_id (al menos uno).
    """

    def get(self, request):
        alumno_id = request.query_params.get("alumno_id")
        clase_id = request.query_params.get("clase_id")
        estado = request.query_params.get("estado")
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")

        limit = int(request.query_params.get("limit") or 20)
        offset = int(request.query_params.get("offset") or 0)

        if not alumno_id and not clase_id:
            return Response({"detail": "Debes enviar alumno_id o clase_id"}, status=400)

        qs = Reserva.objects.all().order_by("-timestamp_creado")

        if alumno_id:
            qs = qs.filter(alumno_id=alumno_id)
        if clase_id:
            qs = qs.filter(clase_id=clase_id)
        if estado:
            qs = qs.filter(estado=estado)
        if date_from:
            qs = qs.filter(timestamp_creado__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp_creado__date__lte=date_to)

        total = qs.count()
        items = qs[offset: offset + limit]

        return Response(
            {
                "results": ReservaListItemSerializer(items, many=True).data,
                "limit": limit,
                "offset": offset,
                "total": total,
            }
        )


@extend_schema(tags=["Reservas"], request=ReservaCancelSerializer, responses={200: OkSerializer})
class ReservaCancelView(APIView):
    """
    Cancela una reserva.

    Reglas:
    - Solo se cancela si la reserva está PENDIENTE.
    - Al cancelar, se cancelan negociaciones PENDIENTES asociadas.
    """

    @transaction.atomic
    def patch(self, request, reserva_id: int):
        reserva = Reserva.objects.select_for_update().filter(id=reserva_id).first()
        if not reserva:
            return Response({"detail": "No encontrado"}, status=404)

        if reserva.estado != Reserva.Estado.PENDIENTE:
            return Response({"detail": "Solo se puede cancelar una reserva PENDIENTE"}, status=409)

        # Cierra negociaciones pendientes
        Negociacion.objects.filter(reserva_id=reserva.id, estado=Negociacion.Estado.PENDIENTE).update(
            estado=Negociacion.Estado.CANCELADA,
            decided_at=datetime.now(timezone.utc),
        )

        reserva.estado = Reserva.Estado.CANCELADA
        reserva.save(update_fields=["estado", "updated_at"])

        return Response({"ok": True})


# =========================
# Negociaciones
# =========================

@extend_schema(tags=["Negociaciones"], request=NegociacionCreateSerializer, responses={201: CreateIdSerializer})
class NegociacionCreateView(APIView):
    """
    Crea una negociación (propuesta de monto) para una reserva.
    """

    def post(self, request):
        ser = NegociacionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        nego = ser.save()
        return Response({"ok": True, "id": nego.id}, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Negociaciones"], responses={200: NegociacionReadSerializer})
class NegociacionDetailView(APIView):
    """Detalle de negociación por id."""

    def get(self, request, negociacion_id: int):
        nego = Negociacion.objects.filter(id=negociacion_id).first()
        if not nego:
            return Response({"detail": "No encontrado"}, status=404)
        return Response(NegociacionReadSerializer(nego).data)


@extend_schema(tags=["Negociaciones"], responses={200: dict})
class NegociacionListByReservaView(APIView):
    """
    Historial de negociaciones de una reserva (ordenado por created_at desc).
    """

    def get(self, request, reserva_id: int):
        if not Reserva.objects.filter(id=reserva_id).exists():
            return Response({"detail": "reserva_id no existe"}, status=404)

        qs = Negociacion.objects.filter(reserva_id=reserva_id).order_by("-created_at")
        return Response({"results": NegociacionListItemSerializer(qs, many=True).data})


@extend_schema(
    tags=["Negociaciones"],
    request=NegociacionAcceptSerializer,
    responses={200: NegociacionDecisionResponseSerializer},
)
class NegociacionAcceptView(APIView):
    """
    Acepta una negociación.

    Efectos:
    - negociación -> ACEPTADA (decided_at)
    - reserva.monto_acordado = monto_propuesto
    - reserva -> CONFIRMADA
    - otras negociaciones PENDIENTES -> RECHAZADA
    """

    @transaction.atomic
    def patch(self, request, negociacion_id: int):
        nego = (
            Negociacion.objects.select_for_update()
            .select_related("reserva")
            .filter(id=negociacion_id)
            .first()
        )
        if not nego:
            return Response({"detail": "No encontrado"}, status=404)

        reserva = Reserva.objects.select_for_update().filter(id=nego.reserva_id).first()

        if reserva.estado != Reserva.Estado.PENDIENTE:
            return Response({"detail": "La reserva ya no está PENDIENTE"}, status=409)

        if nego.estado != Negociacion.Estado.PENDIENTE:
            return Response({"detail": "Solo se puede aceptar una negociación PENDIENTE"}, status=409)

        # Si ya hay una aceptada (carrera/race), no permitir
        if Negociacion.objects.filter(reserva_id=reserva.id, estado=Negociacion.Estado.ACEPTADA).exists():
            return Response({"detail": "Ya existe una negociación ACEPTADA para esta reserva"}, status=409)

        now = datetime.now(timezone.utc)

        # 1) aceptar negociación actual
        nego.estado = Negociacion.Estado.ACEPTADA
        nego.decided_at = now
        nego.save(update_fields=["estado", "decided_at"])

        # 2) actualizar reserva (cierra negociación)
        reserva.monto_acordado = nego.monto_propuesto
        reserva.estado = Reserva.Estado.CONFIRMADA
        reserva.save(update_fields=["monto_acordado", "estado", "updated_at"])

        # 3) rechazar otras pendientes (si existieran)
        Negociacion.objects.filter(
            reserva_id=reserva.id,
            estado=Negociacion.Estado.PENDIENTE,
        ).exclude(id=nego.id).update(
            estado=Negociacion.Estado.RECHAZADA,
            decided_at=now,
        )

        return Response(
            {
                "ok": True,
                "negociacion_id": nego.id,
                "estado_negociacion": nego.estado,
                "reserva_id": reserva.id,
                "estado_reserva": reserva.estado,
                "monto_acordado": str(reserva.monto_acordado),
            }
        )


@extend_schema(
    tags=["Negociaciones"],
    request=NegociacionRejectSerializer,
    responses={200: NegociacionDecisionResponseSerializer},
)
class NegociacionRejectView(APIView):
    """
    Rechaza una negociación PENDIENTE.
    No modifica la reserva (sigue PENDIENTE).
    """

    @transaction.atomic
    def patch(self, request, negociacion_id: int):
        nego = Negociacion.objects.select_for_update().select_related("reserva").filter(id=negociacion_id).first()
        if not nego:
            return Response({"detail": "No encontrado"}, status=404)

        reserva = Reserva.objects.select_for_update().filter(id=nego.reserva_id).first()

        if reserva.estado != Reserva.Estado.PENDIENTE:
            return Response({"detail": "La reserva ya no está PENDIENTE"}, status=409)

        if nego.estado != Negociacion.Estado.PENDIENTE:
            return Response({"detail": "Solo se puede rechazar una negociación PENDIENTE"}, status=409)

        now = datetime.now(timezone.utc)
        nego.estado = Negociacion.Estado.RECHAZADA
        nego.decided_at = now
        nego.save(update_fields=["estado", "decided_at"])

        return Response(
            {
                "ok": True,
                "negociacion_id": nego.id,
                "estado_negociacion": nego.estado,
                "reserva_id": reserva.id,
                "estado_reserva": reserva.estado,
                "monto_acordado": str(reserva.monto_acordado),
            }
        )


@extend_schema(
    tags=["Negociaciones"],
    request=NegociacionCancelSerializer,
    responses={200: NegociacionDecisionResponseSerializer},
)
class NegociacionCancelView(APIView):
    """
    Cancela una negociación PENDIENTE.
    Similar a RECHAZAR, pero estado=CANCELADA.
    """

    @transaction.atomic
    def patch(self, request, negociacion_id: int):
        nego = Negociacion.objects.select_for_update().select_related("reserva").filter(id=negociacion_id).first()
        if not nego:
            return Response({"detail": "No encontrado"}, status=404)

        reserva = Reserva.objects.select_for_update().filter(id=nego.reserva_id).first()

        if reserva.estado != Reserva.Estado.PENDIENTE:
            return Response({"detail": "La reserva ya no está PENDIENTE"}, status=409)

        if nego.estado != Negociacion.Estado.PENDIENTE:
            return Response({"detail": "Solo se puede cancelar una negociación PENDIENTE"}, status=409)

        now = datetime.now(timezone.utc)
        nego.estado = Negociacion.Estado.CANCELADA
        nego.decided_at = now
        nego.save(update_fields=["estado", "decided_at"])

        return Response(
            {
                "ok": True,
                "negociacion_id": nego.id,
                "estado_negociacion": nego.estado,
                "reserva_id": reserva.id,
                "estado_reserva": reserva.estado,
                "monto_acordado": str(reserva.monto_acordado),
            }
        )
