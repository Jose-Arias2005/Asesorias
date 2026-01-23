from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .services import execute_recharge, execute_payment, create_wallet
from .serializers import WalletSerializer, TransactionSerializer, OperationSerializer
from .models import Wallet

class WalletView(APIView):
    """
    GET: Ver saldo de un usuario
    POST: Crear billetera (Idempotente)
    """
    def get(self, request, user_id):
        try:
            wallet = Wallet.objects.get(user_id=user_id)
            return Response(WalletSerializer(wallet).data)
        except Wallet.DoesNotExist:
            return Response({"error": "Billetera no encontrada"}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request):
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({"error": "user_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)
        
        wallet = create_wallet(user_id)
        return Response(WalletSerializer(wallet).data, status=status.HTTP_201_CREATED)

class RechargeView(APIView):
    """
    POST: Recargar saldo (Integración con Pasarela de Pagos externa sería aquí)
    """
    def post(self, request):
        serializer = OperationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                trx = execute_recharge(
                    user_id=serializer.validated_data['user_id'],
                    amount=serializer.validated_data['amount'],
                    payment_method=serializer.validated_data.get('payment_method', 'YAPE')
                )
                return Response(TransactionSerializer(trx).data, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PaymentView(APIView):
    """
    POST: Cobrar una clase (Usado por MS Reservas)
    """
    def post(self, request):
        serializer = OperationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                trx = execute_payment(
                    user_id=serializer.validated_data['user_id'],
                    amount=serializer.validated_data['amount']
                )
                return Response(TransactionSerializer(trx).data, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)