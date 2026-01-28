from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView 
from .models import Usuario
from .serializers import (
    RegistroUsuarioSerializer, 
    UsuarioSerializer, 
    CambiarPasswordSerializer 
)

# Endpoint para Registrarse (Público)
class RegistroUsuarioView(generics.CreateAPIView):
    queryset = Usuario.objects.all()
    serializer_class = RegistroUsuarioSerializer
    permission_classes = [permissions.AllowAny] 


class MiPerfilView(generics.RetrieveUpdateAPIView):
    serializer_class = UsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
    
class CambiarPasswordView(generics.UpdateAPIView):
    serializer_class = CambiarPasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            # Setear nueva password y guardar
            request.user.set_password(serializer.validated_data['password_nueva'])
            request.user.save()
            return Response({"message": "Contraseña actualizada correctamente."}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)