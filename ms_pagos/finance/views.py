from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .services import execute_transaction, create_wallet
from .serializers import WalletSerializer, TransactionSerializer, TransactionInputSerializer
from .models import Wallet, Transaction


# --- VISTAS DE BILLETERA (Separadas para limpieza en Swagger) ---
class WalletCreateView(APIView):
    """
    POST: Crea una billetera nueva.
    Usado por el Orquestador cuando se registra un usuario nuevo.
    """
    def post(self, request):
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({"error": "user_id es requerido"}, status=status.HTTP_400_BAD_REQUEST)
        
        wallet = create_wallet(user_id)
        return Response(WalletSerializer(wallet).data, status=status.HTTP_201_CREATED)

class WalletDetailView(APIView):
    """
    GET: Ver saldo y estado de un usuario específico.
    """
    def get(self, request, user_id):
        try:
            wallet = Wallet.objects.get(user_id=user_id)
            return Response(WalletSerializer(wallet).data)
        except Wallet.DoesNotExist:
            return Response({"error": "Billetera no encontrada"}, status=status.HTTP_404_NOT_FOUND)

# --- VISTAS DE TRANSACCIONES (Usan el servicio maestro) ---
class ChargeView(APIView):
    """
    POST: Cobrar dinero (salidas).
    Usado para: Pagar Reservas, Comisiones, Retiros.
    El Orquestador define el 'type' y envía la 'info' necesaria.
    """
    def post(self, request):
        # 1. Validamos la entrada con el Serializer de Input
        serializer = TransactionInputSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            try:
                # 2. Definimos el tipo de transacción (Default: Pago de Reserva)
                # El orquestador puede mandar 'type' si es un COBRO_CREAR_CLASE, por ejemplo.
                trx_type = request.data.get('type', Transaction.TransactionType.PAYMENT_RESERVA)
                
                # 3. Ejecutamos la transacción (Forzamos negativo con -abs)
                trx = execute_transaction(
                    user_id=data['user_id'],
                    amount=-abs(data['amount']), # SIEMPRE negativo para cobros
                    type=trx_type,
                    payment_method=data.get('payment_method'), 
                    reference=data.get('external_reference'), # ID de Reserva/Clase
                    source="ORQUESTADOR",
                    description=data.get('description'),
                    extra_info=data.get('info')
                )
                return Response(TransactionSerializer(trx).data, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RechargeView(APIView):
    """
    POST: Ingresar dinero (Entradas).
    Usado para: Recargas Yape/Plin/Tarjeta o Reembolsos.
    """
    def post(self, request):
        serializer = TransactionInputSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            try:
                # Ejecutamos transacción (Forzamos positivo con abs)
                trx = execute_transaction(
                    user_id=data['user_id'],
                    amount=abs(data['amount']), # SIEMPRE positivo para recargas
                    type=Transaction.TransactionType.RECHARGE,
                    payment_method=data.get('payment_method', Transaction.PaymentMethod.YAPE),
                    description="Recarga de Saldo",
                    extra_info=data.get('info')
                )
                return Response(TransactionSerializer(trx).data, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)