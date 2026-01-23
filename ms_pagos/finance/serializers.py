from rest_framework import serializers
from .models import Wallet, Transaction

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ['user_id', 'balance', 'updated_at']

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'amount', 'transaction_type', 'status', 'created_at']

# Serializer para validar la entrada de una recarga o pago
class OperationSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    # Solo para recargas
    payment_method = serializers.ChoiceField(choices=Transaction.PaymentMethod.choices, required=False)