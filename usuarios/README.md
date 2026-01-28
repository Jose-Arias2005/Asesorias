# 🎓 Microservicio de Usuarios (Auth & Profiles)

Microservicio encargado de la gestión de identidad, autenticación (JWT) y perfiles académicos (Alumnos y Profesores) para la plataforma universitaria.

Este servicio está construido con **Django Rest Framework** y sigue una arquitectura dockerizada lista para desplegar.

---

## 🚀 Tecnologías

* **Python 3.11** + **Django 5**
* **Django Rest Framework** (API)
* **SimpleJWT** (Autenticación segura)
* **PostgreSQL 15** (Base de Datos)
* **Docker & Docker Compose** (Contenedorización)
* **Drf-Spectacular** (Documentación Swagger/OpenAPI)
* **Whitenoise** (Servidor de estáticos)

---

## 🛠️ Instalación y Despliegue

### Opción A: Usando Docker (Recomendado) 🐳
Esta es la forma más rápida. No necesitas instalar Python ni Postgres en tu máquina.

1.  **Clonar el repositorio:**
    ```bash
    git clone <tu-repo-url>
    cd microservicio-usuarios
    ```

2.  **Configurar Variables de Entorno:**
    Copia el archivo de ejemplo y renómbralo.
    ```bash
    cp .env.example .env
    ```

3.  **Levantar el servicio:**
    ```bash
    docker-compose up --build
    ```
    *El servicio estará disponible en: `http://localhost:8000`*

4.  **Inicializar Base de Datos (Solo la primera vez):**
    En otra terminal, ejecuta:
    ```bash
    # Aplicar migraciones
    docker-compose exec web python manage.py migrate
    
    # Crear superusuario (Admin)
    docker-compose exec web python manage.py createsuperuser
    ```

### Opción B: Instalación Manual (Local) 💻
Si prefieres correrlo sin Docker:

1.  Crear entorno virtual: `python -m venv venv` y activarlo.
2.  Instalar dependencias: `pip install -r requirements.txt`.
3.  Tener PostgreSQL corriendo y crear una BD llamada `db_usuarios`.
4.  Configurar `.env` apuntando a tu BD local (`DB_HOST=localhost`).
5.  Migrar y correr:
    ```bash
    python manage.py migrate
    python manage.py runserver
    ```

---

## 📚 Documentación de API (Swagger)

No necesitas adivinar los endpoints. Una vez corriendo el servidor, visita:

👉 **Documentación Interactiva:** [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/)

Desde ahí puedes probar el Login, Registro y ver los esquemas de datos JSON requeridos.

---

## 🔑 Endpoints Principales

### Autenticación
| Método | Endpoint | Descripción |
|:---|:---|:---|
| `POST` | `/api/auth/login/` | Obtener Access y Refresh Token (JWT). |
| `POST` | `/api/auth/refresh/` | Refrescar un token vencido. |

### Usuarios
| Método | Endpoint | Descripción | Requiere Token |
|:---|:---|:---|:---:|
| `POST` | `/api/v1/registro/` | Registrar nuevo Alumno o Profesor. | ❌ |
| `GET` | `/api/v1/me/` | Ver mi perfil y datos de rol. | ✅ |
| `PATCH` | `/api/v1/me/` | Actualizar datos básicos (Email, Nombres). | ✅ |
| `PUT` | `/api/v1/me/password/` | Cambiar contraseña. | ✅ |

---

## 🧪 Tests y Calidad

Para ejecutar las pruebas automatizadas y verificar que todo funciona correctamente:

**En Docker:**
```bash
docker-compose exec web python manage.py test core