from rest_framework import serializers
from .models import Wallet, Transaction

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ['user_id', 'balance', 'is_active', 'updated_at']

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'

class TransactionInputSerializer(serializers.Serializer):
    user_id = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    # Campos opcionales nuevos
    external_reference = serializers.CharField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_null=True)
    payment_method = serializers.ChoiceField(choices=Transaction.PaymentMethod.choices, required=False)
    
    # Para recibir el JSON desde el frontend/orquestador
    info = serializers.JSONField(required=False, default=dict)