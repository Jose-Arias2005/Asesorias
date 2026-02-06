from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from .models import Calificacion, Clase, ClaseHorario, Crea, Llevo, Materia


# -------------------------
# Responses “simples”
# -------------------------

class OkResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()


class CreateIdResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    id = serializers.IntegerField()


class DeleteResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    deleted = serializers.IntegerField()


# -------------------------
# Materia
# -------------------------

class MateriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Materia
        fields = ["id", "nombre", "carrera", "ciclo_relativo"]


class MateriaSuggestResponseSerializer(serializers.Serializer):
    results = MateriaSerializer(many=True)


# -------------------------
# Horarios
# -------------------------

class ClaseHorarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClaseHorario
        fields = ["dia_semana", "hora_inicio", "hora_fin"]

    def validate(self, attrs):
        if attrs["hora_inicio"] >= attrs["hora_fin"]:
            raise serializers.ValidationError("hora_inicio debe ser menor que hora_fin")
        return attrs


# -------------------------
# Creadores (input)
# -------------------------

class CreaInputSerializer(serializers.Serializer):
    profesor_id = serializers.IntegerField(min_value=1)
    rol = serializers.ChoiceField(choices=Crea.Rol.choices, required=False)
    porcentaje_reparto = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    comision_por_curso = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)

    def validate(self, attrs):
        pr = attrs.get("porcentaje_reparto")
        if pr is not None and (pr < 0 or pr > 100):
            raise serializers.ValidationError("porcentaje_reparto debe estar entre 0 y 100")
        return attrs


# -------------------------
# Clase
# -------------------------

class ClaseCreateSerializer(serializers.ModelSerializer):
    """
    Crea:
    - Clase
    - N horarios (ClaseHorario)
    - N creadores (Crea)
    """
    horarios = ClaseHorarioSerializer(many=True)
    creadores = CreaInputSerializer(many=True)

    class Meta:
        model = Clase
        fields = [
            "materia", "estado",
            "fecha_inicio", "fecha_fin",
            "monto", "numero_participantes", "link_zoom",
            "horarios", "creadores",
        ]

    def validate(self, attrs):
        if attrs["fecha_inicio"] > attrs["fecha_fin"]:
            raise serializers.ValidationError("fecha_inicio no puede ser mayor que fecha_fin")

        creadores = attrs.get("creadores") or []
        if not creadores:
            raise serializers.ValidationError("Debe existir al menos 1 profesor (creadores)")

        ids = [c["profesor_id"] for c in creadores]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("No puedes repetir profesor_id en la misma clase")

        # Si N>1, todos deben mandar porcentaje_reparto y sumar 100.00
        if len(creadores) == 1:
            # ok: puede venir o no venir
            pass
        else:
            if not all("porcentaje_reparto" in c for c in creadores):
                raise serializers.ValidationError("Si hay más de 1 profesor, todos deben enviar porcentaje_reparto")

            total = sum(Decimal(str(c["porcentaje_reparto"])) for c in creadores)
            if total.quantize(Decimal("0.00")) != Decimal("100.00"):
                raise serializers.ValidationError("La suma de porcentaje_reparto debe ser 100.00")


        horarios = attrs.get("horarios") or []
        if not horarios:
            raise serializers.ValidationError("Debe existir al menos 1 horario")

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        horarios_data = validated_data.pop("horarios")
        creadores_data = validated_data.pop("creadores")

        clase = Clase.objects.create(**validated_data)

        ClaseHorario.objects.bulk_create([ClaseHorario(clase=clase, **h) for h in horarios_data])

        crea_objs = []
        for c in creadores_data:
            crea_objs.append(
                Crea(
                    profesor_id=c["profesor_id"],
                    clase=clase,
                    rol=c.get("rol", Crea.Rol.CREADOR),
                    porcentaje_reparto=c.get(
                        "porcentaje_reparto",
                        Decimal("100.00"),
                    ),
                    comision_por_curso=c.get("comision_por_curso", Decimal("0")),
                )
            )
        Crea.objects.bulk_create(crea_objs)

        return clase


class ClaseReadSerializer(serializers.ModelSerializer):
    materia = MateriaSerializer()
    horarios = ClaseHorarioSerializer(many=True)
    creadores = serializers.SerializerMethodField()

    class Meta:
        model = Clase
        fields = [
            "id", "materia", "estado",
            "fecha_inicio", "fecha_fin",
            "monto", "numero_participantes", "link_zoom",
            "timestamp_creacion",
            "horarios", "creadores",
        ]

    def get_creadores(self, obj):
        return list(
            obj.creadores.all().values("profesor_id", "rol", "porcentaje_reparto", "comision_por_curso")
        )


class ClaseEstadoPatchSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=Clase.Estado.choices)


class ClaseSearchItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    fecha_inicio = serializers.DateField()
    fecha_fin = serializers.DateField()
    monto = serializers.DecimalField(max_digits=12, decimal_places=2)
    numero_participantes = serializers.IntegerField()
    estado = serializers.CharField()
    link_zoom = serializers.CharField(allow_blank=True, required=False)
    ranking = serializers.DecimalField(max_digits=6, decimal_places=3)


class ClaseSearchResponseSerializer(serializers.Serializer):
    results = ClaseSearchItemSerializer(many=True)
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()


# -------------------------
# Calificación
# -------------------------

class CalificacionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Calificacion
        fields = ["alumno_id", "clase", "opinion", "estrellas"]

    def validate(self, attrs):
        if attrs["clase"].estado != Clase.Estado.FINALIZADA:
            raise serializers.ValidationError("Solo se puede calificar una clase FINALIZADA")
        return attrs


# -------------------------
# Llevo
# -------------------------

class LlevoUpsertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Llevo
        fields = ["profesor_id", "materia", "promedio_ponderado", "ciclo_cursado", "profesor"]


class LlevoUpsertResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    created = serializers.BooleanField()
