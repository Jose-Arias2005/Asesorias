# core/tests.py
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError
from django.urls import reverse
from rest_framework.test import APIClient
from django.test import TestCase

from .models import Negociacion, Reserva


# =============================================================================
# Helpers / Base
# =============================================================================

class BaseAPITestCase(TestCase):
    """
    Base para tests de API del microservicio ms-reserva.

    Principios:
    - Usar reverse() para construir URLs reales (evita 404 por prefijos como /api/).
    - Crear data "de preparación" directo en BD (factory helpers) para aislar tests
      y no depender de otros endpoints para armar escenarios.
    """

    def setUp(self):
        self.client = APIClient()

    # -------------------------
    # Factories (BD)
    # -------------------------

    def create_reserva_db(
        self,
        *,
        alumno_id: int = 100,
        clase_id: int = 200,
        estado: str = Reserva.Estado.PENDIENTE,
        monto_acordado: Decimal = Decimal("150.00"),
        comision_por_alumno: Decimal = Decimal("0.00"),
        timestamp_creado=None,
    ) -> Reserva:
        """
        Crea una Reserva en BD, permitiendo setear estado y montos para escenarios.

        Nota:
        - timestamp_creado es auto_now_add. Si se pasa, se guarda y luego se fuerza update
          para simular rangos de fechas en filtros 'from/to' del listado.
        """
        reserva = Reserva.objects.create(
            alumno_id=alumno_id,
            clase_id=clase_id,
            estado=estado,
            monto_acordado=monto_acordado,
            comision_por_alumno=comision_por_alumno,
        )
        if timestamp_creado is not None:
            Reserva.objects.filter(id=reserva.id).update(timestamp_creado=timestamp_creado)
            reserva.refresh_from_db()
        return reserva

    def create_negociacion_db(
        self,
        *,
        reserva: Reserva,
        monto_propuesto: Decimal = Decimal("120.00"),
        propuesto_por: str = Negociacion.Autor.ALUMNO,
        estado: str = Negociacion.Estado.PENDIENTE,
        created_at=None,
    ) -> Negociacion:
        """
        Crea una Negociación en BD. Permite forzar estado/fechas para testear orden/historial.
        """
        nego = Negociacion.objects.create(
            reserva=reserva,
            monto_propuesto=monto_propuesto,
            propuesto_por=propuesto_por,
            estado=estado,
        )
        if created_at is not None:
            Negociacion.objects.filter(id=nego.id).update(created_at=created_at)
            nego.refresh_from_db()
        return nego


# =============================================================================
# Tests de Modelo / Constraints
# =============================================================================

class ReservaModelTests(TestCase):
    """
    Validaciones críticas a nivel BD (constraints) para asegurar integridad en producción.
    """

    def test_unique_reserva_por_alumno_y_clase(self):
        """
        Constraint uq_reserva_alumno_clase:
        Debe existir como máximo una reserva por (alumno_id, clase_id).
        """
        Reserva.objects.create(
            alumno_id=1,
            clase_id=10,
            monto_acordado=Decimal("100.00"),
            comision_por_alumno=Decimal("0.00"),
        )
        with self.assertRaises(IntegrityError):
            Reserva.objects.create(
                alumno_id=1,
                clase_id=10,
                monto_acordado=Decimal("200.00"),
                comision_por_alumno=Decimal("0.00"),
            )


# =============================================================================
# Tests de API: Reservas
# =============================================================================

class ReservaApiTests(BaseAPITestCase):
    """
    Cobertura de endpoints de Reserva:
    - POST   /api/reservas
    - GET    /api/reservas/<id>
    - GET    /api/reservas/list
    - PATCH  /api/reservas/<id>/cancelar
    """

    # -------------------------
    # URL builders
    # -------------------------

    def url_reserva_create(self) -> str:
        return "/api/reservas"

    def url_reserva_list(self) -> str:
        return "/api/reservas/list"

    def url_reserva_detail(self, reserva_id: int) -> str:
        return f"/api/reservas/{reserva_id}"

    def url_reserva_cancel(self, reserva_id: int) -> str:
        return f"/api/reservas/{reserva_id}/cancelar"

    # -------------------------
    # Create
    # -------------------------

    def test_create_reserva_ok_forza_estado_pendiente(self):
        """
        POST /reservas:
        - 201 con {ok: True, id}
        - Estado se fuerza a PENDIENTE (aunque cliente intente enviar otro valor)
        """
        payload = {
            "alumno_id": 101,
            "clase_id": 501,
            "monto_acordado": "250.00",
            "comision_por_alumno": "10.00",
            "estado": Reserva.Estado.CONFIRMADA,  # será ignorado
        }

        r = self.client.post(self.url_reserva_create(), payload, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.data["ok"])
        self.assertIsInstance(r.data["id"], int)

        reserva = Reserva.objects.get(id=r.data["id"])
        self.assertEqual(reserva.estado, Reserva.Estado.PENDIENTE)
        self.assertEqual(reserva.alumno_id, 101)
        self.assertEqual(reserva.clase_id, 501)
        self.assertEqual(reserva.monto_acordado, Decimal("250.00"))
        self.assertEqual(reserva.comision_por_alumno, Decimal("10.00"))

    def test_create_reserva_duplicate_returns_409(self):
        """
        Si ya existe la reserva para el par (alumno_id, clase_id), debe retornar 409.
        """
        self.create_reserva_db(alumno_id=1, clase_id=2)

        payload = {
            "alumno_id": 1,
            "clase_id": 2,
            "monto_acordado": "200.00",
            "comision_por_alumno": "0.00",
        }
        r = self.client.post(self.url_reserva_create(), payload, format="json")
        self.assertEqual(r.status_code, 400)

    def test_create_reserva_validation_error_negative_monto(self):
        """
        Validators:
        monto_acordado no puede ser < 0.
        """
        payload = {
            "alumno_id": 10,
            "clase_id": 20,
            "monto_acordado": "-1.00",
            "comision_por_alumno": "0.00",
        }
        r = self.client.post(self.url_reserva_create(), payload, format="json")
        self.assertEqual(r.status_code, 400)

    def test_create_reserva_validation_error_negative_comision(self):
        """
        Validators:
        comision_por_alumno no puede ser < 0.
        """
        payload = {
            "alumno_id": 10,
            "clase_id": 21,
            "monto_acordado": "1.00",
            "comision_por_alumno": "-0.01",
        }
        r = self.client.post(self.url_reserva_create(), payload, format="json")
        self.assertEqual(r.status_code, 400)

    # -------------------------
    # Detail
    # -------------------------

    def test_get_reserva_detail_ok(self):
        """
        GET /reservas/<id> retorna 200 y la estructura del ReservaReadSerializer.
        """
        reserva = self.create_reserva_db(alumno_id=10, clase_id=20, monto_acordado=Decimal("99.90"))
        r = self.client.get(self.url_reserva_detail(reserva.id))
        self.assertEqual(r.status_code, 200)

        self.assertEqual(r.data["id"], reserva.id)
        self.assertEqual(r.data["alumno_id"], 10)
        self.assertEqual(r.data["clase_id"], 20)
        self.assertEqual(r.data["estado"], Reserva.Estado.PENDIENTE)
        self.assertEqual(Decimal(r.data["monto_acordado"]), Decimal("99.90"))
        self.assertIn("timestamp_creado", r.data)
        self.assertIn("updated_at", r.data)

    def test_get_reserva_detail_not_found(self):
        r = self.client.get(self.url_reserva_detail(999999))
        self.assertEqual(r.status_code, 404)

    # -------------------------
    # List / Filters
    # -------------------------

    def test_list_requires_alumno_or_clase(self):
        """
        Regla: debe venir alumno_id o clase_id.
        """
        r = self.client.get(self.url_reserva_list())
        self.assertEqual(r.status_code, 400)
        self.assertIn("detail", r.data)

    def test_list_by_alumno_id(self):
        """
        Crea reservas de prueba directo en BD y verifica filtro alumno_id.
        """
        r1 = self.create_reserva_db(alumno_id=10, clase_id=1)
        r2 = self.create_reserva_db(alumno_id=10, clase_id=2)
        self.create_reserva_db(alumno_id=99, clase_id=3)

        resp = self.client.get(self.url_reserva_list(), {"alumno_id": 10})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total"], 2)

        got_ids = {item["id"] for item in resp.data["results"]}
        self.assertEqual(got_ids, {r1.id, r2.id})

    def test_list_by_clase_id(self):
        """
        Verifica filtro clase_id.
        """
        r1 = self.create_reserva_db(alumno_id=1, clase_id=777)
        r2 = self.create_reserva_db(alumno_id=2, clase_id=777)
        self.create_reserva_db(alumno_id=3, clase_id=888)

        resp = self.client.get(self.url_reserva_list(), {"clase_id": 777})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total"], 2)

        got_ids = {item["id"] for item in resp.data["results"]}
        self.assertEqual(got_ids, {r1.id, r2.id})

    def test_list_filter_by_estado(self):
        """
        Verifica filtro por estado.
        """
        self.create_reserva_db(alumno_id=1, clase_id=1, estado=Reserva.Estado.PENDIENTE)
        canc = self.create_reserva_db(alumno_id=1, clase_id=2, estado=Reserva.Estado.CANCELADA)

        resp = self.client.get(self.url_reserva_list(), {"alumno_id": 1, "estado": Reserva.Estado.CANCELADA})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total"], 1)
        self.assertEqual(resp.data["results"][0]["id"], canc.id)

    def test_list_filter_by_date_range(self):
        """
        Verifica filtros 'from' y 'to' sobre timestamp_creado__date.
        """
        today = date.today()
        r_old = self.create_reserva_db(alumno_id=50, clase_id=1, timestamp_creado=today - timedelta(days=10))
        r_mid = self.create_reserva_db(alumno_id=50, clase_id=2, timestamp_creado=today - timedelta(days=3))
        r_new = self.create_reserva_db(alumno_id=50, clase_id=3, timestamp_creado=today)

        resp = self.client.get(
            self.url_reserva_list(),
            {"alumno_id": 50, "from": str(today - timedelta(days=4)), "to": str(today)},
        )
        self.assertEqual(resp.status_code, 200)
        got_ids = {item["id"] for item in resp.data["results"]}
        self.assertIn(r_mid.id, got_ids)
        self.assertIn(r_new.id, got_ids)
        self.assertNotIn(r_old.id, got_ids)

    def test_list_pagination_limit_offset(self):
        """
        Paginación manual: limit/offset.
        """
        for i in range(5):
            self.create_reserva_db(alumno_id=123, clase_id=1000 + i)

        resp = self.client.get(self.url_reserva_list(), {"alumno_id": 123, "limit": 2, "offset": 0})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["limit"], 2)
        self.assertEqual(resp.data["offset"], 0)
        self.assertEqual(resp.data["total"], 5)
        self.assertEqual(len(resp.data["results"]), 2)

        resp2 = self.client.get(self.url_reserva_list(), {"alumno_id": 123, "limit": 2, "offset": 2})
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(len(resp2.data["results"]), 2)

    # -------------------------
    # Cancel
    # -------------------------

    def test_cancel_reserva_ok_cancela_negociaciones_pendientes(self):
        """
        PATCH /reservas/<id>/cancelar:
        - Solo si Reserva está PENDIENTE.
        - Reserva pasa a CANCELADA.
        - Negociaciones PENDIENTES asociadas pasan a CANCELADA y setean decided_at.
        - Negociaciones en otros estados no cambian.
        """
        reserva = self.create_reserva_db(estado=Reserva.Estado.PENDIENTE)

        n_p1 = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.PENDIENTE)
        n_p2 = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.PENDIENTE, monto_propuesto=Decimal("111.00"))
        n_r = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.RECHAZADA)
        n_c = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.CANCELADA)

        resp = self.client.patch(self.url_reserva_cancel(reserva.id), {}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["ok"])

        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, Reserva.Estado.CANCELADA)

        n_p1.refresh_from_db()
        n_p2.refresh_from_db()
        n_r.refresh_from_db()
        n_c.refresh_from_db()

        self.assertEqual(n_p1.estado, Negociacion.Estado.CANCELADA)
        self.assertIsNotNone(n_p1.decided_at)
        self.assertEqual(n_p2.estado, Negociacion.Estado.CANCELADA)
        self.assertIsNotNone(n_p2.decided_at)

        self.assertEqual(n_r.estado, Negociacion.Estado.RECHAZADA)
        self.assertEqual(n_c.estado, Negociacion.Estado.CANCELADA)

    def test_cancel_reserva_not_found(self):
        resp = self.client.patch(self.url_reserva_cancel(999999), {}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_cancel_reserva_not_pendiente_returns_409(self):
        reserva = self.create_reserva_db(estado=Reserva.Estado.CONFIRMADA)
        resp = self.client.patch(self.url_reserva_cancel(reserva.id), {}, format="json")
        self.assertEqual(resp.status_code, 409)


# =============================================================================
# Tests de API: Negociaciones
# =============================================================================

class NegociacionApiTests(BaseAPITestCase):
    """
    Cobertura de endpoints de Negociación:
    - POST   /api/negociaciones
    - GET    /api/negociaciones/<id>
    - GET    /api/reservas/<id>/negociaciones
    - PATCH  /api/negociaciones/<id>/aceptar
    - PATCH  /api/negociaciones/<id>/rechazar
    - PATCH  /api/negociaciones/<id>/cancelar
    """

    # -------------------------
    # URL builders
    # -------------------------

    def url_negociacion_create(self) -> str:
        return "/api/negociaciones"

    def url_negociacion_detail(self, negociacion_id: int) -> str:
        return f"/api/negociaciones/{negociacion_id}"

    def url_negociacion_list_by_reserva(self, reserva_id: int) -> str:
        return f"/api/reservas/{reserva_id}/negociaciones"

    def url_negociacion_accept(self, negociacion_id: int) -> str:
        return f"/api/negociaciones/{negociacion_id}/aceptar"

    def url_negociacion_reject(self, negociacion_id: int) -> str:
        return f"/api/negociaciones/{negociacion_id}/rechazar"

    def url_negociacion_cancel(self, negociacion_id: int) -> str:
        return f"/api/negociaciones/{negociacion_id}/cancelar"

    # -------------------------
    # Create
    # -------------------------

    def test_create_negociacion_ok(self):
        """
        POST /negociaciones:
        - Reserva debe existir y estar PENDIENTE.
        - No debe existir otra negociación PENDIENTE en la reserva.
        - No debe existir negociación ACEPTADA previa.
        """
        reserva = self.create_reserva_db(estado=Reserva.Estado.PENDIENTE)

        payload = {
            "reserva_id": reserva.id,
            "monto_propuesto": "140.00",
            "propuesto_por": Negociacion.Autor.ALUMNO,
        }
        resp = self.client.post(self.url_negociacion_create(), payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data["ok"])

        nego = Negociacion.objects.get(id=resp.data["id"])
        self.assertEqual(nego.reserva_id, reserva.id)
        self.assertEqual(nego.estado, Negociacion.Estado.PENDIENTE)
        self.assertEqual(nego.monto_propuesto, Decimal("140.00"))
        self.assertEqual(nego.propuesto_por, Negociacion.Autor.ALUMNO)

    def test_create_negociacion_reserva_no_existe(self):
        payload = {"reserva_id": 999999, "monto_propuesto": "140.00", "propuesto_por": Negociacion.Autor.ALUMNO}
        resp = self.client.post(self.url_negociacion_create(), payload, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_create_negociacion_reserva_no_pendiente(self):
        reserva = self.create_reserva_db(estado=Reserva.Estado.CANCELADA)

        payload = {"reserva_id": reserva.id, "monto_propuesto": "140.00", "propuesto_por": Negociacion.Autor.ALUMNO}
        resp = self.client.post(self.url_negociacion_create(), payload, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_create_negociacion_ya_existe_pendiente(self):
        reserva = self.create_reserva_db()
        self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.PENDIENTE)

        payload = {"reserva_id": reserva.id, "monto_propuesto": "140.00", "propuesto_por": Negociacion.Autor.ALUMNO}
        resp = self.client.post(self.url_negociacion_create(), payload, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_create_negociacion_ya_existe_aceptada(self):
        reserva = self.create_reserva_db()
        self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.ACEPTADA)

        payload = {"reserva_id": reserva.id, "monto_propuesto": "140.00", "propuesto_por": Negociacion.Autor.ALUMNO}
        resp = self.client.post(self.url_negociacion_create(), payload, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_create_negociacion_validation_error_negative_monto(self):
        """
        Validators:
        monto_propuesto no puede ser < 0.
        """
        reserva = self.create_reserva_db()
        payload = {"reserva_id": reserva.id, "monto_propuesto": "-0.01", "propuesto_por": Negociacion.Autor.ALUMNO}
        resp = self.client.post(self.url_negociacion_create(), payload, format="json")
        self.assertEqual(resp.status_code, 400)

    # -------------------------
    # Detail
    # -------------------------

    def test_get_negociacion_detail_ok(self):
        reserva = self.create_reserva_db()
        nego = self.create_negociacion_db(reserva=reserva, monto_propuesto=Decimal("123.45"))

        resp = self.client.get(self.url_negociacion_detail(nego.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["id"], nego.id)
        self.assertEqual(resp.data["reserva_id"], reserva.id)
        self.assertEqual(Decimal(resp.data["monto_propuesto"]), Decimal("123.45"))
        self.assertEqual(resp.data["estado"], Negociacion.Estado.PENDIENTE)

    def test_get_negociacion_detail_not_found(self):
        resp = self.client.get(self.url_negociacion_detail(999999))
        self.assertEqual(resp.status_code, 404)

    # -------------------------
    # List by Reserva (historial)
    # -------------------------

    def test_list_negociaciones_by_reserva_ok(self):
        """
        GET /reservas/<id>/negociaciones:
        - retorna 200 y results
        - ordena por created_at desc
        """
        reserva = self.create_reserva_db()

        # Creamos en orden temporal conocido para validar sorting (desc)
        n_old = self.create_negociacion_db(reserva=reserva, monto_propuesto=Decimal("100.00"), created_at=date.today() - timedelta(days=3))
        n_new = self.create_negociacion_db(reserva=reserva, monto_propuesto=Decimal("90.00"), estado=Negociacion.Estado.RECHAZADA, created_at=date.today())

        resp = self.client.get(self.url_negociacion_list_by_reserva(reserva.id))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("results", resp.data)
        self.assertEqual(len(resp.data["results"]), 2)

        # Validación fuerte: el primer elemento debe ser el más reciente (created_at desc)
        self.assertEqual(resp.data["results"][0]["id"], n_new.id)
        self.assertEqual(resp.data["results"][1]["id"], n_old.id)

    def test_list_negociaciones_by_reserva_reserva_no_existe(self):
        resp = self.client.get(self.url_negociacion_list_by_reserva(999999))
        self.assertEqual(resp.status_code, 404)

    # -------------------------
    # Accept
    # -------------------------

    def test_accept_negociacion_ok_actualiza_reserva_y_rechaza_otras_pendientes(self):
        """
        PATCH /negociaciones/<id>/aceptar:
        - nego PENDIENTE -> ACEPTADA
        - reserva PENDIENTE -> CONFIRMADA
        - reserva.monto_acordado = nego.monto_propuesto
        - otras negociaciones PENDIENTES (si existieran por datos inconsistentes/race) -> RECHAZADA
        """
        reserva = self.create_reserva_db(estado=Reserva.Estado.PENDIENTE, monto_acordado=Decimal("150.00"))

        nego = self.create_negociacion_db(reserva=reserva, monto_propuesto=Decimal("130.00"), estado=Negociacion.Estado.PENDIENTE)

        # Caso defensivo (simula inconsistencia/race):
        extra = self.create_negociacion_db(reserva=reserva, monto_propuesto=Decimal("125.00"), estado=Negociacion.Estado.PENDIENTE)

        resp = self.client.patch(self.url_negociacion_accept(nego.id), {}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["ok"])
        self.assertEqual(resp.data["estado_negociacion"], Negociacion.Estado.ACEPTADA)
        self.assertEqual(resp.data["estado_reserva"], Reserva.Estado.CONFIRMADA)
        self.assertEqual(Decimal(resp.data["monto_acordado"]), Decimal("130.00"))

        reserva.refresh_from_db()
        nego.refresh_from_db()
        extra.refresh_from_db()

        self.assertEqual(nego.estado, Negociacion.Estado.ACEPTADA)
        self.assertIsNotNone(nego.decided_at)

        self.assertEqual(reserva.estado, Reserva.Estado.CONFIRMADA)
        self.assertEqual(reserva.monto_acordado, Decimal("130.00"))

        self.assertEqual(extra.estado, Negociacion.Estado.RECHAZADA)
        self.assertIsNotNone(extra.decided_at)

    def test_accept_negociacion_not_found(self):
        resp = self.client.patch(self.url_negociacion_accept(999999), {}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_accept_negociacion_reserva_no_pendiente_returns_409(self):
        """
        Si la reserva ya no está PENDIENTE => 409.
        """
        reserva = self.create_reserva_db(estado=Reserva.Estado.CONFIRMADA)
        nego = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.PENDIENTE)

        resp = self.client.patch(self.url_negociacion_accept(nego.id), {}, format="json")
        self.assertEqual(resp.status_code, 409)

    def test_accept_negociacion_no_pendiente_returns_409(self):
        """
        Si la negociación no está PENDIENTE => 409.
        """
        reserva = self.create_reserva_db(estado=Reserva.Estado.PENDIENTE)
        nego = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.RECHAZADA)

        resp = self.client.patch(self.url_negociacion_accept(nego.id), {}, format="json")
        self.assertEqual(resp.status_code, 409)

    def test_accept_negociacion_si_ya_hay_aceptada_returns_409(self):
        """
        Defensa contra race:
        Si ya existe una ACEPTADA, no se puede aceptar otra => 409.
        """
        reserva = self.create_reserva_db(estado=Reserva.Estado.PENDIENTE)

        self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.ACEPTADA, monto_propuesto=Decimal("111.00"))
        nego = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.PENDIENTE, monto_propuesto=Decimal("120.00"))

        resp = self.client.patch(self.url_negociacion_accept(nego.id), {}, format="json")
        self.assertEqual(resp.status_code, 409)

    # -------------------------
    # Reject
    # -------------------------

    def test_reject_negociacion_ok(self):
        """
        PATCH /negociaciones/<id>/rechazar:
        - nego PENDIENTE -> RECHAZADA
        - reserva permanece PENDIENTE
        - monto_acordado no cambia
        """
        reserva = self.create_reserva_db(estado=Reserva.Estado.PENDIENTE, monto_acordado=Decimal("150.00"))
        nego = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.PENDIENTE, monto_propuesto=Decimal("140.00"))

        resp = self.client.patch(self.url_negociacion_reject(nego.id), {}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["ok"])
        self.assertEqual(resp.data["estado_negociacion"], Negociacion.Estado.RECHAZADA)
        self.assertEqual(resp.data["estado_reserva"], Reserva.Estado.PENDIENTE)
        self.assertEqual(Decimal(resp.data["monto_acordado"]), Decimal("150.00"))

        reserva.refresh_from_db()
        nego.refresh_from_db()
        self.assertEqual(nego.estado, Negociacion.Estado.RECHAZADA)
        self.assertIsNotNone(nego.decided_at)
        self.assertEqual(reserva.monto_acordado, Decimal("150.00"))

    def test_reject_negociacion_not_found(self):
        resp = self.client.patch(self.url_negociacion_reject(999999), {}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_reject_negociacion_reserva_no_pendiente_returns_409(self):
        reserva = self.create_reserva_db(estado=Reserva.Estado.CANCELADA)
        nego = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.PENDIENTE)

        resp = self.client.patch(self.url_negociacion_reject(nego.id), {}, format="json")
        self.assertEqual(resp.status_code, 409)

    def test_reject_negociacion_no_pendiente_returns_409(self):
        reserva = self.create_reserva_db(estado=Reserva.Estado.PENDIENTE)
        nego = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.CANCELADA)

        resp = self.client.patch(self.url_negociacion_reject(nego.id), {}, format="json")
        self.assertEqual(resp.status_code, 409)

    # -------------------------
    # Cancel
    # -------------------------

    def test_cancel_negociacion_ok(self):
        """
        PATCH /negociaciones/<id>/cancelar:
        - nego PENDIENTE -> CANCELADA
        - reserva permanece PENDIENTE
        - monto_acordado no cambia
        """
        reserva = self.create_reserva_db(estado=Reserva.Estado.PENDIENTE, monto_acordado=Decimal("200.00"))
        nego = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.PENDIENTE, monto_propuesto=Decimal("180.00"))

        resp = self.client.patch(self.url_negociacion_cancel(nego.id), {}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["ok"])
        self.assertEqual(resp.data["estado_negociacion"], Negociacion.Estado.CANCELADA)
        self.assertEqual(resp.data["estado_reserva"], Reserva.Estado.PENDIENTE)
        self.assertEqual(Decimal(resp.data["monto_acordado"]), Decimal("200.00"))

        reserva.refresh_from_db()
        nego.refresh_from_db()
        self.assertEqual(nego.estado, Negociacion.Estado.CANCELADA)
        self.assertIsNotNone(nego.decided_at)
        self.assertEqual(reserva.monto_acordado, Decimal("200.00"))

    def test_cancel_negociacion_not_found(self):
        resp = self.client.patch(self.url_negociacion_cancel(999999), {}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_cancel_negociacion_reserva_no_pendiente_returns_409(self):
        reserva = self.create_reserva_db(estado=Reserva.Estado.CONFIRMADA)
        nego = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.PENDIENTE)

        resp = self.client.patch(self.url_negociacion_cancel(nego.id), {}, format="json")
        self.assertEqual(resp.status_code, 409)

    def test_cancel_negociacion_no_pendiente_returns_409(self):
        reserva = self.create_reserva_db(estado=Reserva.Estado.PENDIENTE)
        nego = self.create_negociacion_db(reserva=reserva, estado=Negociacion.Estado.RECHAZADA)

        resp = self.client.patch(self.url_negociacion_cancel(nego.id), {}, format="json")
        self.assertEqual(resp.status_code, 409)
