# core/serializers.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from .models import Negociacion, Reserva


# =========================
# Respuestas estándar
# =========================

class OkSerializer(serializers.Serializer):
    """Respuesta simple para acciones tipo PATCH/DELETE."""
    ok = serializers.BooleanField()


class CreateIdSerializer(serializers.Serializer):
    """Respuesta estándar para creaciones."""
    ok = serializers.BooleanField()
    id = serializers.IntegerField()


class ListResponseSerializer(serializers.Serializer):
    """
    Wrapper simple para listados con paginación manual.
    (Si luego migras a DRF GenericViews + pagination, se puede reemplazar.)
    """
    results = serializers.ListField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()


# =========================
# Reserva
# =========================

class ReservaCreateSerializer(serializers.ModelSerializer):
    """
    Crea una Reserva con payload completo (orquestador).

    Reglas:
    - Estado inicia PENDIENTE (ignoramos si lo mandan distinto).
    - Unique (alumno_id, clase_id) se valida en BD.
    """

    class Meta:
        model = Reserva
        fields = ["alumno_id", "clase_id", "monto_acordado", "comision_por_alumno"]

    def create(self, validated_data):
        # Forzamos el estado inicial por consistencia del dominio.
        return Reserva.objects.create(**validated_data, estado=Reserva.Estado.PENDIENTE)


class ReservaReadSerializer(serializers.ModelSerializer):
    """Detalle de una Reserva."""
    class Meta:
        model = Reserva
        fields = [
            "id",
            "alumno_id",
            "clase_id",
            "estado",
            "monto_acordado",
            "comision_por_alumno",
            "timestamp_creado",
            "updated_at",
        ]


class ReservaCancelSerializer(serializers.Serializer):
    """
    Cancela una reserva.
    (No requiere body, pero se deja serializer para documentación y consistencia.)
    """
    pass


class ReservaListItemSerializer(serializers.ModelSerializer):
    """Item liviano para listados."""
    class Meta:
        model = Reserva
        fields = ["id", "alumno_id", "clase_id", "estado", "monto_acordado", "timestamp_creado"]


# =========================
# Negociación
# =========================

class NegociacionCreateSerializer(serializers.ModelSerializer):
    """
    Crea una negociación (propuesta).

    Reglas (en validate):
    - reserva debe estar PENDIENTE
    - si existe ACEPTADA para esa reserva => no permitir
    - si existe PENDIENTE para esa reserva => no permitir
    """

    reserva_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Negociacion
        fields = ["reserva_id", "monto_propuesto", "propuesto_por"]

    def validate(self, attrs):
        reserva_id = attrs["reserva_id"]
        reserva = Reserva.objects.filter(id=reserva_id).first()
        if not reserva:
            raise serializers.ValidationError("reserva_id no existe")

        if reserva.estado != Reserva.Estado.PENDIENTE:
            raise serializers.ValidationError("Solo se puede negociar una reserva en estado PENDIENTE")

        # Si ya hay una negociación aceptada, se cerró el regateo.
        if Negociacion.objects.filter(reserva_id=reserva_id, estado=Negociacion.Estado.ACEPTADA).exists():
            raise serializers.ValidationError("La reserva ya tiene una negociación ACEPTADA (negociación cerrada)")

        # Solo 1 pendiente activa
        if Negociacion.objects.filter(reserva_id=reserva_id, estado=Negociacion.Estado.PENDIENTE).exists():
            raise serializers.ValidationError("Ya existe una negociación PENDIENTE para esta reserva")

        # Guardamos reserva para usarla en create()
        self._reserva = reserva
        return attrs

    def create(self, validated_data):
        reserva_id = validated_data.pop("reserva_id")
        return Negociacion.objects.create(reserva_id=reserva_id, **validated_data, estado=Negociacion.Estado.PENDIENTE)


class NegociacionReadSerializer(serializers.ModelSerializer):
    """Detalle de negociación."""
    class Meta:
        model = Negociacion
        fields = ["id", "reserva_id", "monto_propuesto", "propuesto_por", "estado", "created_at", "decided_at"]


class NegociacionListItemSerializer(serializers.ModelSerializer):
    """Item para historial."""
    class Meta:
        model = Negociacion
        fields = ["id", "monto_propuesto", "propuesto_por", "estado", "created_at", "decided_at"]


class NegociacionDecisionResponseSerializer(serializers.Serializer):
    """
    Respuesta al aceptar/rechazar/cancelar.
    Incluye estado final de la reserva si cambió.
    """
    ok = serializers.BooleanField()
    negociacion_id = serializers.IntegerField()
    estado_negociacion = serializers.CharField()
    reserva_id = serializers.IntegerField()
    estado_reserva = serializers.CharField()
    monto_acordado = serializers.DecimalField(max_digits=12, decimal_places=2)


class NegociacionAcceptSerializer(serializers.Serializer):
    """Acción: aceptar una negociación (sin body)."""
    pass


class NegociacionRejectSerializer(serializers.Serializer):
    """Acción: rechazar una negociación (sin body)."""
    pass


class NegociacionCancelSerializer(serializers.Serializer):
    """Acción: cancelar una negociación (sin body)."""
    pass
