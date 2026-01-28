import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

# -----------------------------------------------------------------------------
# MANAGER
# -----------------------------------------------------------------------------
class UsuarioManager(BaseUserManager):
    def create_user(self, codigo, email, nombres, apellidos, carrera, password=None, **extra_fields):
        if not codigo:
            raise ValueError('El usuario debe tener un código')
        
        email = self.normalize_email(email)
        user = self.model(
            codigo=codigo, 
            email=email, 
            nombres=nombres, 
            apellidos=apellidos,
            carrera=carrera,
            **extra_fields
        )
        user.set_password(password) 
        user.save(using=self._db)
        return user

    def create_superuser(self, codigo, email, nombres, apellidos, carrera="ADMIN", password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(codigo, email, nombres, apellidos, carrera, password, **extra_fields)

# -----------------------------------------------------------------------------
# MODELO USUARIO (Datos comunes + Carrera)
# -----------------------------------------------------------------------------
class Usuario(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Atributos Base solicitados
    codigo = models.CharField(max_length=20, unique=True)
    email = models.EmailField(unique=True)
    nombres = models.CharField(max_length=150)
    apellidos = models.CharField(max_length=150)
    carrera = models.CharField(max_length=100) 

    # Banderas para identificar rol rápidamente
    es_alumno = models.BooleanField(default=False)
    es_profesor = models.BooleanField(default=False)

    # Django Admin requerimientos
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    objects = UsuarioManager()

    USERNAME_FIELD = 'codigo'
    REQUIRED_FIELDS = ['email', 'nombres', 'apellidos', 'carrera']

    def __str__(self):
        return f"{self.codigo} ({self.carrera})"

# -----------------------------------------------------------------------------
# TABLA ALUMNOS (Se mantiene para futuro)
# -----------------------------------------------------------------------------
class PerfilAlumno(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name='perfil_alumno')
    
    # Atributo exclusivo de alumno
    ciclo_relativo = models.IntegerField(default=1, help_text="Ciclo actual del alumno")

    def __str__(self):
        return f"Alumno: {self.usuario.codigo} - Ciclo {self.ciclo_relativo}"

# -----------------------------------------------------------------------------
# TABLA PROFESORES
# -----------------------------------------------------------------------------
class PerfilProfesor(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name='perfil_profesor')
    
    # Atributo exclusivo de profesor
    valoracion = models.DecimalField(max_digits=3, decimal_places=2, default=5.00)

    def __str__(self):
        return f"Profesor: {self.usuario.codigo} - Val: {self.valoracion}"