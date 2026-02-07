from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Reserva(models.Model):
    """
    Reserva (sin FK externos):
    - alumno_id y clase_id son IDs externos (otros microservicios).
    - monto_acordado es el monto vigente (puede cambiar por negociación aceptada).
    """

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"       # creada, aún no confirmada
        CONFIRMADA = "CONFIRMADA", "Confirmada"    # acuerdo cerrado / pagado / confirmado (según orquestador)
        CANCELADA = "CANCELADA", "Cancelada"

    alumno_id = models.PositiveBigIntegerField()
    clase_id = models.PositiveBigIntegerField()

    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)

    monto_acordado = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    comision_por_alumno = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(0)]
    )

    timestamp_creado = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reserva"
        constraints = [
            models.UniqueConstraint(fields=["alumno_id", "clase_id"], name="uq_reserva_alumno_clase"),
        ]
        indexes = [
            models.Index(fields=["alumno_id", "timestamp_creado"], name="ix_reserva_alumno_ts"),
            models.Index(fields=["clase_id", "timestamp_creado"], name="ix_reserva_clase_ts"),
            models.Index(fields=["estado"], name="ix_reserva_estado"),
        ]


class Negociacion(models.Model):
    """
    Una negociación es UNA propuesta de monto dentro de una reserva.
    - Una reserva puede tener varias negociaciones (historial).
    - Regla de negocio: solo 1 PENDIENTE a la vez por reserva (la activa).
    """

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        ACEPTADA = "ACEPTADA", "Aceptada"
        RECHAZADA = "RECHAZADA", "Rechazada"
        CANCELADA = "CANCELADA", "Cancelada"

    class Autor(models.TextChoices):
        ALUMNO = "ALUMNO", "Alumno"
        PROFESOR = "PROFESOR", "Profesor"

    reserva = models.ForeignKey(Reserva, on_delete=models.CASCADE, related_name="negociaciones")

    monto_propuesto = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    propuesto_por = models.CharField(max_length=10, choices=Autor.choices)

    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)

    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "negociacion"
        indexes = [
            models.Index(fields=["reserva", "estado", "created_at"], name="ix_nego_reserva_estado_ts"),
        ]
