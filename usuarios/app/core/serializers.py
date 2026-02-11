from rest_framework import serializers
from .models import Usuario, PerfilAlumno, PerfilProfesor
from django.contrib.auth.password_validation import validate_password

class PerfilAlumnoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerfilAlumno
        fields = ['ciclo_relativo']

class PerfilProfesorSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerfilProfesor
        fields = ['valoracion']

class UsuarioSerializer(serializers.ModelSerializer):
    perfil_alumno = PerfilAlumnoSerializer(read_only=True)
    perfil_profesor = PerfilProfesorSerializer(read_only=True)

    class Meta:
        model = Usuario
        fields = [
            'id', 'codigo', 'email', 'nombres', 'apellidos', 'carrera',
            'es_alumno', 'es_profesor', 
            'perfil_alumno', 'perfil_profesor'
        ]

        read_only_fields = ['id', 'codigo', 'es_alumno', 'es_profesor']

class RegistroUsuarioSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    
    # Campos opcionales para datos específicos
    ciclo_relativo = serializers.IntegerField(required=False, write_only=True)
    
    class Meta:
        model = Usuario
        fields = [
            'codigo', 'email', 'nombres', 'apellidos', 'carrera', 'password',
            'es_alumno', 'es_profesor',
            'ciclo_relativo' 
        ]

    def create(self, validated_data):
        ciclo = validated_data.pop('ciclo_relativo', 1)
        password = validated_data.pop('password')
        
        # 1. Crear Usuario
        user = Usuario(**validated_data)
        user.set_password(password)
        user.save()

        # 2. Crear Perfil Alumno si corresponde
        if user.es_alumno:
            PerfilAlumno.objects.create(usuario=user, ciclo_relativo=ciclo)
        
        # 3. Crear Perfil Profesor si corresponde
        if user.es_profesor:
            PerfilProfesor.objects.create(usuario=user)

        return user
    
    def validate_ciclo_relativo(self, value):
        if value < 1 or value > 10:
            raise serializers.ValidationError("El ciclo debe estar entre 1 y 10.")
        return value

    def validate(self, data):
        if data.get('es_profesor') and data.get('valoracion', 0) > 5:
             pass
        return data
    
class CambiarPasswordSerializer(serializers.Serializer):
    password_actual = serializers.CharField(required=True)
    password_nueva = serializers.CharField(required=True, validators=[validate_password])

    def validate_password_actual(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("La contraseña actual es incorrecta.")
        return value
