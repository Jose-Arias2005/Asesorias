from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from .models import PerfilAlumno, PerfilProfesor

Usuario = get_user_model()

class UsuarioTests(APITestCase):
    def setUp(self):
        # Datos base para pruebas
        self.alumno_data = {
            'codigo': '20241001',
            'email': 'alumno@test.com',
            'nombres': 'Juan',
            'apellidos': 'Perez',
            'carrera': 'Sistemas',
            'password': 'password123',
            'es_alumno': True,
            'ciclo_relativo': 5
        }
        self.profesor_data = {
            'codigo': 'DOC200',
            'email': 'profe@test.com',
            'nombres': 'Maria',
            'apellidos': 'Lopez',
            'carrera': 'CS',
            'password': 'password123',
            'es_profesor': True,
            'valoracion': 4.5
        }

    def test_registro_alumno(self):
        """Prueba que se crea usuario + perfil alumno"""
        url = reverse('registro')
        response = self.client.post(url, self.alumno_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Usuario.objects.filter(codigo='20241001').exists())
        self.assertTrue(PerfilAlumno.objects.filter(usuario__codigo='20241001').exists())

    def test_login_jwt(self):
        """Prueba que el login devuelve tokens"""
        self.client.post(reverse('registro'), self.alumno_data, format='json')
        
        url = reverse('token_obtain_pair')
        data = {'codigo': '20241001', 'password': 'password123'}
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_ver_perfil_privado(self):
        """Prueba que no se puede ver perfil sin token"""
        url = reverse('mi_perfil')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)