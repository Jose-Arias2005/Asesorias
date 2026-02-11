from django.urls import path
from .views import RegistroUsuarioView, MiPerfilView, CambiarPasswordView

urlpatterns = [
    path('registro/', RegistroUsuarioView.as_view(), name='registro'),
    path('me/', MiPerfilView.as_view(), name='mi_perfil'),
    path('me/password/', CambiarPasswordView.as_view(), name='cambiar_password'),
]