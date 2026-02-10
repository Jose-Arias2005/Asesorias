from __future__ import annotations

from django.db import connection, transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema

from .models import Clase, Calificacion, Llevo, Materia
from .serializers import (
    CalificacionCreateSerializer,
    ClaseCreateSerializer,
    ClaseEstadoPatchSerializer,
    ClaseReadSerializer,
    ClaseSearchResponseSerializer,
    CreateIdResponseSerializer,
    DeleteResponseSerializer,
    LlevoUpsertResponseSerializer,
    LlevoUpsertSerializer,
    MateriaSerializer,
    MateriaSuggestResponseSerializer,
    OkResponseSerializer,
)


@extend_schema(
    tags=["Materias"],
    parameters=[
        OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True, description="Prefijo (>=2)."),
        OpenApiParameter("carrera", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False, description="Filtro opcional."),
        OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, description="Default 10."),
    ],
    responses={200: MateriaSuggestResponseSerializer},
    examples=[
        OpenApiExample(
            "Ejemplo",
            value={"results": [{"id": 1, "nombre": "Matemática Discreta", "carrera": "ING", "ciclo_relativo": 3}]},
        )
    ],
)
class MateriaSuggestView(APIView):
    """Autocomplete de materias por prefijo."""

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        carrera = (request.query_params.get("carrera") or "").strip()
        limit = int(request.query_params.get("limit") or 10)

        if len(q) < 2:
            return Response({"results": []})

        qs = Materia.objects.all()
        if carrera:
            qs = qs.filter(carrera__iexact=carrera)

        qs = qs.filter(nombre__istartswith=q).order_by("nombre")[:limit]
        return Response({"results": MateriaSerializer(qs, many=True).data})


@extend_schema(tags=["Clases"], request=ClaseCreateSerializer, responses={201: ClaseReadSerializer})
class ClaseCreateView(APIView):
    """Crea una clase con horarios y creadores."""

    def post(self, request):
        ser = ClaseCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        clase = ser.save()
        return Response(ClaseReadSerializer(clase).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Clases"], responses={200: ClaseReadSerializer})
class ClaseDetailView(APIView):
    """Detalle de clase por id."""

    def get(self, request, clase_id: int):
        clase = (
            Clase.objects.select_related("materia")
            .prefetch_related("horarios", "creadores")
            .filter(id=clase_id)
            .first()
        )
        if not clase:
            return Response({"detail": "No encontrado"}, status=404)
        return Response(ClaseReadSerializer(clase).data)


@extend_schema(tags=["Clases"], request=ClaseEstadoPatchSerializer, responses={200: OkResponseSerializer})
class ClaseEstadoUpdateView(APIView):
    """Actualiza el estado de una clase."""

    def patch(self, request, clase_id: int):
        ser = ClaseEstadoPatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        updated = Clase.objects.filter(id=clase_id).update(estado=ser.validated_data["estado"])
        if not updated:
            return Response({"detail": "No encontrado"}, status=404)
        return Response({"ok": True})


@extend_schema(
    tags=["Clases"],
    parameters=[
        OpenApiParameter("materia_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True),
        OpenApiParameter("from", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False, description="fecha_inicio >= from"),
        OpenApiParameter(
            "dias",
            OpenApiTypes.INT,
            OpenApiParameter.QUERY,
            required=False,
            many=True,
            description="Días 0..6. Repetible: ?dias=1&dias=3",
        ),
        OpenApiParameter("hora_desde", OpenApiTypes.TIME, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("hora_hasta", OpenApiTypes.TIME, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, description="Default 20."),
        OpenApiParameter("offset", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, description="Default 0."),
    ],
    responses={200: ClaseSearchResponseSerializer},
)
class ClaseSearchView(APIView):
    """Búsqueda de clases PUBLICADAS futuras, rankeadas por cache de profesores."""

    def get(self, request):
        materia_id = request.query_params.get("materia_id")
        date_from = request.query_params.get("from")

        dias = request.query_params.getlist("dias")
        hora_desde = request.query_params.get("hora_desde")
        hora_hasta = request.query_params.get("hora_hasta")

        limit = int(request.query_params.get("limit") or 20)
        offset = int(request.query_params.get("offset") or 0)

        if not materia_id:
            return Response({"detail": "materia_id es requerido"}, status=400)

        where = [
            "cl.materia_id = %s",
            "cl.estado = %s",
            "cl.fecha_fin >= CURDATE()",
        ]
        params = [materia_id, Clase.Estado.PUBLICADA]

        if date_from:
            where.append("cl.fecha_inicio >= %s")
            params.append(date_from)

        if dias:
            in_days = ",".join(["%s"] * len(dias))
            horario_where = [
                "h.clase_id = cl.id",
                f"h.dia_semana IN ({in_days})",
            ]
            horario_params = list(map(int, dias))

            if hora_desde and hora_hasta:
                # Solape: [inicio, fin) con [desde, hasta)
                horario_where.append("h.hora_inicio < %s")
                horario_where.append("h.hora_fin > %s")
                horario_params.extend([hora_hasta, hora_desde])

            where.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM clase_horario h
                    WHERE {" AND ".join(horario_where)}
                )
                """
            )
            params.extend(horario_params)

        sql = f"""
        WITH filtered AS (
          SELECT
            cl.id, cl.materia_id, cl.fecha_inicio, cl.fecha_fin,
            cl.monto, cl.numero_participantes, cl.estado, cl.link_zoom
          FROM clase cl
          WHERE {" AND ".join(where)}
        )
        SELECT
          f.id,
          f.fecha_inicio, f.fecha_fin,
          f.monto, f.numero_participantes, f.estado, f.link_zoom,
          COALESCE(MAX(COALESCE(pr.avg_estrellas, 0)), 0) AS ranking
        FROM filtered f
        JOIN crea cr ON cr.clase_id = f.id
        LEFT JOIN profesor_rating_cache pr ON pr.profesor_id = cr.profesor_id
        GROUP BY f.id
        ORDER BY ranking DESC, f.fecha_inicio ASC
        LIMIT %s OFFSET %s
        """

        params.extend([limit, offset])

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        return Response({"results": rows, "limit": limit, "offset": offset})


@extend_schema(tags=["Calificaciones"], request=CalificacionCreateSerializer, responses={201: CreateIdResponseSerializer})
class CalificacionCreateView(APIView):
    """Crea una calificación (solo para clases FINALIZADAS)."""

    def post(self, request):
        ser = CalificacionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        cal = ser.save()
        return Response({"ok": True, "id": cal.id}, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Calificaciones"],
    parameters=[
        OpenApiParameter("alumno_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True),
        OpenApiParameter("clase_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True),
    ],
    responses={200: DeleteResponseSerializer},
)
class CalificacionDeleteView(APIView):
    """Elimina la calificación de (alumno_id, clase_id)."""

    def delete(self, request):
        alumno_id = request.query_params.get("alumno_id")
        clase_id = request.query_params.get("clase_id")
        if not alumno_id or not clase_id:
            return Response({"detail": "alumno_id y clase_id son requeridos"}, status=400)

        deleted, _ = Calificacion.objects.filter(alumno_id=alumno_id, clase_id=clase_id).delete()
        return Response({"ok": True, "deleted": deleted})


@extend_schema(tags=["Llevo"], request=LlevoUpsertSerializer, responses={200: LlevoUpsertResponseSerializer})
class LlevoUpsertView(APIView):
    """Upsert de 'profesor llevó materia'."""

    @transaction.atomic
    def put(self, request):
        ser = LlevoUpsertSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        data = ser.validated_data
        _, created = Llevo.objects.update_or_create(
            profesor_id=data["profesor_id"],
            materia=data["materia"],
            defaults={
                "promedio_ponderado": data.get("promedio_ponderado"),
                "ciclo_cursado": data["ciclo_cursado"],
                "profesor": data.get("profesor", ""),
            },
        )
        return Response({"ok": True, "created": created})
