from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Materia(models.Model):
    """
    Materia académica (catálogo).
    """
    nombre = models.CharField(max_length=120)
    carrera = models.CharField(max_length=120)
    ciclo_relativo = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "materia"
        constraints = [
            # Evita duplicados dentro de la misma carrera
            models.UniqueConstraint(
                fields=["carrera", "nombre"],
                name="uq_materia_carrera_nombre",
            ),
        ]
        indexes = [
            models.Index(fields=["nombre"], name="ix_materia_nombre"),
        ]


class Clase(models.Model):
    """
    Publicación de una clase de asesoría para una materia (con fechas de vigencia).
    Los horarios se modelan en ClaseHorario.
    Los profesores participantes se modelan en Crea.
    """

    class Estado(models.TextChoices):
        PUBLICADA = "PUBLICADA", "Publicada"
        CANCELADA = "CANCELADA", "Cancelada"
        FINALIZADA = "FINALIZADA", "Finalizada"
        EN_PROGRESO = "EN_PROGRESO", "En progreso"

    materia = models.ForeignKey(Materia, on_delete=models.PROTECT, related_name="clases")
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PUBLICADA)

    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()

    monto = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    numero_participantes = models.PositiveIntegerField(default=1)
    link_zoom = models.URLField(blank=True)
    timestamp_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "clase"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(fecha_inicio__lte=models.F("fecha_fin")),
                name="ck_clase_rango_fechas",
            ),
        ]
        indexes = [
            models.Index(fields=["materia", "estado", "fecha_fin", "fecha_inicio"], name="ix_clase_m_e_ff_fi"),
        ]


class ClaseHorario(models.Model):
    """
    Bloque horario semanal asociado a una clase.
    dia_semana: 0..6 (según convención del API/test).
    """

    clase = models.ForeignKey(Clase, on_delete=models.CASCADE, related_name="horarios")

    dia_semana = models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(6)])
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    class Meta:
        db_table = "clase_horario"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hora_inicio__lt=models.F("hora_fin")),
                name="ck_horario_horas_validas",
            ),
        ]


class Crea(models.Model):
    """
    Relación profesor-clase (participación y reparto).
    Nota: profesor_id viene de un servicio externo (no FK local).
    """

    class Rol(models.TextChoices):
        CREADOR = "CREADOR", "Creador"
        COHOST = "COHOST", "Co-host"
        ASISTENTE = "ASISTENTE", "Asistente"

    profesor_id = models.PositiveBigIntegerField()
    clase = models.ForeignKey(Clase, on_delete=models.CASCADE, related_name="creadores")

    timestamp_creacion = models.DateTimeField(auto_now_add=True)

    comision_por_curso = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.CREADOR)
    porcentaje_reparto = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    class Meta:
        db_table = "crea"
        constraints = [
            models.UniqueConstraint(fields=["profesor_id", "clase"], name="uq_crea_profesor_clase"),
        ]
        indexes = [
            models.Index(fields=["clase"], name="ix_crea_clase"),
            models.Index(fields=["profesor_id"], name="ix_crea_profesor"),
        ]


class Calificacion(models.Model):
    """
    Calificación de un alumno a una clase (1..5).
    Nota: alumno_id viene de un servicio externo (no FK local).
    """

    alumno_id = models.PositiveBigIntegerField()
    clase = models.ForeignKey(Clase, on_delete=models.CASCADE, related_name="calificaciones")

    opinion = models.TextField(blank=True)
    estrellas = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])

    class Meta:
        db_table = "calificacion"
        constraints = [
            models.UniqueConstraint(fields=["alumno_id", "clase"], name="uq_calificacion_alumno_clase"),
        ]
        indexes = [
            models.Index(fields=["clase"], name="ix_calificacion_clase"),
            models.Index(fields=["alumno_id"], name="ix_calificacion_alumno"),
        ]


class Llevo(models.Model):
    """
    Registro “profesor llevó materia” (para dar contexto/credenciales).
    """

    profesor_id = models.PositiveBigIntegerField()
    materia = models.ForeignKey(Materia, on_delete=models.PROTECT, related_name="llevos")

    promedio_ponderado = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    ciclo_cursado = models.PositiveSmallIntegerField()
    profesor = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = "llevo"
        constraints = [
            models.UniqueConstraint(fields=["profesor_id", "materia"], name="uq_llevo_profesor_materia"),
        ]
        indexes = [
            models.Index(fields=["materia"], name="ix_llevo_materia"),
            models.Index(fields=["profesor_id"], name="ix_llevo_profesor"),
        ]


class ProfesorRatingCache(models.Model):
    """
    Cache materializado para ranking de profesores.

    Se mantiene por triggers MySQL sobre calificacion.
    Django no la migra (managed=False).
    """

    profesor_id = models.PositiveBigIntegerField(primary_key=True)
    sum_ponderada = models.DecimalField(max_digits=18, decimal_places=6)
    sum_pesos = models.DecimalField(max_digits=18, decimal_places=6)

    total_calificaciones = models.PositiveIntegerField()
    avg_estrellas = models.DecimalField(max_digits=6, decimal_places=3, null=True)

    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "profesor_rating_cache"
