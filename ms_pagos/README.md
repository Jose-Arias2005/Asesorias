# 💸 Microservicio de Pagos y Billetera (MS-Pagos)

Este microservicio es el corazón financiero de la plataforma. Su responsabilidad única es gestionar billeteras digitales, procesar movimientos de dinero (ingresos y egresos) y mantener un registro contable inmutable.

> **Arquitectura:** Microservicio Aislado (Database-per-service).
> **Patrón:** Orquestación (Este servicio no toma decisiones de negocio académico, solo ejecuta órdenes financieras).

---

## 🧠 Lógica de Negocio y Arquitectura

A diferencia de un sistema monolítico tradicional, este servicio **no conoce** conceptos como "Alumno", "Profesor", "Materia" o "Horario". Su diseño es agnóstico y se basa en dos pilares:

### 1. Modelo "Wallet & Ledger"
El sistema se basa en solo dos tablas optimizadas para consistencia transaccional:
* **Wallet (Billetera):** Almacena el saldo actual y el estado (activo/congelado) de un `user_id`. No le importa el rol del usuario.
* **Transaction (Libro Mayor):** Registro histórico inmutable de cada centavo que se mueve.
    * **Atomicidad:** Utilizamos `transaction.atomic()` para garantizar que el saldo y el historial se actualicen al mismo tiempo o no se actualicen en absoluto.

### 2. Flexibilidad vía JSON (`info`)
Para evitar llenar la base de datos de columnas vacías (nulls), utilizamos un campo `JSONField` llamado `info`.
* Si es una **Recarga Yape**, guardamos: `{"celular": "...", "operacion": "..."}`.
* Si es un **Retiro Bancario**, guardamos: `{"banco": "BCP", "cci": "..."}`.

### 3. Referencias Externas
El **Orquestador** es quien nos dice "Cobra por la Reserva X". Nosotros guardamos ese ID en el campo `external_reference` para auditoría futura, permitiendo cruzar datos con el Microservicio Académico sin acoplar las bases de datos.

---

## 🚀 Stack Tecnológico

* **Lenguaje:** Python 3.12
* **Framework:** Django REST Framework (DRF)
* **Base de Datos:** PostgreSQL 15 (Dockerizado)
* **Contenedores:** Docker & Docker Compose
* **Documentación:** Swagger / OpenAPI 3.0

---

## 🛠️ Configuración e Instalación

### 1. Variables de Entorno
Crea un archivo `.env` en la raíz (basado en `.env.example`):

```env
SECRET_KEY=tu_secreto_super_seguro
DEBUG=True
ALLOWED_HOSTS=*

# Configuración de Base de Datos (Interna de Docker)
DB_NAME=db_pagos
DB_USER=postgres_user
DB_PASSWORD=postgres_password
DB_HOST=db
DB_PORT=5432
```

### 2. Levanta el Proyecto
Con Docker instalado, ejecuta:
```bash
# Construir y levantar contenedores en segundo plano
docker compose up -d --build
```

### 3. Inicialización (Por única vez)
Al ser un entorno nuevo, debes aplicar las migraciones y crear un superusuario:

```bash
# Crear tablas en la BD
docker exec -it ms_pagos_web python manage.py migrate

# Crear administrador para el panel
docker exec -it ms_pagos_web python manage.py createsuperuser
```
---
## 📡 Endpoints Principales

La documentación interactiva completa está disponible en: 👉 http://127.0.0.1:8000/swagger/

### 💼 Billetera (Wallet)
- POST /api/wallet/ - Crear Billetera: Se llama cuando un usuario se registra en la plataforma.

- GET /api/wallet/{user_id}/ - Ver Saldo: Consulta el estado financiero de un usuario.

### 💸 Transacciones (Transactions)
- POST /api/transaction/deposit/ - Recarga/Ingreso:

    - Usado para recargas de saldo (Yape, Tarjeta) o reembolsos.

    - Incrementa el saldo.

- POST /api/transaction/charge/ - Cobro/Egreso:

    - Usado para pagar Reservas, Comisiones por crear clase o Retiros de dinero.

    - Resta el saldo (valida fondos insuficientes).

Requiere external_reference (ej: ID de la Reserva) para trazabilidad.

---
## ✅ Testing
El proyecto cuenta con pruebas End-to-End (E2E) que simulan el flujo completo desde la API hasta la base de datos.

Para ejecutar los tests:

```bash
docker exec -it ms_pagos_web python manage.py test finance
```