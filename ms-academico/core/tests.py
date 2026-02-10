# core/tests.py
from __future__ import annotations

import json
import unittest
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, connection
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Calificacion, Clase, Crea, Materia, ProfesorRatingCache


# Defaults 
DEFAULT_HORARIOS = [
    # Martes (1) 18:00-20:00
    {"dia_semana": 1, "hora_inicio": "18:00:00", "hora_fin": "20:00:00"},
]

DEFAULT_CREADORES = [
    # 1 profesor con 100% participación por defecto
    {"profesor_id": 1001, "rol": "CREADOR", "porcentaje_reparto": "100.00"},
]


def _ensure_required_for_create(payload: dict) -> dict:
    """
    Inyecta horarios/creadores SOLO si no vienen.
    Útil para tests “ok” donde el foco no es validar esos campos.
    """
    p = deepcopy(payload)
    p.setdefault("horarios", DEFAULT_HORARIOS)
    p.setdefault("creadores", DEFAULT_CREADORES)
    return p


# ============================================================
# Helpers de precisión Decimal (para comparar con DECIMAL(6,3))
# ============================================================

def q3(x: Decimal) -> Decimal:
    """
    Normaliza a 3 decimales con ROUND_HALF_UP.
    Esto emula DECIMAL(6,3) de MySQL al comparar promedios.
    """
    return x.quantize(Decimal("0.000"), rounding=ROUND_HALF_UP)


def dec(x) -> Decimal:
    """
    Convierte valores (str/int/float/Decimal) a Decimal de forma segura.
    - Usamos str(x) para evitar problemas típicos de float binario.
    """
    return Decimal(str(x))


def iso(d) -> str:
    """
    Convierte date a "YYYY-MM-DD".
    Si ya es string, lo deja igual.
    """
    if isinstance(d, date):
        return d.isoformat()
    return str(d)


# ============================================================
# Helpers BD / MySQL para triggers
# ============================================================

def _is_mysql() -> bool:
    # connection.vendor = "mysql" / "sqlite" / "postgresql" etc.
    return connection.vendor == "mysql"


def _table_exists(table_name: str) -> bool:
    """
    Valida que exista una tabla en la BD actual.
    (Se usa para saber si la migración que crea profesor_rating_cache corrió.)
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = %s
            LIMIT 1
            """,
            [table_name],
        )
        return cursor.fetchone() is not None


def _trigger_exists(trigger_name: str) -> bool:
    """
    Valida que exista un trigger en la BD actual.
    Si el usuario de MySQL no tiene permiso TRIGGER, esto suele fallar o no crear triggers.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.triggers
            WHERE trigger_schema = DATABASE()
              AND trigger_name = %s
            LIMIT 1
            """,
            [trigger_name],
        )
        return cursor.fetchone() is not None


# ============================================================
# Base TestCase con helper JSON “real”
# ============================================================

class BaseAPITestCase(TestCase):
    """
    Usamos APIClient en TODOS los tests para:
    - soportar format="json"
    - enviar JSON real (application/json)
    - evitar que listas de dict se “pierdan” por form-encoding
    """

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def request_json(self, method: str, url: str, payload: dict | None = None):
        """
        Envía payload como JSON "real".

        Líneas clave:
        - json.dumps(payload) convierte dict -> string JSON
        - content_type="application/json" obliga a DRF a parsear como JSON
        - getattr(self.client, method) permite usar "get"/"post"/"patch"/"delete"
        """
        data = json.dumps(payload or {})
        return getattr(self.client, method)(
            url,
            data=data,
            content_type="application/json",
        )


# ============================================================
# 1) Materias: Suggest
# ============================================================

class MateriaSuggestTests(BaseAPITestCase):
    @classmethod
    def setUpTestData(cls):
        """
        setUpTestData crea datos UNA sola vez para esta clase de tests (más rápido).
        """
        data = [
            ("Matematica Basica", "ING", 1),
            ("Matematica Discreta", "ING", 3),
            ("Matematica Financiera", "ADM", 4),
            ("Matematica I", "ING", 1),
            ("Matematica II", "ING", 2),
            ("Mates Aplicadas", "ING", 2),
            ("Microeconomia", "ADM", 2),
            ("Metodos Numericos", "ING", 5),
            ("Programacion I", "ING", 1),
            ("Quimica", "ING", 1),
        ]
        for nombre, carrera, ciclo in data:
            Materia.objects.create(nombre=nombre, carrera=carrera, ciclo_relativo=ciclo)

    def test_suggest_devuelve_vacio_si_prefijo_menor_a_2(self):
        """
        Si q tiene longitud < 2 => el endpoint debe devolver results=[].
        """
        r = self.client.get("/api/materias/suggest", {"q": "m"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["results"], [])

    def test_suggest_prefijo_case_insensitive_y_ordenado(self):
        """
        Debe:
        - filtrar por prefijo "MA" ignorando mayúsculas/minúsculas
        - devolver ordenado ascendente por nombre
        """
        r = self.client.get("/api/materias/suggest", {"q": "MA"})
        self.assertEqual(r.status_code, 200)

        results = r.json()["results"]
        self.assertTrue(all(x["nombre"].lower().startswith("ma") for x in results))

        nombres = [x["nombre"] for x in results]
        self.assertEqual(nombres, sorted(nombres))

    def test_suggest_filtra_por_carrera(self):
        """
        carrera=ING debe filtrar resultados a esa carrera.
        """
        r = self.client.get("/api/materias/suggest", {"q": "mate", "carrera": "ING"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(all(x["carrera"] == "ING" for x in r.json()["results"]))

    def test_suggest_respetar_limit(self):
        """
        limit debe recortar resultados.
        """
        r = self.client.get("/api/materias/suggest", {"q": "ma", "limit": 2})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["results"]), 2)


# ============================================================
# 2) Endpoints + Validaciones (sin depender de triggers)
# ============================================================

class EndpointsValidationTests(BaseAPITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.materia = Materia.objects.create(nombre="Probabilidad", carrera="ING", ciclo_relativo=4)

    # ---------- Helper: crea clase por API ----------
    def _create_clase(self, payload: dict, expected_status: int = 201):
        """
        Helper para POST /api/clases.
        - Si esperamos 201, inyectamos defaults para no fallar por falta de campos requeridos.
        """
        if expected_status == 201:
            payload = _ensure_required_for_create(payload)

        r = self.request_json("post", "/api/clases", payload)
        self.assertEqual(r.status_code, expected_status, r.json() if r.content else None)
        return r

    def test_crear_clase_ok_1_profesor_1_horario(self):
        """
        Caso feliz:
        - Crea una clase con 1 horario y 1 creador.
        - Verifica respuesta: id, materia embebida, y rol default = CREADOR.
        """
        today = date.today()
        payload = {
            "materia": self.materia.id,
            "estado": "PUBLICADA",
            "fecha_inicio": iso(today + timedelta(days=5)),
            "fecha_fin": iso(today + timedelta(days=5)),
            "monto": "120.00",
            "numero_participantes": 10,
            "link_zoom": "",
            "horarios": [{"dia_semana": 1, "hora_inicio": "18:00:00", "hora_fin": "20:00:00"}],
            "creadores": [{"profesor_id": 10, "porcentaje_reparto": "100.00"}],  # rol opcional
        }
        r = self._create_clase(payload, 201)

        body = r.json()
        self.assertIn("id", body)
        self.assertEqual(body["materia"]["id"], self.materia.id)
        self.assertEqual(len(body["horarios"]), 1)
        self.assertEqual(len(body["creadores"]), 1)
        self.assertEqual(body["creadores"][0]["rol"], "CREADOR")

    def test_crear_clase_falla_si_fecha_inicio_mayor_que_fecha_fin(self):
        """
        fecha_inicio > fecha_fin debe fallar (validate() del serializer).
        """
        today = date.today()
        payload = {
            "materia": self.materia.id,
            "estado": "PUBLICADA",
            "fecha_inicio": iso(today + timedelta(days=10)),
            "fecha_fin": iso(today + timedelta(days=5)),
            "monto": "120.00",
            "numero_participantes": 10,
            "horarios": DEFAULT_HORARIOS,
            "creadores": [{"profesor_id": 10, "porcentaje_reparto": "100.00"}],
        }
        self._create_clase(payload, 400)

    def test_crear_clase_falla_si_no_hay_horarios(self):
        """
        horarios=[] debe fallar (regla del serializer: al menos 1 horario).
        """
        today = date.today()
        payload = {
            "materia": self.materia.id,
            "estado": "PUBLICADA",
            "fecha_inicio": iso(today + timedelta(days=5)),
            "fecha_fin": iso(today + timedelta(days=5)),
            "monto": "120.00",
            "numero_participantes": 10,
            "horarios": [],
            "creadores": [{"profesor_id": 10, "porcentaje_reparto": "100.00"}],
        }
        self._create_clase(payload, 400)

    def test_crear_clase_falla_si_no_hay_creadores(self):
        """
        creadores=[] debe fallar (regla del serializer: al menos 1 profesor).
        """
        today = date.today()
        payload = {
            "materia": self.materia.id,
            "estado": "PUBLICADA",
            "fecha_inicio": iso(today + timedelta(days=5)),
            "fecha_fin": iso(today + timedelta(days=5)),
            "monto": "120.00",
            "numero_participantes": 10,
            "horarios": DEFAULT_HORARIOS,
            "creadores": [],
        }
        self._create_clase(payload, 400)

    def test_crear_clase_falla_si_profesor_duplicado_en_misma_clase(self):
        """
        No se puede repetir profesor_id dentro de la misma clase.
        """
        today = date.today()
        payload = {
            "materia": self.materia.id,
            "estado": "PUBLICADA",
            "fecha_inicio": iso(today + timedelta(days=5)),
            "fecha_fin": iso(today + timedelta(days=5)),
            "monto": "120.00",
            "numero_participantes": 10,
            "horarios": DEFAULT_HORARIOS,
            "creadores": [
                {"profesor_id": 10, "porcentaje_reparto": "50.00"},
                {"profesor_id": 10, "porcentaje_reparto": "50.00"},
            ],
        }
        self._create_clase(payload, 400)

    def test_crear_clase_falla_si_suma_porcentajes_no_es_100(self):
        """
        Si se envía porcentaje_reparto, la suma debe ser exactamente 100.
        """
        today = date.today()
        payload = {
            "materia": self.materia.id,
            "estado": "PUBLICADA",
            "fecha_inicio": iso(today + timedelta(days=5)),
            "fecha_fin": iso(today + timedelta(days=5)),
            "monto": "120.00",
            "numero_participantes": 10,
            "horarios": DEFAULT_HORARIOS,
            "creadores": [
                {"profesor_id": 10, "porcentaje_reparto": "60.00"},
                {"profesor_id": 20, "porcentaje_reparto": "30.00"},
            ],
        }
        self._create_clase(payload, 400)

    def test_crear_clase_falla_si_porcentaje_fuera_de_rango(self):
        """
        porcentaje_reparto fuera de [0,100] debe fallar.
        """
        today = date.today()
        payload = {
            "materia": self.materia.id,
            "estado": "PUBLICADA",
            "fecha_inicio": iso(today + timedelta(days=5)),
            "fecha_fin": iso(today + timedelta(days=5)),
            "monto": "120.00",
            "numero_participantes": 10,
            "horarios": DEFAULT_HORARIOS,
            "creadores": [{"profesor_id": 10, "porcentaje_reparto": "150.00"}],
        }
        self._create_clase(payload, 400)

    def test_crear_clase_falla_si_horas_invalidas(self):
        """
        hora_inicio >= hora_fin debe fallar.
        """
        today = date.today()
        payload = {
            "materia": self.materia.id,
            "estado": "PUBLICADA",
            "fecha_inicio": iso(today + timedelta(days=5)),
            "fecha_fin": iso(today + timedelta(days=5)),
            "monto": "120.00",
            "numero_participantes": 10,
            "horarios": [{"dia_semana": 1, "hora_inicio": "20:00:00", "hora_fin": "20:00:00"}],
            "creadores": [{"profesor_id": 10, "porcentaje_reparto": "100.00"}],
        }
        self._create_clase(payload, 400)

    def test_crear_clase_falla_si_dia_semana_fuera_de_rango(self):
        """
        dia_semana debe estar en [0..6].
        """
        today = date.today()
        payload = {
            "materia": self.materia.id,
            "estado": "PUBLICADA",
            "fecha_inicio": iso(today + timedelta(days=5)),
            "fecha_fin": iso(today + timedelta(days=5)),
            "monto": "120.00",
            "numero_participantes": 10,
            "horarios": [{"dia_semana": 9, "hora_inicio": "18:00:00", "hora_fin": "20:00:00"}],
            "creadores": [{"profesor_id": 10, "porcentaje_reparto": "100.00"}],
        }
        self._create_clase(payload, 400)

    def test_clase_detail_ok_y_404(self):
        """
        - Crea una clase
        - GET /api/clases/{id} debe devolverla
        - GET a un id inexistente => 404
        """
        today = date.today()
        r = self._create_clase(
            {
                "materia": self.materia.id,
                "estado": "PUBLICADA",
                "fecha_inicio": iso(today + timedelta(days=5)),
                "fecha_fin": iso(today + timedelta(days=6)),
                "monto": "120.00",
                "numero_participantes": 10,
                "horarios": [{"dia_semana": 2, "hora_inicio": "18:00:00", "hora_fin": "20:00:00"}],
                "creadores": [{"profesor_id": 10, "porcentaje_reparto": "100.00"}],
            },
            201,
        )
        clase_id = r.json()["id"]

        ok = self.client.get(f"/api/clases/{clase_id}")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["id"], clase_id)

        not_found = self.client.get("/api/clases/999999")
        self.assertEqual(not_found.status_code, 404)

    def test_patch_estado_ok_invalido_y_404(self):
        """
        PATCH /api/clases/{id}/estado:
        - estado inválido => 400
        - estado válido => 200 + ok=True
        - id inexistente => 404
        """
        today = date.today()
        r = self._create_clase(
            {
                "materia": self.materia.id,
                "estado": "PUBLICADA",
                "fecha_inicio": iso(today + timedelta(days=5)),
                "fecha_fin": iso(today + timedelta(days=5)),
                "monto": "120.00",
                "numero_participantes": 10,
                "horarios": DEFAULT_HORARIOS,
                "creadores": [{"profesor_id": 10, "porcentaje_reparto": "100.00"}],
            },
            201,
        )
        clase_id = r.json()["id"]

        bad = self.request_json("patch", f"/api/clases/{clase_id}/estado", {"estado": "XXX"})
        self.assertEqual(bad.status_code, 400)

        ok = self.request_json("patch", f"/api/clases/{clase_id}/estado", {"estado": "CANCELADA"})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["ok"])

        missing = self.request_json("patch", "/api/clases/999999/estado", {"estado": "CANCELADA"})
        self.assertEqual(missing.status_code, 404)

    def test_calificacion_se_permite_solo_si_finalizada(self):
        """
        /api/calificaciones:
        - Si la clase NO está FINALIZADA => 400
        - Si la clase está FINALIZADA => 201
        """
        today = date.today()

        r_pub = self._create_clase(
            {
                "materia": self.materia.id,
                "estado": "PUBLICADA",
                "fecha_inicio": iso(today + timedelta(days=1)),
                "fecha_fin": iso(today + timedelta(days=1)),
                "monto": "120.00",
                "numero_participantes": 10,
                "horarios": DEFAULT_HORARIOS,
                "creadores": [{"profesor_id": 10, "porcentaje_reparto": "100.00"}],
            },
            201,
        )
        clase_pub = r_pub.json()["id"]

        bad = self.client.post("/api/calificaciones", {"alumno_id": 1, "clase": clase_pub, "estrellas": 5}, format="json")
        self.assertEqual(bad.status_code, 400)

        r_fin = self._create_clase(
            {
                "materia": self.materia.id,
                "estado": "FINALIZADA",
                "fecha_inicio": iso(today - timedelta(days=2)),
                "fecha_fin": iso(today - timedelta(days=2)),
                "monto": "120.00",
                "numero_participantes": 10,
                "horarios": [{"dia_semana": 2, "hora_inicio": "18:00:00", "hora_fin": "20:00:00"}],
                "creadores": [{"profesor_id": 10, "porcentaje_reparto": "100.00"}],
            },
            201,
        )
        clase_fin = r_fin.json()["id"]

        ok = self.client.post("/api/calificaciones", {"alumno_id": 1, "clase": clase_fin, "estrellas": 5}, format="json")
        self.assertEqual(ok.status_code, 201)

    def test_unique_calificacion_alumno_clase_en_bd(self):
        """
        Constraint uq_calificacion_alumno_clase:
        un alumno solo puede calificar 1 vez la misma clase.
        """
        today = date.today()

        clase = Clase.objects.create(
            materia=self.materia,
            estado="FINALIZADA",
            fecha_inicio=today - timedelta(days=1),
            fecha_fin=today - timedelta(days=1),
            monto=Decimal("100.00"),
            numero_participantes=10,
            link_zoom="",
        )
        Crea.objects.create(profesor_id=10, clase=clase, porcentaje_reparto=Decimal("100.00"))

        Calificacion.objects.create(alumno_id=999, clase=clase, estrellas=5, opinion="")
        with self.assertRaises(IntegrityError):
            Calificacion.objects.create(alumno_id=999, clase=clase, estrellas=4, opinion="")


# ============================================================
# 3) Trigger + Cache + Search (E2E real en MySQL)
# ============================================================

@unittest.skipUnless(_is_mysql(), "Estos tests requieren MySQL (triggers + CURDATE()).")
class TriggerCacheAndSearchTests(BaseAPITestCase):
    """
    Objetivo:
    - Validar triggers AFTER INSERT/DELETE en calificacion que mantienen profesor_rating_cache
    - Validar /api/clases/search rankeado por avg_estrellas (cache)

    Por qué estos tests detectan bugs reales:
    - Usan porcentajes distintos (70/30, 80/20)
    - Usan múltiples clases y luego borrado (prueba que el promedio se recalcula bien)
    - Verifican sum_pesos y total_calificaciones (no solo avg)
    """

    @classmethod
    def setUpTestData(cls):
        cls.materia_hist = Materia.objects.create(nombre="Historia", carrera="HUM", ciclo_relativo=1)
        cls.materia_search = Materia.objects.create(nombre="Probabilidad", carrera="ING", ciclo_relativo=4)

        # IDs externos de profesores
        cls.prof_a = 101
        cls.prof_b = 202
        cls.prof_c = 303
        cls.prof_nuevo = 404

        # alumnos
        cls.al_1, cls.al_2, cls.al_3 = 1001, 1002, 1003

    def setUp(self):
        super().setUp()

        # Infraestructura: tabla cache y triggers existen.
        # Si no existen => skip (esto pasa cuando MySQL user no tiene permiso TRIGGER).
        if not _table_exists("profesor_rating_cache"):
            raise unittest.SkipTest("No existe profesor_rating_cache en la BD de test (migración no aplicada).")
        if not (_trigger_exists("trg_calificacion_ai") and _trigger_exists("trg_calificacion_ad")):
            raise unittest.SkipTest("No existen triggers trg_calificacion_ai/ad en la BD de test (sin permisos TRIGGER).")

        # Limpieza: managed=False => Django no borra automáticamente esta tabla entre tests.
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM profesor_rating_cache")

    # -------------------------
    # Helpers API (claros y cortos)
    # -------------------------

    def _create_clase_api(self, *, materia_id, estado, fi, ff, horarios=None, creadores=None) -> int:
        """
        Crea clase por API y devuelve id.

        Nota: usamos request_json() para que "horarios" y "creadores" (listas de dict)
        lleguen bien al serializer.
        """
        payload = {
            "materia": materia_id,
            "estado": estado,
            "fecha_inicio": iso(fi),
            "fecha_fin": iso(ff),
            "monto": "100.00",
            "numero_participantes": 1,
            "link_zoom": "",
            "horarios": horarios if horarios is not None else DEFAULT_HORARIOS,
            "creadores": creadores if creadores is not None else DEFAULT_CREADORES,
        }
        r = self.request_json("post", "/api/clases", payload)
        self.assertEqual(r.status_code, 201, r.json() if r.content else None)
        return r.json()["id"]

    def _post_calif(self, *, alumno_id, clase_id, estrellas) -> int:
        """
        POST /api/calificaciones
        Dispara trigger AFTER INSERT en MySQL.
        """
        r = self.client.post(
            "/api/calificaciones",
            {"alumno_id": alumno_id, "clase": clase_id, "estrellas": estrellas},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.json())
        return r.json()["id"]

    def _del_calif(self, *, alumno_id, clase_id):
        """
        DELETE /api/calificaciones/delete?alumno_id=...&clase_id=...
        Dispara trigger AFTER DELETE en MySQL.
        """
        r = self.client.delete(f"/api/calificaciones/delete?alumno_id={alumno_id}&clase_id={clase_id}")
        self.assertEqual(r.status_code, 200, r.json())
        return r.json()

    def _cache(self, profesor_id):
        return ProfesorRatingCache.objects.filter(profesor_id=profesor_id).first()

    def _assert_cache(self, profesor_id, *, avg, sum_pesos=None, total=None):
        """
        Assert central:
        - existe fila en cache
        - avg coincide a 3 decimales
        - opcional: sum_pesos y total_calificaciones

        Líneas “complejas” explicadas:
        - q3(dec(row.avg_estrellas)) normaliza a 3 decimales porque MySQL DECIMAL(6,3)
        - dec(...) evita problemas por floats / strings
        """
        row = self._cache(profesor_id)
        self.assertIsNotNone(row, f"No existe cache para profesor_id={profesor_id}")

        self.assertEqual(q3(dec(row.avg_estrellas)), q3(dec(avg)))

        if sum_pesos is not None:
            self.assertEqual(q3(dec(row.sum_pesos)), q3(dec(sum_pesos)))

        if total is not None:
            self.assertEqual(row.total_calificaciones, total)

    # ============================================================
    # TRIGGERS: INSERT / DELETE
    # ============================================================

    def test_trigger_insert_ignora_clase_no_finalizada(self):
        """
        Caso:
        - Clase PUBLICADA
        - Insertamos calificación por ORM (para bypass del endpoint que la bloquearía)
        Esperado:
        - El trigger NO debe crear cache si clase.estado != FINALIZADA
        """
        today = date.today()
        clase_id = self._create_clase_api(
            materia_id=self.materia_hist.id,
            estado="PUBLICADA",
            fi=today + timedelta(days=1),
            ff=today + timedelta(days=1),
            creadores=[{"profesor_id": self.prof_a, "porcentaje_reparto": "100.00"}],
        )
        clase = Clase.objects.get(id=clase_id)

        # Insert directo por ORM: en DB se ejecuta INSERT => dispara trigger.
        Calificacion.objects.create(alumno_id=9999, clase=clase, estrellas=5, opinion="")
        self.assertIsNone(self._cache(self.prof_a), "No debió crear cache si clase no es FINALIZADA")

    def test_trigger_insert_distribuye_a_varios_profesores(self):
        """
        Detecta errores de “distribución” por porcentaje:
        - 1 calificación en clase con 2 profes (70/30)
        - estrellas = 4

        Esperado:
        - prof_a: pesos=0.7, avg=4.000
        - prof_b: pesos=0.3, avg=4.000

        Nota:
        avg debe quedar EXACTO en 4 porque sum_ponderada/pesos da 4.
        """
        today = date.today()
        clase_id = self._create_clase_api(
            materia_id=self.materia_hist.id,
            estado="FINALIZADA",
            fi=today - timedelta(days=2),
            ff=today - timedelta(days=2),
            creadores=[
                {"profesor_id": self.prof_a, "porcentaje_reparto": "70.00"},
                {"profesor_id": self.prof_b, "porcentaje_reparto": "30.00"},
            ],
        )
        self._post_calif(alumno_id=self.al_1, clase_id=clase_id, estrellas=4)

        self._assert_cache(self.prof_a, avg="4.000", sum_pesos="0.700", total=1)
        self._assert_cache(self.prof_b, avg="4.000", sum_pesos="0.300", total=1)

    def test_trigger_promedio_ponderado_multi_clase_y_delete_revierte(self):
        """
        Detecta el bug típico que tuvieron tus triggers: avg mal recalculado.

        Escenario:
        - Clase 1: prof_b 100%, estrellas=1   => aporta sum=1.0, peso=1.0
        - Clase 2: prof_b 20%,  estrellas=5   => aporta sum=1.0, peso=0.2

        Para prof_b:
          sum_total   = 1.0 + 1.0 = 2.0
          pesos_total = 1.0 + 0.2 = 1.2
          avg         = 2 / 1.2 = 1.666... => 1.667

        Luego BORRAMOS la calificación de la Clase 2:
          prof_b vuelve a:
          sum=1.0, pesos=1.0, avg=1.000
        """
        today = date.today()

        c1 = self._create_clase_api(
            materia_id=self.materia_hist.id,
            estado="FINALIZADA",
            fi=today - timedelta(days=10),
            ff=today - timedelta(days=10),
            creadores=[{"profesor_id": self.prof_b, "porcentaje_reparto": "100.00"}],
        )
        self._post_calif(alumno_id=self.al_1, clase_id=c1, estrellas=1)

        c2 = self._create_clase_api(
            materia_id=self.materia_hist.id,
            estado="FINALIZADA",
            fi=today - timedelta(days=9),
            ff=today - timedelta(days=9),
            creadores=[
                {"profesor_id": self.prof_a, "porcentaje_reparto": "80.00"},
                {"profesor_id": self.prof_b, "porcentaje_reparto": "20.00"},
            ],
        )
        self._post_calif(alumno_id=self.al_2, clase_id=c2, estrellas=5)

        self._assert_cache(self.prof_b, avg="1.667", sum_pesos="1.200", total=2)
        self._assert_cache(self.prof_a, avg="5.000", sum_pesos="0.800", total=1)

        out = self._del_calif(alumno_id=self.al_2, clase_id=c2)
        self.assertEqual(out["deleted"], 1)

        self._assert_cache(self.prof_b, avg="1.000", sum_pesos="1.000", total=1)

    def test_trigger_delete_borra_fila_cache_si_queda_en_cero(self):
        """
        Si un profesor queda con total_calificaciones <= 0 o sum_pesos <= 0,
        la fila cache debe borrarse.
        """
        today = date.today()
        clase_id = self._create_clase_api(
            materia_id=self.materia_hist.id,
            estado="FINALIZADA",
            fi=today - timedelta(days=3),
            ff=today - timedelta(days=3),
            creadores=[{"profesor_id": self.prof_c, "porcentaje_reparto": "100.00"}],
        )

        self._post_calif(alumno_id=self.al_1, clase_id=clase_id, estrellas=5)
        self._assert_cache(self.prof_c, avg="5.000", sum_pesos="1.000", total=1)

        self._del_calif(alumno_id=self.al_1, clase_id=clase_id)
        self.assertIsNone(self._cache(self.prof_c), "La fila debió borrarse al quedar total<=0")

    # ============================================================
    # SEARCH: ranking + filtros
    # ============================================================

    def test_search_orden_por_ranking_y_tie_break_por_fecha_inicio(self):
        """
        End-to-end REAL del search:

        - Creamos historial (FINALIZADA) para que prof_a tenga ranking alto (5.000).
        - Luego creamos 2 clases PUBLICADAS (mismo prof => mismo ranking)
          con fechas distintas => tie-break por fecha_inicio ASC.
        - Creamos otra clase con prof_nuevo sin cache => ranking 0.
        """
        today = date.today()

        # Historial para poblar cache del prof_a (2 calificaciones de 5)
        c_hist = self._create_clase_api(
            materia_id=self.materia_hist.id,
            estado="FINALIZADA",
            fi=today - timedelta(days=20),
            ff=today - timedelta(days=20),
            creadores=[{"profesor_id": self.prof_a, "porcentaje_reparto": "100.00"}],
        )
        self._post_calif(alumno_id=self.al_1, clase_id=c_hist, estrellas=5)
        self._post_calif(alumno_id=self.al_2, clase_id=c_hist, estrellas=5)
        self._assert_cache(self.prof_a, avg="5.000", sum_pesos="2.000", total=2)

        # Dos clases PUBLICADAS futuras: misma ranking, distinta fecha_inicio
        c_late = self._create_clase_api(
            materia_id=self.materia_search.id,
            estado="PUBLICADA",
            fi=today + timedelta(days=10),
            ff=today + timedelta(days=10),
            horarios=[{"dia_semana": 1, "hora_inicio": "19:00:00", "hora_fin": "21:00:00"}],
            creadores=[{"profesor_id": self.prof_a, "porcentaje_reparto": "100.00"}],
        )
        c_early = self._create_clase_api(
            materia_id=self.materia_search.id,
            estado="PUBLICADA",
            fi=today + timedelta(days=9),
            ff=today + timedelta(days=9),
            horarios=[{"dia_semana": 1, "hora_inicio": "19:00:00", "hora_fin": "21:00:00"}],
            creadores=[{"profesor_id": self.prof_a, "porcentaje_reparto": "100.00"}],
        )
        c_zero = self._create_clase_api(
            materia_id=self.materia_search.id,
            estado="PUBLICADA",
            fi=today + timedelta(days=12),
            ff=today + timedelta(days=12),
            creadores=[{"profesor_id": self.prof_nuevo, "porcentaje_reparto": "100.00"}],
        )

        r = self.client.get("/api/clases/search", {"materia_id": self.materia_search.id, "limit": 50, "offset": 0})
        self.assertEqual(r.status_code, 200, r.json())
        ids = [x["id"] for x in r.json()["results"]]

        # tie-break: misma ranking => fecha_inicio ASC => c_early primero
        self.assertEqual(ids[:3], [c_early, c_late, c_zero])

    def test_search_filtra_por_dias_y_solape_de_horas(self):
        """
        Prueba específicamente el filtro de horarios:
        - Creamos 3 clases futuras PUBLICADAS en la misma materia
        - Filtramos: dias=[1], hora_desde=20:00, hora_hasta=22:00

        Regla de solape en tu SQL:
          h.hora_inicio < hora_hasta  AND  h.hora_fin > hora_desde
        """
        today = date.today()

        # Clase 1: 19-21 (solapa con 20-22)
        c1 = self._create_clase_api(
            materia_id=self.materia_search.id,
            estado="PUBLICADA",
            fi=today + timedelta(days=10),
            ff=today + timedelta(days=10),
            horarios=[{"dia_semana": 1, "hora_inicio": "19:00:00", "hora_fin": "21:00:00"}],
            creadores=[{"profesor_id": self.prof_a, "porcentaje_reparto": "100.00"}],
        )

        # Clase 2: 18-20 (NO solapa con 20-22 porque hora_fin > 20 debe ser True, pero 20 > 20 es False)
        c2 = self._create_clase_api(
            materia_id=self.materia_search.id,
            estado="PUBLICADA",
            fi=today + timedelta(days=11),
            ff=today + timedelta(days=11),
            horarios=[{"dia_semana": 1, "hora_inicio": "18:00:00", "hora_fin": "20:00:00"}],
            creadores=[{"profesor_id": self.prof_b, "porcentaje_reparto": "100.00"}],
        )

        # Clase 3: día 2 (no pasa filtro de dias=[1])
        c3 = self._create_clase_api(
            materia_id=self.materia_search.id,
            estado="PUBLICADA",
            fi=today + timedelta(days=12),
            ff=today + timedelta(days=12),
            horarios=[{"dia_semana": 2, "hora_inicio": "19:00:00", "hora_fin": "21:00:00"}],
            creadores=[{"profesor_id": self.prof_c, "porcentaje_reparto": "100.00"}],
        )

        r = self.client.get(
            "/api/clases/search",
            {
                "materia_id": self.materia_search.id,
                "dias": [1],
                "hora_desde": "20:00:00",
                "hora_hasta": "22:00:00",
                "limit": 50,
                "offset": 0,
            },
        )
        self.assertEqual(r.status_code, 200, r.json())
        ids = [x["id"] for x in r.json()["results"]]

        self.assertEqual(ids, [c1], f"Se esperaba solo {c1}. Se obtuvo: {ids}. (c2={c2}, c3={c3})")

    def test_search_filtra_por_from_y_paginacion(self):
        """
        Valida:
        - filtro from: fecha_inicio >= from
        - paginación limit/offset

        No depende del ranking: solo verifica que el endpoint filtra y pagina bien.
        """
        today = date.today()

        c1 = self._create_clase_api(
            materia_id=self.materia_search.id,
            estado="PUBLICADA",
            fi=today + timedelta(days=9),
            ff=today + timedelta(days=9),
            creadores=[{"profesor_id": self.prof_a, "porcentaje_reparto": "100.00"}],
        )
        c2 = self._create_clase_api(
            materia_id=self.materia_search.id,
            estado="PUBLICADA",
            fi=today + timedelta(days=11),
            ff=today + timedelta(days=11),
            creadores=[{"profesor_id": self.prof_b, "porcentaje_reparto": "100.00"}],
        )
        c3 = self._create_clase_api(
            materia_id=self.materia_search.id,
            estado="PUBLICADA",
            fi=today + timedelta(days=12),
            ff=today + timedelta(days=12),
            creadores=[{"profesor_id": self.prof_c, "porcentaje_reparto": "100.00"}],
        )

        # from = hoy+11 => deben quedar c2 y c3 (c1 se elimina)
        r = self.client.get(
            "/api/clases/search",
            {"materia_id": self.materia_search.id, "from": iso(today + timedelta(days=11)), "limit": 50, "offset": 0},
        )
        self.assertEqual(r.status_code, 200, r.json())
        ids = [x["id"] for x in r.json()["results"]]
        self.assertTrue(c1 not in ids)
        self.assertTrue(c2 in ids and c3 in ids)

        # paginación: limit=1 offset=1 => debe devolver el 2do resultado
        r2 = self.client.get("/api/clases/search", {"materia_id": self.materia_search.id, "limit": 1, "offset": 1})
        self.assertEqual(r2.status_code, 200, r2.json())
        self.assertEqual(len(r2.json()["results"]), 1)

        # Nota: el orden puede depender del ranking y fecha_inicio, por eso aquí solo validamos "1 elemento".
        # Si quieres validar ID exacto, primero sembrar cache y fijar ranking/fechas para hacer determinista el orden.
        self.assertIn(r2.json()["results"][0]["id"], [c1, c2, c3])

