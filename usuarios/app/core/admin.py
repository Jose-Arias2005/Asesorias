from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Usuario, PerfilAlumno, PerfilProfesor

class PerfilAlumnoInline(admin.StackedInline):
    model = PerfilAlumno
    can_delete = False
    verbose_name_plural = 'Perfil de Alumno'

class PerfilProfesorInline(admin.StackedInline):
    model = PerfilProfesor
    can_delete = False
    verbose_name_plural = 'Perfil de Profesor'

class UsuarioAdmin(BaseUserAdmin):
    # Configuración de listas
    list_display = ('codigo', 'nombres', 'apellidos', 'carrera', 'es_alumno', 'es_profesor')
    list_filter = ('es_alumno', 'es_profesor', 'carrera')
    search_fields = ('codigo', 'email', 'nombres')
    ordering = ('codigo',)

    # Formulario de edición
    fieldsets = (
        ('Credenciales', {'fields': ('codigo', 'password')}),
        ('Información Personal', {'fields': ('nombres', 'apellidos', 'email', 'carrera')}),
        ('Roles', {'fields': ('es_alumno', 'es_profesor')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )
    
    inlines = [PerfilAlumnoInline, PerfilProfesorInline]

admin.site.register(Usuario, UsuarioAdmin)